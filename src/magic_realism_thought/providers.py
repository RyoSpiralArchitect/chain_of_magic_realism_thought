from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple

from .types import ChatRequest, ChatResult, ProviderError
from .utils import extract_content_text, first_env, to_plain_dict

class BaseProvider(ABC):
    name: str = "base"
    env_names: Tuple[str, ...] = ()

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or first_env(self.env_names)

    def require_api_key(self) -> str:
        if not self.api_key:
            env_hint = " or ".join(self.env_names) or "the provider API key"
            raise ProviderError(f"{self.name}: API key is missing. Set {env_hint}.")
        return self.api_key

    @abstractmethod
    def generate(self, request: ChatRequest) -> ChatResult:
        raise NotImplementedError


class OpenAIProvider(BaseProvider):
    name = "openai"
    env_names = ("OPENAI_API_KEY",)

    def __init__(self, api_key: Optional[str] = None) -> None:
        super().__init__(api_key)
        api_key = self.require_api_key()
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:
            raise ProviderError("openai: install the SDK with `pip install openai`.") from exc
        self.client = OpenAI(api_key=api_key)

    def generate(self, request: ChatRequest) -> ChatResult:
        payload: Dict[str, Any] = {
            "model": request.model,
            "input": request.prompt,
            "max_output_tokens": request.max_tokens,
        }
        if request.system:
            payload["instructions"] = request.system
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        response = self.client.responses.create(**payload)
        text = getattr(response, "output_text", None) or self._extract_text(response)
        return ChatResult(
            provider=self.name,
            model=request.model,
            text=text.strip(),
            usage=to_plain_dict(getattr(response, "usage", None)),
        )

    @staticmethod
    def _extract_text(response: Any) -> str:
        chunks: List[str] = []
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                text = getattr(content, "text", None)
                if text:
                    chunks.append(str(text))
        return "\n".join(chunks)


class GoogleProvider(BaseProvider):
    name = "google"
    env_names = ("GEMINI_API_KEY", "GOOGLE_API_KEY")

    def __init__(self, api_key: Optional[str] = None) -> None:
        super().__init__(api_key)
        api_key = self.require_api_key()
        try:
            from google import genai  # type: ignore
            from google.genai import types  # type: ignore
        except ImportError as exc:
            raise ProviderError("google: install the SDK with `pip install google-genai`.") from exc
        self.client = genai.Client(api_key=api_key)
        self.types = types

    def generate(self, request: ChatRequest) -> ChatResult:
        config_kwargs: Dict[str, Any] = {"max_output_tokens": request.max_tokens}
        if request.system:
            config_kwargs["system_instruction"] = request.system
        if request.temperature is not None:
            config_kwargs["temperature"] = request.temperature

        config = self.types.GenerateContentConfig(**config_kwargs)
        response = self.client.models.generate_content(
            model=request.model,
            contents=request.prompt,
            config=config,
        )
        text = getattr(response, "text", None) or self._extract_text(response)
        return ChatResult(
            provider=self.name,
            model=request.model,
            text=text.strip(),
            usage=to_plain_dict(getattr(response, "usage_metadata", None)),
        )

    @staticmethod
    def _extract_text(response: Any) -> str:
        chunks: List[str] = []
        for cand in getattr(response, "candidates", []) or []:
            content = getattr(cand, "content", None)
            for part in getattr(content, "parts", []) or []:
                text = getattr(part, "text", None)
                if text:
                    chunks.append(str(text))
        return "\n".join(chunks)


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    env_names = ("ANTHROPIC_API_KEY",)

    def __init__(self, api_key: Optional[str] = None) -> None:
        super().__init__(api_key)
        api_key = self.require_api_key()
        try:
            import anthropic  # type: ignore
        except ImportError as exc:
            raise ProviderError("anthropic: install the SDK with `pip install anthropic`.") from exc
        self.client = anthropic.Anthropic(api_key=api_key)

    def generate(self, request: ChatRequest) -> ChatResult:
        payload: Dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if request.system:
            payload["system"] = request.system
        # Claude Opus 4.7 removed non-default sampling parameters; omit
        # temperature for that model alias unless users choose another model.
        if request.temperature is not None and "claude-opus-4-7" not in request.model:
            payload["temperature"] = request.temperature

        message = self.client.messages.create(**payload)
        text = extract_content_text(getattr(message, "content", None))
        return ChatResult(
            provider=self.name,
            model=request.model,
            text=text.strip(),
            usage=to_plain_dict(getattr(message, "usage", None)),
        )


class MistralProvider(BaseProvider):
    name = "mistral"
    env_names = ("MISTRAL_API_KEY",)

    def __init__(self, api_key: Optional[str] = None) -> None:
        super().__init__(api_key)
        api_key = self.require_api_key()
        try:
            try:
                from mistralai import Mistral  # type: ignore
            except ImportError:
                from mistralai.client import Mistral  # type: ignore
        except ImportError as exc:
            raise ProviderError("mistral: install the SDK with `pip install mistralai`.") from exc
        self.client = Mistral(api_key=api_key)

    def generate(self, request: ChatRequest) -> ChatResult:
        messages: List[Dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})

        payload: Dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_tokens,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        response = self.client.chat.complete(**payload)
        choices = getattr(response, "choices", []) or []
        if not choices:
            text = ""
        else:
            message = getattr(choices[0], "message", None)
            text = extract_content_text(getattr(message, "content", None))
        return ChatResult(
            provider=self.name,
            model=request.model,
            text=text.strip(),
            usage=to_plain_dict(getattr(response, "usage", None)),
        )


