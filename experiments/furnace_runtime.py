"""Batched, final-only local inference. Enter through the managed launcher."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import queue
import re
import subprocess
import sys
import time
from collections.abc import Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from magic_realism_thought.types import ChatRequest, ChatResult, ProviderError


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def model_identity(path: Path) -> dict:
    index = path / "model.safetensors.index.json"
    weights = sorted(set(json.loads(index.read_text())["weight_map"].values())) if index.exists() else ["model.safetensors"]
    names = sorted(set(weights) | {file.name for file in path.iterdir()
                                  if file.suffix in {"json", ".json", ".jinja", ".model"}})
    records = []
    for name in names:
        file = path / name
        if not file.is_file():
            raise ValueError(f"missing model artifact: {name}")
        sha = digest(file)
        blob = file.resolve().name
        if len(blob) == 64 and re.fullmatch(r"[0-9a-f]{64}", blob) and blob != sha:
            raise ValueError(f"cached model blob hash mismatch: {name}")
        records.append({"file": name, "bytes": file.stat().st_size, "sha256": sha})
    reference = path / "MODEL_IDENTITY.json"
    if reference.exists():
        expected = json.loads(reference.read_text())
        actual = {item["file"]: item for item in records}
        for item in expected["files"]:
            file = path / item["path"]
            observed = actual.get(item["path"])
            sha = observed["sha256"] if observed else digest(file)
            if sha != item["sha256"] or file.stat().st_size != item["bytes"]:
                raise ValueError(f"model identity receipt mismatch: {item['path']}")
    encoded = json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
    return {"path": str(path), "revision": path.name, "files": records,
            "sha256": hashlib.sha256(encoded).hexdigest()}


class TrtEngine:
    def __init__(self, path: Path, batch_size: int, max_tokens: int, harmony_adapter: Path | None = None):
        owners = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip()
        if owners:
            raise RuntimeError("GPU compute owner exists; do not launch over another workload")
        self.identity = model_identity(path)
        self.adapter = None
        self.harmony = None
        if harmony_adapter:
            expected = "579c0672eeb7837690540e7ed670cf612bda07440d37ba4e9cdaa57ed362eedc"
            if digest(harmony_adapter) != expected:
                raise ValueError("final-only Harmony adapter hash mismatch")
            if digest(path / "MODEL_IDENTITY.json") != "6ddf1ef642669cdb5e110b502c05bc2666aa34c0cbe2b4179f1aa90a2edb4bac":
                raise ValueError("pinned GPT-OSS model identity receipt mismatch")
            spec = importlib.util.spec_from_file_location("cmrt_final_only_adapter", harmony_adapter)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            self.adapter = module
            from openai_harmony import ReasoningEffort
            from tensorrt_llm.serve.harmony_adapter import HarmonyAdapter
            self.harmony = HarmonyAdapter(default_reasoning_effort=ReasoningEffort.LOW)
        from transformers import AutoTokenizer
        from tensorrt_llm import LLM, SamplingParams
        from tensorrt_llm.llmapi.llm_args import MoeConfig
        self.params = SamplingParams
        self.tokenizer = AutoTokenizer.from_pretrained(str(path), local_files_only=True, trust_remote_code=False)
        self.max_tokens = max_tokens
        generation = json.loads((path / "generation_config.json").read_text())
        stop = generation.get("eos_token_id", self.tokenizer.eos_token_id)
        self.stop_ids = stop if isinstance(stop, list) else [stop]
        if self.harmony:
            self.stop_ids = self.harmony.get_stop_tokens()
        kwargs = {"model": str(path), "backend": "pytorch", "dtype": "auto", "trust_remote_code": False,
                  "tensor_parallel_size": 1, "max_batch_size": batch_size, "max_input_len": 8192,
                  "max_seq_len": 8192 + max_tokens, "max_num_tokens": 8192, "enable_chunked_prefill": True}
        if self.harmony:
            kwargs.update(moe_config=MoeConfig(backend="CUTLASS"), attn_backend="TRTLLM", enable_autotuner=True)
        started = time.monotonic()
        self.llm = LLM(**kwargs)
        self.load_seconds = time.monotonic() - started
        self.batch_receipts = []

    def close(self):
        self.llm.shutdown()

    def generate(self, requests: list[tuple[ChatRequest, int]]) -> list[ChatResult | Exception]:
        prompts = []
        parameters = []
        for request, seed in requests:
            # A single user message supports templates that forbid a system role.
            content = f"{request.system}\n\n{request.prompt}"
            messages = [{"role": "user", "content": content}]
            if self.harmony:
                from openai_harmony import ReasoningEffort
                tokens = self.harmony.openai_to_harmony_tokens(messages, available_tools=None,
                            reasoning_effort=ReasoningEffort.LOW, tool_choice="none")
            else:
                tokens = self.tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                                            return_dict=False)
                if isinstance(tokens, Mapping):
                    tokens = tokens["input_ids"]
                if not isinstance(tokens, list) or any(type(token) is not int for token in tokens):
                    raise ValueError("chat template must produce a flat integer token list")
            if len(tokens) > 8192:
                raise ValueError("rendered prompt exceeds frozen context budget")
            prompts.append(tokens)
            parameters.append(self.params(max_tokens=request.max_tokens, temperature=request.temperature,
                top_p=0.95, top_k=40, seed=seed, n=1, stop_token_ids=self.stop_ids,
                exclude_input_from_output=True, detokenize=False, add_special_tokens=False, skip_special_tokens=False))
        started = time.monotonic()
        outputs = self.llm.generate(prompts, sampling_params=parameters, use_tqdm=False)
        elapsed = time.monotonic() - started
        if not isinstance(outputs, list) or len(outputs) != len(requests):
            raise RuntimeError("inference output count mismatch")
        results = []
        receipts = []
        for (request, seed), tokens, output in zip(requests, prompts, outputs):
            if len(output.outputs) != 1:
                raise RuntimeError("inference completion count mismatch")
            completion = output.outputs[0]
            ids = list(completion.token_ids or [])
            receipt = {"seed": seed, "prompt_sha256": hashlib.sha256(request.prompt.encode()).hexdigest(),
                       "prompt_tokens": len(tokens), "completion_tokens": len(ids),
                       "finish_reason": str(completion.finish_reason), "batch_seconds": elapsed}
            text = ""
            if self.harmony:
                route = self.adapter.route_completion_tokens(ids)
                if (route.reason_codes == ("harmony_parse_error",) and completion.finish_reason == "stop"
                        and completion.stop_reason in self.stop_ids):
                    route = self.adapter.route_completion_tokens([*ids, completion.stop_reason])
                receipt["final_gate"] = route.public_receipt()
                if route.status == "accepted":
                    text = route.accepted_final_text or ""
            else:
                text = self.tokenizer.decode(ids, skip_special_tokens=True).strip()
            if completion.finish_reason != "stop":
                receipt["status"] = "incomplete"
            elif not text or re.search(r"<\s*/?\s*think\s*>|<\|(?:start|channel|im_start)\|>", text, re.I):
                receipt["status"] = "final_gate_failed"
            else:
                receipt["status"] = "complete"
                receipt["output_sha256"] = hashlib.sha256(text.encode()).hexdigest()
            receipts.append(receipt)
            if receipt["status"] == "complete":
                results.append(ChatResult(provider="local", model=request.model, text=text, usage=receipt))
            else:
                results.append(ProviderError(f"completion_not_accepted:{receipt['status']}:{receipt['finish_reason']}"))
        self.batch_receipts.append({"elapsed_seconds": elapsed, "requests": receipts})
        return results


@dataclass
class Pending:
    request: ChatRequest
    seed: int
    future: Future


class VllmEngine(TrtEngine):
    """Use only after a preserved TRT canary failure; share completion gates."""
    def __init__(self, path: Path, batch_size: int, max_tokens: int, harmony_adapter=None):
        if harmony_adapter:
            raise ValueError("this fallback supports non-Harmony models only")
        owners = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip()
        if owners:
            raise RuntimeError("GPU compute owner exists; do not launch over another workload")
        self.identity = model_identity(path)
        from transformers import AutoTokenizer
        from vllm import LLM, SamplingParams
        self.tokenizer = AutoTokenizer.from_pretrained(str(path), local_files_only=True, trust_remote_code=False)
        self.adapter = self.harmony = None
        self.max_tokens = max_tokens
        stop = json.loads((path / "generation_config.json").read_text()).get("eos_token_id", self.tokenizer.eos_token_id)
        self.stop_ids = stop if isinstance(stop, list) else [stop]
        self.params = lambda **kwargs: SamplingParams(**{key: value for key, value in kwargs.items()
                            if key not in {"exclude_input_from_output", "add_special_tokens"}})
        started = time.monotonic()
        llm = LLM(model=str(path), tokenizer=str(path), trust_remote_code=False, dtype="auto",
                  tensor_parallel_size=1, max_model_len=8192 + max_tokens, max_num_seqs=batch_size,
                  max_num_batched_tokens=8192, gpu_memory_utilization=0.90, enforce_eager=True,
                  enable_prefix_caching=False, disable_log_stats=True, limit_mm_per_prompt={"image": 0})
        self.load_seconds = time.monotonic() - started
        self.batch_receipts = []
        self._raw_llm = llm

        class TokenBatch:
            def generate(self, prompts, **kwargs):
                return llm.generate([{"prompt_token_ids": tokens} for tokens in prompts], **kwargs)
        self.llm = TokenBatch()

    def close(self):
        self._raw_llm.llm_engine.engine_core.shutdown()


class QueuedProvider:
    def __init__(self, inbox: queue.Queue, seed: int, on_result=None):
        self.inbox = inbox
        self.seed = seed
        self.ordinal = 0
        self.on_result = on_result

    def generate(self, request: ChatRequest) -> ChatResult:
        raw = f"{self.seed}:{self.ordinal}".encode()
        seed = int.from_bytes(hashlib.sha256(raw).digest()[:4], "big") % (2**31 - 1)
        ordinal = self.ordinal
        self.ordinal += 1
        future = Future()
        self.inbox.put(Pending(request, seed, future))
        try:
            result = future.result()
        except Exception as exc:
            if self.on_result:
                self.on_result(ordinal, request, seed, None, exc)
            raise
        if self.on_result:
            self.on_result(ordinal, request, seed, result, None)
        return result


def execute_tasks(engine, tasks, worker, concurrency: int, on_progress=None):
    """Run existing synchronous runners while one engine batches their requests."""
    inbox = queue.Queue()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(worker, task, inbox) for task in tasks]
        done_count = 0
        while any(not future.done() for future in futures):
            pending = []
            try:
                pending.append(inbox.get(timeout=0.1))
            except queue.Empty:
                continue
            deadline = time.monotonic() + 0.025
            while len(pending) < concurrency and time.monotonic() < deadline:
                try:
                    pending.append(inbox.get(timeout=max(0.001, deadline - time.monotonic())))
                except queue.Empty:
                    break
            try:
                results = engine.generate([(item.request, item.seed) for item in pending])
                if len(results) != len(pending):
                    raise RuntimeError("batch result count mismatch")
            except Exception as exc:
                results = [exc] * len(pending)
            for item, result in zip(pending, results):
                if isinstance(result, Exception):
                    item.future.set_exception(result)
                else:
                    item.future.set_result(result)
            count = sum(future.done() for future in futures)
            if on_progress and count != done_count:
                on_progress(count, len(tasks))
                done_count = count
        return [future.result() for future in futures]
