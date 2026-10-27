"""Rejudge fixed visible passages through OpenAI; no regeneration or automatic retry."""
from __future__ import annotations

import argparse
import collections
import fcntl
import hashlib
import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import version
from pathlib import Path

from analyze_frontier_study import verify_manifest
from frontier_study import (JUDGE_SYSTEM, ROOT, canonical, complete_pairs, frozen,
                            judge_prompt, save, save_manifest, source_receipt, state)
from furnace_runtime import digest

ENDPOINT = "https://api.openai.com/v1"
CATEGORIES = ("winner", "continuity", "restraint", "freshness")
# Standard short-context rates, verified 2026-10-27. Use the higher 30m-write
# input rate for every byte-token in the budget; no cached-read discount assumed.
PRICING = {"input_per_million_usd": 12.5, "output_per_million_usd": 50.0,
           "source": "https://developers.openai.com/api/docs/pricing", "checked_date": "2026-10-27"}


def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def request_payload(model: str, prompt: str, max_tokens: int) -> dict:
    return {"model": model, "instructions": JUDGE_SYSTEM, "input": prompt,
            "reasoning": {"effort": "low"}, "max_output_tokens": max_tokens,
            "store": False, "service_tier": "default", "prompt_cache_options": {"ttl": "30m"}}


def cost_ceiling(prompt: str, max_tokens: int) -> dict:
    # UTF-8 bytes upper-bound byte-fallback text tokens; 256 extra tokens reserve
    # role/framing overhead. Provider usage is checked against this bound.
    bound = len((JUDGE_SYSTEM + prompt).encode()) + 256
    return {"input_token_bound": bound,
            "usd_bound": (bound * PRICING["input_per_million_usd"] +
                          max_tokens * PRICING["output_per_million_usd"]) / 1e6}


def prepare(args) -> tuple[dict, list[dict]]:
    identities = {}
    tasks = []
    names = set()
    for study in args.studies:
        if study.name in names:
            raise ValueError("study names must be unique")
        names.add(study.name)
        identities[str(study)] = verify_manifest(study)
        for config, item, replicate, paths, runs in complete_pairs(study):
            if config["model_id"].split("/")[-1] == args.model:
                raise ValueError("judge must differ from generator checkpoint")
            for order in (0, 1):
                left, right = runs[::-1] if order else runs
                prompt = judge_prompt(item["seed"], left["final"], right["final"])
                tasks.append({"trial_id": f"{study.name}-{item['id']}-r{replicate:02d}-o{order}",
                    "generator": study.name, "prompt_id": item["id"], "replicate": replicate,
                    "a_phase": "on" if order else "off", "input_sha256": [digest(p) for p in paths],
                    "prompt": prompt, "budget": cost_ceiling(prompt, args.max_tokens)})
    source = source_receipt()
    for path in (Path(__file__), ROOT / "experiments/analyze_frontier_study.py"):
        source["files"][str(path.relative_to(ROOT))] = digest(path)
    config = {"contract": "frontier-api-blind-review-1.0", "source": source,
        "studies": identities, "judge_model": args.model, "endpoint": ENDPOINT,
        "max_tokens": args.max_tokens, "reasoning_effort": "low", "temperature": None,
        "orders": ["off_on", "on_off"], "system_sha256": sha_text(JUDGE_SYSTEM),
        "concurrency": args.concurrency, "timeout_seconds": args.timeout,
        "max_retries": 0, "store": False, "service_tier": "default", "pricing": PRICING,
        "prompt_cache_options": {"ttl": "30m"},
        "planned": len(tasks), "budget_usd": args.budget_usd,
        "plan_usd_bound": sum(t["budget"]["usd_bound"] for t in tasks),
        "task_sha256": canonical(tasks), "request_format": "Responses instructions + user input; unstructured JSON-only prompt",
        "claim_limit": "same passages and rubric; provider, model, rendering, reasoning and sampling differ; model judgment is not human gold"}
    if not tasks:
        raise ValueError("no complete source pairs")
    if not math.isfinite(args.budget_usd) or args.budget_usd <= 0 or args.max_tokens < 16:
        raise ValueError("invalid budget or output allowance")
    if config["plan_usd_bound"] > args.budget_usd:
        raise ValueError(f"planned bound ${config['plan_usd_bound']:.2f} exceeds budget ${args.budget_usd:.2f}")
    return config, tasks


def response_record(response, prompt: str) -> dict:
    raw = response.model_dump(mode="json")
    usage = raw.get("usage") or {}
    record = {"status": "unknown", "api": {key: raw.get(key) for key in
        ("id", "model", "status", "created_at", "incomplete_details", "service_tier")},
        "usage": {**usage, "prompt_sha256": sha_text(prompt)},
        "request_id": getattr(response, "_request_id", None)}
    # Do not save reasoning items, encrypted state, or incomplete output text.
    if raw.get("status") != "completed":
        record["error_type"] = "response_not_completed"
        return record
    items = [item for item in raw.get("output", []) if item.get("type") == "message"]
    if len(items) != 1 or items[0].get("status") != "completed" or items[0].get("role") != "assistant":
        record["error_type"] = "invalid_final_message"
        return record
    content = items[0].get("content", [])
    if not content or any(item.get("type") != "output_text" for item in content):
        record["error_type"] = "refused_or_nontext_final"
        return record
    text = "\n".join(item["text"] for item in content).strip()
    record["response"] = text
    try:
        data = json.loads(text)
        if not isinstance(data, dict) or any(data.get(key) not in ("A", "B", "tie") for key in CATEGORIES):
            raise ValueError("category")
        if not isinstance(data.get("reason"), str) or not data["reason"].strip():
            raise ValueError("reason")
        record.update(status="complete", judgment=data)
    except (ValueError, TypeError):
        record["error_type"] = "invalid_judgment_json"
    return record