class DryRunProvider(BaseProvider):
    """Deterministic fake provider for CLI testing without SDKs or API keys."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.api_key = "dry-run"

    def generate(self, request: ChatRequest) -> ChatResult:
        stage_name = "stage"
        role = "role"
        variant = "1"
        match = re.search(r"Stage:\s*(.+)", request.prompt)
        if match:
            stage_name = match.group(1).strip()[:60]
        role_match = re.search(r"Role:\s*(.+)", request.prompt)
        if role_match:
            role = role_match.group(1).strip()[:40]
        variant_match = re.search(r"Candidate variant:\s*(\d+)", request.prompt)
        if variant_match:
            variant = variant_match.group(1)
        seed_match = re.search(r"(?:Original seed|Seed):\s*(.+?)(?:\n\n|$)", request.prompt, flags=re.S)
        seed = " ".join(seed_match.group(1).split())[:80] if seed_match else "Seed"

        suffixes = {
            "1": "。",
            "2": "。その音は、誰かが戸棚の奥で紙を折る音に似ていた。",
            "3": "。灯りの下だけ、時間は乾かないまま残っていた。",
            "4": "。私はそれを見ずに、見たこととして覚えた。",
        }
        tail = suffixes.get(variant, "。")

        by_role = {
            "grounder": (
                f"{seed} 夕方の台所には、洗った米の匂いと古い木箱の湿り気があった。"
                "窓の外で雨が細く降り、畳の縁だけが暗くなっていた。"
                "祖母の使っていた硯箱は食器棚の下に残り、誰もそれを捨てなかった"
            ),
            "expander": (
                "雨粒が障子に触れるたび、薄い墨の線がひとつずつ浮かんだ。"
                "家族はそれを雨漏りの癖のように扱い、茶碗を伏せて夕飯を続けた。"
                "線は祖母の丸い払いに似ていたが、誰も名前を呼ばなかった"
            ),
            "symbolizer": (
                "雨、硯箱、止まった時計が、同じ小さな音で部屋を回った。"
                "雨は筆跡になり、筆跡は湯気になり、湯気はまた窓へ戻った。"
                "祖母の不在だけが、濡れた紙の白さとして何度も現れた"
            ),
            "stabilizer": (
                "母はその夜も台所に立ち、私は障子の前で濡れた文字を読まないふりをした。"
                "時計は三時十七分で止まっていたが、家の中では夕飯の時間だけが正しく進んだ。"
                "雨の書く線は増えすぎず、祖母の癖だけを静かに残した"
            ),
            "compressor": (
                "雨が降る夜だけ、障子に祖母の筆跡が戻った。"
                "母は茶碗を並べ、私は三時十七分で止まった時計を見ないようにした。"
                "墨の線は説明を求めず、湯気の中でほどけ、翌朝にはただ畳の縁が少し黒くなっていた"
            ),
            "integrator": (
                "雨が降る夜、障子には祖母の筆跡が戻った。夕飯の匂い、止まった時計、"
                "硯箱の湿り気がひとつの部屋に集まり、誰もそれを奇跡とは呼ばなかった。"
                "母は茶碗を伏せ、私は読めそうで読めない線を見ていた。"
                "朝になると文字は消え、畳の縁だけが、墨を吸ったように少し暗かった"
            ),
            "recursive": (
                "雨が降ると、祖母の筆跡は障子ではなく家そのものに戻ってきた。"
                "三時十七分の時計、湯気の立つ茶碗、硯箱の匂いが、黙ったまま同じ線を描いた。"
                "朝、私は乾いた畳を指でなぞり、雨がまだ祖母の筆跡を覚えていることを知った"
            ),
        }
        text = by_role.get(role, by_role.get("expander", seed)) + tail
        if "Process Reward Evaluator" in request.system or "Return JSON" in request.prompt:
            # Minimal judge response for dry-run LLM judge mode.
            text = json.dumps(
                {
                    "score": 0.78,
                    "metric_scores": {
                        "grounding": 0.76,
                        "drift_control": 0.82,
                        "symbol_recurrence": 0.72,
                        "novelty": 0.68,
                        "integration": 0.74,
                        "collapse_control": 0.88,
                    },
                    "reasons": ["dry-run visible transition is coherent"],
                    "repairable": False,
                    "repair_prompt": None,
                },
                ensure_ascii=False,
            )
        return ChatResult(provider=self.name, model=request.model, text=text, usage={"dry_run": True, "stage": stage_name})


def build_provider(name: str, dry_run: bool = False) -> BaseProvider:
    if dry_run:
        return DryRunProvider(name)
    if name == "openai":
        return OpenAIProvider()
    if name == "google":
        return GoogleProvider()
    if name == "anthropic":
        return AnthropicProvider()
    if name == "mistral":
        return MistralProvider()
    raise ProviderError(f"Unknown provider: {name}")