def execute_one(client, task: dict, output: Path, config: dict, config_sha: str) -> dict:
    trial = task["trial_id"]
    path = output / "judgments" / f"{trial}.json"
    spec = {key: task[key] for key in ("generator", "prompt_id", "replicate", "a_phase", "input_sha256")}
    spec["config_sha256"] = config_sha
    if path.exists():
        prior = json.loads(path.read_text())
        if prior["study"] != spec:
            raise ValueError("existing judgment identity mismatch")
        return prior
    issued = output / "issued" / f"{trial}.json"
    if issued.exists():
        raise ValueError("request outcome unobserved; refusing automatic resend")
    payload = request_payload(config["judge_model"], task["prompt"], config["max_tokens"])
    client_id = canonical({"config": config_sha, "trial": trial})
    save(issued, {"study": spec, "client_request_id": client_id, "payload_sha256": canonical(payload),
                  "prompt_sha256": sha_text(task["prompt"]), "budget": task["budget"]})
    started = time.monotonic()
    try:
        response = client.responses.create(**payload, extra_headers={"X-Client-Request-Id": client_id})
        record = response_record(response, task["prompt"])
        observed = record["usage"]
        if observed.get("input_tokens", 0) > task["budget"]["input_token_bound"]:
            record.update(status="unknown", error_type="input_budget_bound_exceeded")
        if observed.get("output_tokens", 0) > config["max_tokens"]:
            record.update(status="unknown", error_type="output_budget_bound_exceeded")
    except Exception as exc:
        # Error strings can include request bodies or credentials. Persist only
        # transport classifications and provider request IDs, never exception text.
        record = {"status": "unknown", "error_type": type(exc).__name__,
                  "http_status": getattr(exc, "status_code", None),
                  "request_id": getattr(exc, "request_id", None)}
    record.update(study=spec, wall_seconds=time.monotonic() - started, client_request_id=client_id)
    if record["status"] == "complete":
        winner = record["judgment"]["winner"]
        record["preferred_phase"] = ("tie" if winner == "tie" else spec["a_phase"] if winner == "A"
                                     else "on" if spec["a_phase"] == "off" else "off")
    save(path, record)
    return record


def run(args, client_factory=None) -> dict:
    config, tasks = prepare(args)
    if args.plan_only:
        print(json.dumps({key: config[key] for key in ("judge_model", "planned", "plan_usd_bound", "budget_usd")}, indent=2))
        return config
    # Lock the whole evidence directory. Issued markers cover process death
    # between remote acceptance and local completion; they never authorize retry.
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "execution.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        config_sha = frozen(args.output / "frozen.json", config)
        if (args.output / "manifest.json").exists():
            verify_manifest(args.output)
        if client_factory is None:
            from openai import OpenAI
            client_factory = lambda: OpenAI(api_key=os.environ["OPENAI_API_KEY"], base_url=ENDPOINT,
                                            max_retries=0, timeout=args.timeout)
        runtime = {"python": sys.version, "executable": sys.executable, "versions": {"openai": version("openai")}}
        frozen(args.output / "runtime.json", runtime)
        # Detect ambiguous requests before even constructing a network client.
        for task in tasks:
            name = task["trial_id"] + ".json"
            if (args.output / "issued" / name).exists() and not (args.output / "judgments" / name).exists():
                raise ValueError("request outcome unobserved; inspect issued receipt, do not resend")
        client = client_factory()
        try:
            remaining = [task for task in tasks if not (args.output / "judgments" / (task["trial_id"] + ".json")).exists()]
            if args.limit is not None:
                remaining = remaining[:args.limit]
            state(args.output, "judging", planned=len(tasks), admitted_this_invocation=len(remaining))
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                for index, record in enumerate(pool.map(lambda task: execute_one(client, task, args.output, config, config_sha), remaining)):
                    if (index + 1) % 8 == 0:
                        state(args.output, "judging", planned=len(tasks), finished_this_invocation=index + 1)
            records = [json.loads(path.read_text()) for path in (args.output / "judgments").glob("*.json")]
            counts = collections.Counter(record["status"] for record in records)
            complete = len(records) == len(tasks)
            usage = collections.Counter()
            for record in records:
                for key in ("input_tokens", "output_tokens", "total_tokens"):
                    usage[key] += (record.get("usage") or {}).get(key, 0)
            state(args.output, "complete" if complete else "partial", planned=len(tasks), attempted=len(records),
                  completed=counts["complete"], unknown=counts["unknown"], usage=dict(usage))
            return {"attempted": len(records), "usage": dict(usage)}
        finally:
            client.close()
            save_manifest(args.output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--studies", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gpt-6-astra", choices=("gpt-6-astra",))
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--budget-usd", type=float, default=30)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.concurrency <= 8 or args.timeout <= 0 or (args.limit is not None and args.limit < 1):
        parser.error("invalid execution limits")
    run(args)


if __name__ == "__main__":
    main()
