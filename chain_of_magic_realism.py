#!/usr/bin/env python3
"""
chain_of_magic_realism.py

Chain of Magic Realism Thought packaging for the Spiral RPM-PRM Harness V5.

V5 extends V4 by adding beam search and run-to-run memory on top of PRM-style visible process supervision with RPM-style
state-matrix reasoning:

- provider abstraction: OpenAI, Google Gemini, Anthropic Claude, Mistral
- explicit ChainState: text, symbols, constraints, metrics, control notes
- candidate generation per stage: best-of-N instead of a single linear rewrite
- PRM scoring: heuristic, LLM judge, or hybrid process reward models
- selection pressure: accept the strongest visible state transition
- repair loop: low-reward steps can be rewritten and rescored
- trace output: accepted path, rejected candidates, rewards, metrics, repairs
- beam search: keep top-k visible state paths instead of committing to one path immediately
- run memory: update a JSON profile of provider/role, operator, stage, and symbol performance
- RPM matrix trace: each accepted transition becomes a matrix cell
- rule hypotheses: symbols and operators are converted into explicit visible rules
- conflict detection: drift, collapse, symbol loss, repetition, and operator mismatch
- aggregation and recursive closure remain explicit final stages

This script never asks a model to reveal private chain-of-thought. It treats
visible stage outputs as process steps, scores those visible transitions, and
uses the score to choose or repair the next state.

Examples:

  python chain_of_magic_realism.py \
    --dry-run \
    --providers openai,google,anthropic,mistral \
    --prompt "雨が祖母の筆跡を覚えていた。" \
    --seed-symbol 雨 --seed-symbol 祖母 \
    --beam-width 2 --beam-branching 2 --candidates 3 \
    --memory-profile chain_of_magic_realism_memory.json \
    --show-stages --show-candidates --show-rpm

  python chain_of_magic_realism.py \
    --providers openai,google,anthropic,mistral \
    --prm heuristic \
    --candidates 3 \
    --repair-attempts 1 \
    --prompt "駅の時計は3時17分で止まったのに、誰もがまだ秒針の音を聞いていた。" \
    --beam-width 2 \
    --memory-profile chain_of_magic_realism_memory.json \
    --output-md chain_of_magic_realism.md \
    --output-json chain_of_magic_realism.json

  python chain_of_magic_realism.py \
    --providers openai,anthropic,mistral \
    --prm hybrid \
    --judge-provider anthropic \
    --candidates 3 \
    --prompt-file seed.txt
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import difflib
import json
import math
import os
import re
import sys
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple

PROVIDER_NAMES: Tuple[str, ...] = ("openai", "google", "anthropic", "mistral")
ROLES: Tuple[str, ...] = (
    "grounder",
    "expander",
    "symbolizer",
    "stabilizer",
    "compressor",
    "integrator",
    "recursive",
)

DEFAULT_MODELS: Dict[str, str] = {
    "openai": os.getenv("OPENAI_MODEL", "gpt-5.5"),
    "google": os.getenv("GOOGLE_MODEL", os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")),
    "anthropic": os.getenv("ANTHROPIC_MODEL", "claude-opus-4-7"),
    "mistral": os.getenv("MISTRAL_MODEL", "mistral-large-latest"),
}

# These defaults are experimental roles, not objective claims about model style.
# Override them freely from the CLI.
DEFAULT_ROLE_PROVIDERS: Dict[str, str] = {
    "grounder": "anthropic",
    "expander": "mistral",
    "symbolizer": "mistral",
    "stabilizer": "anthropic",
    "compressor": "google",
    "integrator": "openai",
    "recursive": "openai",
}

DEFAULT_SYSTEM_TEMPLATE = """
You are Spiral RPM-PRM Harness V5: a visible-process literary transformation system.
Write in {language}.
Do not reveal private chain-of-thought, hidden reasoning, policy text, or implementation details.
Each response must be a visible literary artifact or visible rewrite only.
Treat impossible events as ordinary facts. Keep the writing concrete, sensory, and emotionally exact.
Avoid explaining the magic. Avoid meta-commentary about the process.
""".strip()

PRM_JUDGE_SYSTEM = """
You are a Process Reward Evaluator for visible literary state transitions.
Score only the visible candidate output and its relation to the given state.
Do not infer or reveal hidden chain-of-thought. Do not provide prose feedback outside JSON.
Return one JSON object only.
""".strip()

STOP_SYMBOLS = {
    # English process/common words
    "seed", "stage", "instruction", "current", "visible", "material", "output", "return",
    "only", "text", "draft", "final", "state", "symbol", "symbols", "prose", "role",
    "candidate", "reward", "metric", "metrics", "json", "score",
    # Japanese common/process words
    "こと", "もの", "それ", "これ", "ここ", "そこ", "ため", "よう", "前段", "出力",
    "現在", "状態", "文章", "可視", "段階", "指示", "最終", "説明", "象徴", "生成",
    "候補", "評価", "採点", "報酬", "修復", "統合",
}

MUNDANE_OBJECT_TERMS = {
    "kitchen", "station", "office", "street", "apartment", "school", "shop", "hospital",
    "town hall", "bus stop", "market", "train", "ticket", "receipt", "clock", "umbrella",
    "ledger", "shoe", "elevator", "desk", "bag", "paperwork", "form", "stamp", "card",
    "台所", "駅", "会社", "職場", "団地", "商店街", "学校", "病院", "市役所", "役所",
    "バス停", "市場", "電車", "改札", "切符", "領収書", "時計", "傘", "帳簿",
    "靴", "エレベーター", "机", "鞄", "書類", "申請書", "用紙", "印鑑", "社員証",
    "タイムカード", "弁当", "財布", "鍵", "玄関", "廊下", "窓口", "レジ", "伝票",
}
SOCIAL_NORMALIZATION_TERMS = {
    "clerk", "office", "rule", "notice", "custom", "queue", "counter", "procedure",
    "usual", "habit", "quietly", "adapt", "form", "staff",
    "職員", "係", "店員", "駅員", "窓口", "規則", "貼り紙", "習慣", "手続き",
    "番号札", "順番", "控え", "訂正", "印鑑", "予備", "誰も", "いつも", "普通",
}
IMPOSSIBLE_FACT_TERMS = {
    "impossible", "unreal", "remembered", "forgot", "vanished", "appeared", "wrong floor",
    "ありえない", "存在しない", "覚えて", "忘れず", "浮か", "消え", "戻っ", "ずれ",
    "伸び", "ほどけ", "通過", "違う階", "知らない", "勝手に", "昨日の声", "名前を",
}
EXPLANATION_TERMS = {
    "because", "therefore", "it meant", "the reason", "magic system", "spell", "supernatural",
    "dream", "hallucination",
    "なぜなら", "理由", "つまり", "要するに", "これは", "意味していた", "魔法体系",
    "超常現象", "夢だった", "幻覚", "啓示", "救済", "慰め",
}
FANTASY_LORE_TERMS = {
    "wizard", "spell", "portal", "chosen one", "prophecy", "kingdom", "dragon", "elf",
    "魔法使い", "呪文", "異世界", "転生", "選ばれし", "勇者", "魔王", "王国",
    "予言", "精霊", "妖精", "ドラゴン",
}
DREAM_REVEAL_TERMS = {
    "it was a dream", "woke up", "hallucination", "delusion",
    "夢だった", "目が覚め", "幻覚だった", "妄想", "白昼夢",
}
COSMIC_EXPLANATION_TERMS = {
    "cosmic", "universe", "dimension", "god", "myth", "destiny",
    "宇宙", "次元", "神々", "神話", "運命", "世界の真理", "根源", "預言",
}
PURPLE_ABSTRACTION_TERMS = {
    "soul", "eternity", "infinite", "destiny", "void", "absolute",
    "魂", "永遠", "無限", "運命", "虚無", "絶対", "深淵", "宿命", "概念", "真理",
}
ORDINARY_CONTINUITY_TERMS = {
    "then", "afterward", "continued", "went", "returned", "paid", "wrote", "opened",
    "その後", "それから", "続け", "戻", "行っ", "払", "書き直", "押し", "閉め",
    "開け", "並び", "待ち", "仕事", "通勤", "帰り", "昼休み", "退勤",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


class ProviderError(RuntimeError):
    """Raised when a provider cannot be initialized or called."""


@dataclass(frozen=True)
class StageSpec:
    name: str
    role: str
    instruction: str
    operator: str = ""


DEFAULT_STAGES: Tuple[StageSpec, ...] = (
    StageSpec(
        name="現実の足場",
        role="grounder",
        operator="increase_grounding_and_stabilize_viewpoint",
        instruction=(
            "Seedを、手触り・音・匂い・場所・時間がわかる小さな現実の場面へ変換する。"
            "まだ魔法を大きくしすぎない。語り手・視点・季節を安定させる。6〜10文。"
        ),
    ),
    StageSpec(
        name="摂動：ありえない事実",
        role="expander",
        operator="inject_one_impossible_fact_without_explanation",
        instruction=(
            "前段の場面に、ただ一つの不可能な出来事を日常的な口調で混ぜる。"
            "登場人物は驚きすぎず、生活の一部として扱う。因果を説明しない。6〜10文。"
        ),
    ),
    StageSpec(
        name="象徴の反復",
        role="symbolizer",
        operator="amplify_symbolic_recurrence_by_variation",
        instruction=(
            "状態に記録されたsymbolsから1〜3個を選び、記憶・喪失・予感の回路として反復させる。"
            "同じ語を機械的に連呼せず、形・音・動作を変えながら戻す。8〜12文。"
        ),
    ),
    StageSpec(
        name="安定化：語りの重力",
        role="stabilizer",
        operator="reduce_drift_while_preserving_magic",
        instruction=(
            "前段までの美しいズレを残しながら、語り手・時制・場所・人物関係の破綻を減らす。"
            "過剰な比喩と説明を落とし、読者が立てる床を一枚戻す。8〜12文。"
        ),
    ),
    StageSpec(
        name="圧縮：骨格を残す",
        role="compressor",
        operator="compress_to_dense_visible_bone_structure",
        instruction=(
            "場面の核・反復象徴・不可能な事実だけを残し、短編冒頭として強い骨格へ圧縮する。"
            "要約ではなく、密度の高い可視稿として書く。350〜700字程度。"
        ),
    ),
)


SEED_INDEPENDENT_MAGIC_STAGES: Tuple[StageSpec, ...] = (
    StageSpec(
        name="日常アンカー抽出",
        role="grounder",
        operator="mundane_anchor_extraction",
        instruction=(
            "入力から、日常的な場所・物・行為・社会的状況を具体的な場面へ展開する。"
            "魔術的要素はまだ大きく入れない。通勤、家事、書類、食事、近所、職場、駅など、"
            "現実の手触りを優先する。6〜10文。"
        ),
    ),
    StageSpec(
        name="静かな不可能性",
        role="expander",
        operator="quiet_impossibility_injection",
        instruction=(
            "日常の足場を保ったまま、小さな不可能な事実をひとつだけ入れる。"
            "それを魔法、夢、幻覚、比喩、超常現象として説明しない。人物は驚きすぎず、"
            "その事実の処理を続ける。6〜10文。"
        ),
    ),
    StageSpec(
        name="社会的な馴化",
        role="stabilizer",
        operator="social_normalization",
        instruction=(
            "人物や社会が、不可能な事実に少しだけ適応している様子を書く。"
            "驚きよりも、習慣、手続き、貼り紙、沈黙、諦め、窓口対応、近所の作法を使う。"
            "説明ではなく運用を描く。8〜12文。"
        ),
    ),
    StageSpec(
        name="象徴圧の変奏",
        role="symbolizer",
        operator="symbolic_recurrence",
        instruction=(
            "不可能な事実に関係する物・音・色・動作を反復させる。"
            "同じ言葉の反復ではなく、場所や用途を変えた変奏として戻す。"
            "抽象的な意味づけを避け、具体物の挙動で圧力を作る。8〜12文。"
        ),
    ),
    StageSpec(
        name="説明抑制",
        role="compressor",
        operator="explanation_suppression",
        instruction=(
            "超常現象の説明、夢オチ、比喩化、世界設定の説明、感情的な回収を削る。"
            "代わりに具体的な日常描写、手続き、物の扱い、移動、支払い、仕事の続きを増やす。"
            "450〜800字程度。"
        ),
    ),
    StageSpec(
        name="リアリズム修復",
        role="stabilizer",
        operator="realism_repair",
        instruction=(
            "場面がファンタジー、寓話、夢、詩的抽象に寄りすぎていないか修復する。"
            "公共交通、家事、書類、食事、近所付き合い、仕事、天気、物の重さを戻す。"
            "不可能な事実は小さく物質的なまま残す。8〜12文。"
        ),
    ),
)


@dataclass(frozen=True)
class ChatRequest:
    model: str
    system: str
    prompt: str
    temperature: Optional[float]
    max_tokens: int


@dataclass
class ChatResult:
    provider: str
    model: str
    text: str
    usage: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChainConstraints:
    max_drift: float = 0.82
    min_drift: float = 0.18
    max_repetition: float = 0.28
    min_recurrence: float = 0.15
    min_novelty: float = 0.18
    max_collapse: float = 0.55
    required_prefix: Optional[str] = None
    symbol_limit: int = 12


@dataclass(frozen=True)
class MagicRealismPrior:
    mundane_grounding: float = 0.18
    impossible_fact_density: float = 0.16
    explanatory_restraint: float = 0.14
    social_normalization: float = 0.12
    symbolic_recurrence: float = 0.12
    sensory_concreteness: float = 0.12
    ordinary_continuity: float = 0.10
    restraint: float = 0.06
    anti_fantasy_penalty: float = 0.25
    anti_dream_penalty: float = 0.20
    anti_cosmic_explanation_penalty: float = 0.18
    anti_purple_prose_penalty: float = 0.15


@dataclass(frozen=True)
class PromptAnchorProfile:
    mundane_anchors: List[str] = field(default_factory=list)
    social_setting: str = ""
    routine_actions: List[str] = field(default_factory=list)
    ordinary_objects: List[str] = field(default_factory=list)
    emotional_pressure: List[str] = field(default_factory=list)
    impossible_fact_slots: List[str] = field(default_factory=list)


@dataclass
class ProcessReward:
    score: float
    accept: bool
    repairable: bool
    metric_scores: Dict[str, float] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)
    repair_prompt: Optional[str] = None
    judge: str = "heuristic"
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateStep:
    candidate_id: str
    stage_index: int
    stage_name: str
    role: str
    operator: str
    provider: str
    model: str
    output: str
    metrics: Dict[str, float] = field(default_factory=dict)
    symbols_before: List[str] = field(default_factory=list)
    symbols_after: List[str] = field(default_factory=list)
    reward: Optional[ProcessReward] = None
    prompt: Optional[str] = None
    usage: Dict[str, Any] = field(default_factory=dict)
    repaired_from: Optional[str] = None
    repair_attempt: int = 0


@dataclass
class ProcessStepRecord:
    index: int
    name: str
    role: str
    operator: str
    accepted: CandidateStep
    rejected: List[CandidateStep] = field(default_factory=list)
    repaired: List[CandidateStep] = field(default_factory=list)
    control_notes_for_next: List[str] = field(default_factory=list)


@dataclass
class RuleHypothesis:
    rule_id: str
    kind: str
    statement: str
    confidence: float
    support: List[str] = field(default_factory=list)
    stage_indices: List[int] = field(default_factory=list)


@dataclass
class RPMConflict:
    conflict_id: str
    type: str
    severity: float
    description: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    repair_instruction: str = ""
    resolved: bool = False


@dataclass
class RPMRepairPlan:
    conflict_id: str
    stage_index: int
    instruction: str
    applied_by_candidate_id: Optional[str] = None


@dataclass
class RPMCell:
    row_index: int
    stage_name: str
    role: str
    operator: str
    provider: str
    model: str
    candidate_id: str
    status: str
    text_preview: str
    reward_score: Optional[float]
    symbols_before: List[str] = field(default_factory=list)
    symbols_after: List[str] = field(default_factory=list)
    symbols_gained: List[str] = field(default_factory=list)
    symbols_lost: List[str] = field(default_factory=list)
    metrics_before: Dict[str, float] = field(default_factory=dict)
    metrics_after: Dict[str, float] = field(default_factory=dict)
    metric_delta: Dict[str, float] = field(default_factory=dict)
    operator_effects: Dict[str, str] = field(default_factory=dict)
    rule_ids: List[str] = field(default_factory=list)
    conflict_ids: List[str] = field(default_factory=list)


@dataclass
class RPMTrace:
    axes: List[str] = field(default_factory=lambda: [
        "text", "symbols", "constraints", "drift", "recurrence", "reward", "operator"
    ])
    matrix: List[RPMCell] = field(default_factory=list)
    inferred_rules: List[RuleHypothesis] = field(default_factory=list)
    conflicts: List[RPMConflict] = field(default_factory=list)
    repair_plans: List[RPMRepairPlan] = field(default_factory=list)
    stable_symbols: List[str] = field(default_factory=list)
    unstable_symbols: List[str] = field(default_factory=list)
    drift_vector: Dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


@dataclass
class ChainState:
    seed: str
    text: str
    symbols: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    control_notes: List[str] = field(default_factory=list)
    memory_notes: List[str] = field(default_factory=list)
    magic_prior: Optional[MagicRealismPrior] = None
    anchor_profile: Optional[PromptAnchorProfile] = None
    rpm_trace: RPMTrace = field(default_factory=RPMTrace)
    step_history: List[ProcessStepRecord] = field(default_factory=list)
    path_id: str = "root"
    path_score: float = 0.0


@dataclass
class PRMConfig:
    mode: str
    candidates: int
    accept_threshold: float
    repair_threshold: float
    judge_provider: Optional[str]
    judge_model: Optional[str]
    hybrid_llm_weight: float
    include_prompts: bool


@dataclass
class BeamConfig:
    enabled: bool
    beam_width: int
    beam_branching: int
    archive_limit: int


@dataclass
class BeamPathSnapshot:
    path_id: str
    stage_index: int
    score: float
    rewards: List[float]
    providers: List[str]
    symbols: List[str]
    unresolved_conflicts: int
    final_text_preview: str


@dataclass
class ChainRun:
    script: str
    version: str
    started_at_utc: str
    language: str
    seed: str
    providers: List[str]
    routing: str
    role_providers: Dict[str, str]
    models: Dict[str, str]
    constraints: Dict[str, Any]
    magic_prior: Optional[MagicRealismPrior]
    anchor_profile: Optional[PromptAnchorProfile]
    prm: PRMConfig
    beam: BeamConfig
    beam_archive: List[BeamPathSnapshot]
    memory_profile_path: Optional[str]
    memory_profile_before: Dict[str, Any]
    memory_profile_after: Dict[str, Any]
    final: str
    final_state: ChainState
    rpm_trace: RPMTrace
    steps: List[ProcessStepRecord]


# ---------------------------------------------------------------------------
# General utilities
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def first_env(names: Iterable[str]) -> Optional[str]:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def clip_text(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    head = max_chars // 2
    tail = max_chars - head
    return text[:head] + "\n\n...[clipped]...\n\n" + text[-tail:]


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    if dataclasses.is_dataclass(value):
        return json_safe(dataclasses.asdict(value))
    if hasattr(value, "model_dump"):
        try:
            return json_safe(value.model_dump())
        except Exception:
            pass
    return repr(value)


def to_plain_dict(obj: Any) -> Dict[str, Any]:
    """Best-effort conversion of SDK usage objects into JSON-safe dictionaries."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return json_safe(obj)
    if hasattr(obj, "model_dump"):
        try:
            return json_safe(obj.model_dump())
        except Exception:
            pass
    if dataclasses.is_dataclass(obj):
        try:
            return json_safe(dataclasses.asdict(obj))
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        try:
            return json_safe({k: v for k, v in vars(obj).items() if not k.startswith("_")})
        except Exception:
            pass
    return {"repr": repr(obj)}



# ---------------------------------------------------------------------------
# Run memory profile
# ---------------------------------------------------------------------------


def empty_memory_profile() -> Dict[str, Any]:
    return {
        "version": "5-memory-1.0",
        "created_at_utc": utc_now_iso(),
        "updated_at_utc": utc_now_iso(),
        "run_count": 0,
        "provider_role_scores": {},
        "stage_scores": {},
        "operator_scores": {},
        "symbol_scores": {},
        "notes": [],
    }


def load_memory_profile(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return empty_memory_profile()
    profile_path = Path(path)
    if not profile_path.exists():
        return empty_memory_profile()
    try:
        data = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Could not read memory profile {path!r}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Memory profile {path!r} must contain a JSON object.")
    base = empty_memory_profile()
    base.update(data)
    return base


def save_memory_profile(path: Optional[str], profile: Dict[str, Any]) -> None:
    if not path:
        return
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(json_safe(profile), ensure_ascii=False, indent=2), encoding="utf-8")


def update_mean_stat(bucket: Dict[str, Any], key: str, value: float, extra: Optional[Dict[str, Any]] = None) -> None:
    rec = bucket.setdefault(key, {"count": 0, "mean_reward": 0.0})
    count = int(rec.get("count", 0)) + 1
    prior = float(rec.get("mean_reward", 0.0))
    rec["count"] = count
    rec["mean_reward"] = round(prior + (float(value) - prior) / count, 5)
    if extra:
        for k, v in extra.items():
            rec[k] = v


def profile_snapshot(profile: Dict[str, Any], limit: int = 8) -> Dict[str, Any]:
    def top_items(bucket_name: str) -> List[Dict[str, Any]]:
        bucket = profile.get(bucket_name, {})
        if not isinstance(bucket, dict):
            return []
        items = []
        for key, rec in bucket.items():
            if isinstance(rec, dict):
                items.append({"key": key, **{k: rec.get(k) for k in ("count", "mean_reward") if k in rec}})
        return sorted(items, key=lambda x: (float(x.get("mean_reward") or 0.0), int(x.get("count") or 0)), reverse=True)[:limit]

    provider_roles: List[Dict[str, Any]] = []
    raw_provider_roles = profile.get("provider_role_scores", {})
    if isinstance(raw_provider_roles, dict):
        for role, provider_bucket in raw_provider_roles.items():
            if not isinstance(provider_bucket, dict):
                continue
            for provider, rec in provider_bucket.items():
                if isinstance(rec, dict):
                    provider_roles.append({
                        "role": role,
                        "provider": provider,
                        "count": rec.get("count", 0),
                        "mean_reward": rec.get("mean_reward", 0.0),
                    })
    provider_roles = sorted(provider_roles, key=lambda x: (float(x.get("mean_reward") or 0.0), int(x.get("count") or 0)), reverse=True)[:limit]
    return {
        "version": profile.get("version"),
        "run_count": profile.get("run_count", 0),
        "updated_at_utc": profile.get("updated_at_utc"),
        "top_provider_roles": provider_roles,
        "top_stages": top_items("stage_scores"),
        "top_operators": top_items("operator_scores"),
        "top_symbols": top_items("symbol_scores"),
    }


def best_memory_provider_for_role(profile: Dict[str, Any], role: str, available: Sequence[str], min_count: int = 1) -> Optional[str]:
    role_bucket = profile.get("provider_role_scores", {}).get(role, {}) if isinstance(profile.get("provider_role_scores"), dict) else {}
    if not isinstance(role_bucket, dict):
        return None
    best: Optional[Tuple[float, int, str]] = None
    for provider in available:
        rec = role_bucket.get(provider)
        if not isinstance(rec, dict):
            continue
        count = int(rec.get("count", 0))
        if count < min_count:
            continue
        score = float(rec.get("mean_reward", 0.0))
        item = (score, count, provider)
        if best is None or item > best:
            best = item
    return best[2] if best else None


def format_memory_context(profile: Dict[str, Any], role: str, available_providers: Sequence[str], memory_weight: float, max_lines: int = 8) -> str:
    if not profile or int(profile.get("run_count", 0) or 0) <= 0 or memory_weight <= 0:
        return "No prior run memory is active for this stage."
    lines: List[str] = []
    preferred = best_memory_provider_for_role(profile, role, available_providers)
    if preferred:
        rec = profile.get("provider_role_scores", {}).get(role, {}).get(preferred, {})
        lines.append(f"Memory-preferred provider for role {role!r}: {preferred} (mean_reward={rec.get('mean_reward')}, count={rec.get('count')}).")
    snapshot = profile_snapshot(profile, limit=5)
    if snapshot.get("top_symbols"):
        syms = ", ".join(f"{x['key']}:{x.get('mean_reward')}" for x in snapshot["top_symbols"][:5])
        lines.append("Previously stable/rewarded symbols: " + syms)
    if snapshot.get("top_operators"):
        ops = ", ".join(f"{x['key']}:{x.get('mean_reward')}" for x in snapshot["top_operators"][:4])
        lines.append("Previously strong operators: " + ops)
    if snapshot.get("top_provider_roles"):
        prs = ", ".join(f"{x['role']}/{x['provider']}:{x.get('mean_reward')}" for x in snapshot["top_provider_roles"][:4])
        lines.append("Provider-role memory: " + prs)
    lines.append(f"Memory weight: {memory_weight:.2f}; treat this as a soft prior, not a hard rule.")
    return "\n".join(lines[:max_lines])


def update_memory_profile_from_run(profile: Dict[str, Any], run: "ChainRun") -> Dict[str, Any]:
    profile = json_safe(profile)
    profile.setdefault("version", "5-memory-1.0")
    profile.setdefault("created_at_utc", utc_now_iso())
    profile["updated_at_utc"] = utc_now_iso()
    profile["run_count"] = int(profile.get("run_count", 0) or 0) + 1
    provider_role_scores = profile.setdefault("provider_role_scores", {})
    stage_scores = profile.setdefault("stage_scores", {})
    operator_scores = profile.setdefault("operator_scores", {})
    symbol_scores = profile.setdefault("symbol_scores", {})

    for step in run.steps:
        cand = step.accepted
        reward = cand.reward.score if cand.reward else 0.0
        role_bucket = provider_role_scores.setdefault(step.role, {})
        update_mean_stat(role_bucket, cand.provider, reward, extra={"last_model": cand.model})
        update_mean_stat(stage_scores, step.name, reward, extra={"last_role": step.role})
        update_mean_stat(operator_scores, step.operator or step.role, reward, extra={"last_role": step.role})
        for sym in cand.symbols_after[:10]:
            update_mean_stat(symbol_scores, sym, reward, extra={"last_seen_stage": step.name})

    notes = profile.setdefault("notes", [])
    if isinstance(notes, list):
        notes.append(
            f"run {profile['run_count']}: mean_reward={sum((s.accepted.reward.score if s.accepted.reward else 0.0) for s in run.steps)/max(1,len(run.steps)):.4f}; final_symbols={', '.join(run.final_state.symbols[:6])}"
        )
        profile["notes"] = notes[-25:]
    return profile


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    return numerator / denominator if denominator else default


def extract_content_text(content: Any) -> str:
    """Extract text from common SDK content shapes."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            text = getattr(item, "text", None)
            if text:
                parts.append(str(text))
                continue
            if isinstance(item, dict):
                if item.get("type") in ("text", "output_text") and item.get("text"):
                    parts.append(str(item["text"]))
                elif item.get("content"):
                    parts.append(extract_content_text(item["content"]))
        return "\n".join(p for p in parts if p)
    text = getattr(content, "text", None)
    if text:
        return str(text)
    return str(content)


def extract_json_object(text: str) -> Dict[str, Any]:
    """Parse the first JSON object found in a model response."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        value = json.loads(stripped)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", stripped, flags=re.S)
    if not match:
        raise ValueError("No JSON object found in judge response.")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("Judge JSON must be an object.")
    return value


# ---------------------------------------------------------------------------
# Provider adapters
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------


TOKEN_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9_'-]*|[0-9]+(?:\.[0-9]+)?|[一-龯々〆ヵヶ]{2,}|[ァ-ヴー]{2,}|[ぁ-ゖ]{2,}",
    re.UNICODE,
)
QUOTE_RE = re.compile(r"[「『\"']([^」』\"']{1,16})[」』\"']")


def normalize_for_similarity(text: str, max_chars: int = 6000) -> str:
    text = re.sub(r"\s+", "", text)
    return text[:max_chars]


def tokenize_text(text: str) -> List[str]:
    tokens = [m.group(0).lower() for m in TOKEN_RE.finditer(text)]
    return [t for t in tokens if t and t not in STOP_SYMBOLS]


def char_ngrams(text: str, n: int = 3, limit: int = 2500) -> List[str]:
    clean = normalize_for_similarity(text, max_chars=limit)
    if not clean:
        return []
    if len(clean) <= n:
        return [clean]
    return [clean[i : i + n] for i in range(0, len(clean) - n + 1)]


def metric_units(text: str) -> List[str]:
    tokens = tokenize_text(text)
    if len(tokens) < 12:
        tokens.extend(char_ngrams(text, n=3, limit=1200))
    return tokens


def shannon_entropy_score(units: Sequence[str]) -> float:
    if not units:
        return 0.0
    counts = Counter(units)
    total = len(units)
    if len(counts) <= 1:
        return 0.0
    entropy = -sum((count / total) * math.log(count / total) for count in counts.values())
    return clamp01(entropy / math.log(len(counts)))


def observe_transition(previous: str, current: str, symbols: Sequence[str]) -> Dict[str, float]:
    prev_norm = normalize_for_similarity(previous)
    curr_norm = normalize_for_similarity(current)
    similarity = difflib.SequenceMatcher(None, prev_norm, curr_norm).ratio() if prev_norm or curr_norm else 1.0
    surface_drift = 1.0 - similarity

    prev_units = metric_units(previous)
    curr_units = metric_units(current)
    prev_set = set(prev_units)
    curr_set = set(curr_units)
    union = prev_set | curr_set
    intersection = prev_set & curr_set
    jaccard_similarity = safe_div(len(intersection), len(union), default=1.0)
    lexical_drift = 1.0 - jaccard_similarity
    novelty = safe_div(sum(1 for unit in curr_units if unit not in prev_set), len(curr_units), default=0.0)

    counts = Counter(curr_units)
    repeated = sum(count - 1 for count in counts.values() if count > 1)
    repetition = safe_div(repeated, len(curr_units), default=0.0)

    active_symbols = [sym for sym in symbols if sym]
    if active_symbols:
        present = 0.0
        for sym in active_symbols:
            present += min(1.0, current.count(sym) / 2.0)
        recurrence = present / len(active_symbols)
    else:
        recurrence = 0.0

    entropy = shannon_entropy_score(curr_units)
    char_len = float(len(current))
    shortness = 1.0 if char_len < 80 else max(0.0, 1.0 - char_len / 450.0)
    collapse = clamp01(0.55 * repetition + 0.30 * shortness + 0.15 * (1.0 - entropy))
    compression_ratio = safe_div(len(current), len(previous), default=1.0)
    drift_score = clamp01(0.65 * surface_drift + 0.35 * lexical_drift)

    return {
        "char_len": round(char_len, 4),
        "unit_count": round(float(len(curr_units)), 4),
        "similarity": round(similarity, 4),
        "surface_drift": round(surface_drift, 4),
        "lexical_drift": round(lexical_drift, 4),
        "drift_score": round(drift_score, 4),
        "novelty_score": round(novelty, 4),
        "repetition_score": round(repetition, 4),
        "recurrence_score": round(recurrence, 4),
        "entropy_score": round(entropy, 4),
        "collapse_score": round(collapse, 4),
        "compression_ratio": round(compression_ratio, 4),
    }


def term_hit_count(text: str, terms: Iterable[str]) -> int:
    lower = str(text or "").lower()
    return sum(1 for term in terms if term and term.lower() in lower)


def term_score(text: str, terms: Iterable[str], target: int) -> float:
    return clamp01(term_hit_count(text, terms) / max(1, target))


def profile_hit_score(text: str, values: Sequence[str], target: int) -> float:
    lower = str(text or "").lower()
    hits = 0
    for value in values:
        value = str(value or "").strip()
        if value and value.lower() in lower:
            hits += 1
    return clamp01(hits / max(1, target))


def compute_magic_realism_metrics(
    text: str,
    state: Optional[ChainState] = None,
    stage: Optional[StageSpec] = None,
    transition_metrics: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    profile = state.anchor_profile if state else None
    prior = state.magic_prior if state else None
    transition_metrics = transition_metrics or {}
    mundane_profile = 0.0
    social_profile = 0.0
    object_profile = 0.0
    continuity_profile = 0.0
    impossible_profile = 0.0
    if profile:
        mundane_profile = profile_hit_score(text, profile.mundane_anchors, target=3)
        social_profile = 0.35 if profile.social_setting and any(part in text for part in profile.social_setting.split("と")) else 0.0
        object_profile = profile_hit_score(text, profile.ordinary_objects, target=4)
        continuity_profile = profile_hit_score(text, profile.routine_actions, target=3)
        impossible_profile = profile_hit_score(text, profile.impossible_fact_slots, target=1)

    mundane_grounding = clamp01(0.45 * term_score(text, MUNDANE_OBJECT_TERMS, 6) + 0.35 * object_profile + 0.20 * mundane_profile)
    quiet_impossibility = clamp01(
        0.55 * term_score(text, IMPOSSIBLE_FACT_TERMS, 2)
        + 0.25 * impossible_profile
        + 0.20 * transition_metrics.get("novelty_score", 0.0)
    )
    explanation_density = clamp01(term_hit_count(text, EXPLANATION_TERMS) / 4.0)
    non_explanation = clamp01(1.0 - explanation_density)
    social_normalization = clamp01(0.65 * term_score(text, SOCIAL_NORMALIZATION_TERMS, 4) + 0.20 * social_profile + 0.15 * mundane_grounding)
    concrete_object = clamp01(0.70 * term_score(text, MUNDANE_OBJECT_TERMS, 7) + 0.30 * object_profile)
    symbolic_pressure = clamp01(
        0.45 * transition_metrics.get("recurrence_score", 0.0)
        + 0.25 * quiet_impossibility
        + 0.20 * concrete_object
        + 0.10 * (1.0 - transition_metrics.get("collapse_score", 0.0))
    )
    ordinary_continuity = clamp01(
        0.50 * term_score(text, ORDINARY_CONTINUITY_TERMS, 4)
        + 0.30 * continuity_profile
        + 0.20 * mundane_grounding
    )

    fantasy_lore_penalty = clamp01(term_hit_count(text, FANTASY_LORE_TERMS) / 2.0)
    dream_reveal_penalty = clamp01(term_hit_count(text, DREAM_REVEAL_TERMS) / 1.0)
    cosmic_explanation_penalty = clamp01(term_hit_count(text, COSMIC_EXPLANATION_TERMS) / 2.0)
    purple_abstraction_penalty = clamp01(term_hit_count(text, PURPLE_ABSTRACTION_TERMS) / 5.0)
    anti_fantasy = clamp01(1.0 - fantasy_lore_penalty)
    restraint = clamp01(1.0 - max(fantasy_lore_penalty, dream_reveal_penalty, cosmic_explanation_penalty, purple_abstraction_penalty, explanation_density * 0.6))

    weights = prior or default_magic_realism_prior()
    positive = (
        weights.mundane_grounding * mundane_grounding
        + weights.impossible_fact_density * quiet_impossibility
        + weights.explanatory_restraint * non_explanation
        + weights.social_normalization * social_normalization
        + weights.symbolic_recurrence * symbolic_pressure
        + weights.sensory_concreteness * concrete_object
        + weights.ordinary_continuity * ordinary_continuity
        + weights.restraint * restraint
    )
    positive_total = (
        weights.mundane_grounding
        + weights.impossible_fact_density
        + weights.explanatory_restraint
        + weights.social_normalization
        + weights.symbolic_recurrence
        + weights.sensory_concreteness
        + weights.ordinary_continuity
        + weights.restraint
    ) or 1.0
    penalty = (
        weights.anti_fantasy_penalty * fantasy_lore_penalty
        + weights.anti_dream_penalty * dream_reveal_penalty
        + weights.anti_cosmic_explanation_penalty * cosmic_explanation_penalty
        + weights.anti_purple_prose_penalty * purple_abstraction_penalty
    )
    penalty_total = (
        weights.anti_fantasy_penalty
        + weights.anti_dream_penalty
        + weights.anti_cosmic_explanation_penalty
        + weights.anti_purple_prose_penalty
    ) or 1.0
    magic_reward = clamp01((positive / positive_total) - 0.38 * (penalty / penalty_total))

    if stage and stage.operator in {"quiet_impossibility_injection", "make_magic_a_weather_condition_not_a_message"}:
        quiet_impossibility = clamp01(0.82 * quiet_impossibility + 0.18 * magic_reward)
    if stage and stage.operator in {"social_normalization", "stabilize_magic_as_world_law"}:
        social_normalization = clamp01(0.82 * social_normalization + 0.18 * magic_reward)

    return {
        "mundane_grounding_score": round(mundane_grounding, 4),
        "quiet_impossibility_score": round(quiet_impossibility, 4),
        "non_explanation_score": round(non_explanation, 4),
        "social_normalization_score": round(social_normalization, 4),
        "anti_fantasy_score": round(anti_fantasy, 4),
        "concrete_object_score": round(concrete_object, 4),
        "symbolic_pressure_score": round(symbolic_pressure, 4),
        "ordinary_continuity_score": round(ordinary_continuity, 4),
        "restraint_score": round(restraint, 4),
        "fantasy_lore_penalty": round(fantasy_lore_penalty, 4),
        "dream_reveal_penalty": round(dream_reveal_penalty, 4),
        "cosmic_explanation_penalty": round(cosmic_explanation_penalty, 4),
        "purple_abstraction_penalty": round(purple_abstraction_penalty, 4),
        "explanation_density_score": round(explanation_density, 4),
        "magic_realism_reward": round(magic_reward, 4),
    }


def candidate_symbols_from_text(text: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for raw in QUOTE_RE.findall(text):
        candidate = raw.strip()
        if 1 <= len(candidate) <= 16 and candidate.lower() not in STOP_SYMBOLS:
            counts[candidate] += 4
    for token in tokenize_text(text):
        if token in STOP_SYMBOLS:
            continue
        if len(token) <= 1:
            continue
        if re.fullmatch(r"[ぁ-ゖ]+", token):
            continue
        weight = 1
        if re.search(r"[一-龯ァ-ヴー]", token):
            weight += min(3, len(token) // 2)
        elif len(token) >= 5:
            weight += 1
        counts[token] += weight
    return counts


def merge_symbols(existing: Sequence[str], text: str, limit: int) -> List[str]:
    cleaned_existing: List[str] = []
    seen = set()
    for sym in existing:
        sym = sym.strip()
        if not sym or sym.lower() in STOP_SYMBOLS or sym in seen:
            continue
        cleaned_existing.append(sym)
        seen.add(sym)

    candidates = candidate_symbols_from_text(text)
    for sym in cleaned_existing:
        candidates[sym] += 6 + min(4, text.count(sym))

    ranked = sorted(candidates.items(), key=lambda kv: (kv[1], len(kv[0])), reverse=True)
    merged: List[str] = []
    seen_lower = set()
    for sym, _score in ranked:
        key = sym.lower()
        if key in seen_lower or key in STOP_SYMBOLS:
            continue
        if len(sym) > 18:
            continue
        merged.append(sym)
        seen_lower.add(key)
        if len(merged) >= limit:
            break
    return merged


def make_control_notes(metrics: Dict[str, float], symbols: Sequence[str], constraints: ChainConstraints, text: str) -> List[str]:
    notes: List[str] = []
    drift = metrics.get("drift_score", 0.0)
    novelty = metrics.get("novelty_score", 0.0)
    repetition = metrics.get("repetition_score", 0.0)
    recurrence = metrics.get("recurrence_score", 0.0)
    collapse = metrics.get("collapse_score", 0.0)

    if drift > constraints.max_drift:
        notes.append("Drift is high: preserve the seed's scene, narrator, and 1-2 existing symbols before adding new material.")
    elif drift < constraints.min_drift:
        notes.append("Drift is low: introduce one controlled mutation that changes the scene without replacing its ground.")

    if novelty < constraints.min_novelty:
        notes.append("Novelty is low: add fresh concrete detail rather than paraphrasing the prior stage.")

    if repetition > constraints.max_repetition:
        notes.append("Repetition is high: vary images and sentence shapes; transform symbols instead of repeating the same words.")

    if symbols and recurrence < constraints.min_recurrence:
        notes.append("Symbol recurrence is weak: reintroduce one existing symbol through action, sound, or object behavior.")

    if collapse > constraints.max_collapse:
        notes.append("Collapse risk is high: expand sensory grounding and avoid short, generic abstraction.")

    if "magic_realism_reward" in metrics:
        if metrics.get("mundane_grounding_score", 1.0) < 0.45:
            notes.append("Magic realism prior: restore a mundane social setting, concrete object, or routine action.")
        if metrics.get("quiet_impossibility_score", 1.0) < 0.35:
            notes.append("Magic realism prior: add one small material impossibility without explaining it.")
        if metrics.get("social_normalization_score", 1.0) < 0.35:
            notes.append("Magic realism prior: show a person, office, shop, rule, or habit adapting to the impossible fact.")
        if metrics.get("non_explanation_score", 1.0) < 0.70:
            notes.append("Magic realism prior: remove explanation, dream logic, magic-system language, or interpretive summary.")
        if metrics.get("ordinary_continuity_score", 1.0) < 0.35:
            notes.append("Magic realism prior: let work, travel, paperwork, food, or another ordinary task continue after the impossible fact.")

    if constraints.required_prefix and not text.startswith(constraints.required_prefix):
        notes.append(f"Required prefix was missing: future controlled outputs should begin with {constraints.required_prefix!r}.")

    return notes

# ---------------------------------------------------------------------------
# RPM matrix trace
# ---------------------------------------------------------------------------


RPM_METRIC_KEYS: Tuple[str, ...] = (
    "drift_score",
    "novelty_score",
    "repetition_score",
    "recurrence_score",
    "entropy_score",
    "collapse_score",
    "compression_ratio",
    "mundane_grounding_score",
    "quiet_impossibility_score",
    "non_explanation_score",
    "social_normalization_score",
    "anti_fantasy_score",
    "concrete_object_score",
    "symbolic_pressure_score",
    "ordinary_continuity_score",
    "magic_realism_reward",
)


def metric_delta(before: Dict[str, float], after: Dict[str, float]) -> Dict[str, float]:
    deltas: Dict[str, float] = {}
    for key in RPM_METRIC_KEYS:
        if key in after:
            base = float(before.get(key, 0.0))
            deltas[key] = round(float(after[key]) - base, 4)
    return deltas


def sign_label(value: float, eps: float = 0.035) -> str:
    if value > eps:
        return "increase"
    if value < -eps:
        return "decrease"
    return "stable"


def operator_effects_from_delta(delta: Dict[str, float], reward: Optional[ProcessReward]) -> Dict[str, str]:
    effects = {key: sign_label(value) for key, value in delta.items()}
    if reward:
        effects["reward"] = "high" if reward.score >= 0.72 else "medium" if reward.score >= 0.55 else "low"
        for axis in (
            "grounding",
            "symbol_recurrence",
            "drift_control",
            "integration",
            "closure",
            "mundane_grounding",
            "quiet_impossibility",
            "non_explanation",
            "social_normalization",
            "anti_fantasy",
            "concrete_object",
            "symbolic_pressure",
            "ordinary_continuity",
            "magic_realism",
        ):
            if axis in reward.metric_scores:
                effects[f"reward_axis:{axis}"] = "high" if reward.metric_scores[axis] >= 0.72 else "medium" if reward.metric_scores[axis] >= 0.5 else "low"
    return effects


def make_rule_id(stage_index: int, offset: int) -> str:
    return f"r{stage_index:02d}-{offset:02d}"


def make_conflict_id(stage_index: int, offset: int, conflict_type: str) -> str:
    safe_type = re.sub(r"[^a-z0-9_]+", "_", conflict_type.lower()).strip("_") or "conflict"
    return f"c{stage_index:02d}-{offset:02d}-{safe_type}"


def make_symbol_statement(symbol: str, stage: StageSpec) -> str:
    role_phrase = {
        "grounder": "anchors the scene in concrete reality",
        "expander": "survives an impossible perturbation",
        "symbolizer": "becomes a recurring symbolic circuit",
        "stabilizer": "helps keep the drift legible",
        "compressor": "remains after compression",
        "integrator": "connects multiple accepted stages",
        "recursive": "returns the seed in transformed form",
    }.get(stage.role, "participates in the visible transformation")
    return f"{symbol!r} {role_phrase} during {stage.name}."


def infer_rules_for_cell(stage: StageSpec, candidate: CandidateStep, cell: RPMCell, seed: str) -> List[RuleHypothesis]:
    rules: List[RuleHypothesis] = []
    reward_score = candidate.reward.score if candidate.reward else 0.0
    recurrence = candidate.metrics.get("recurrence_score", 0.0)
    symbol_confidence = clamp01(0.35 + 0.35 * recurrence + 0.30 * reward_score)

    active_symbols: List[str] = []
    for sym in candidate.symbols_after:
        if sym in candidate.output or sym in seed:
            active_symbols.append(sym)
        if len(active_symbols) >= 3:
            break

    for i, sym in enumerate(active_symbols, start=1):
        rules.append(
            RuleHypothesis(
                rule_id=make_rule_id(candidate.stage_index, i),
                kind="symbolic_recurrence",
                statement=make_symbol_statement(sym, stage),
                confidence=round(symbol_confidence, 4),
                support=[candidate.candidate_id, stage.operator or stage.role],
                stage_indices=[candidate.stage_index],
            )
        )

    delta_summary = ", ".join(f"{k}:{v}" for k, v in sorted(cell.operator_effects.items()) if k in RPM_METRIC_KEYS)
    if not delta_summary:
        delta_summary = "initial operator application"
    rules.append(
        RuleHypothesis(
            rule_id=make_rule_id(candidate.stage_index, len(rules) + 1),
            kind="operator_effect",
            statement=f"Operator {stage.operator or stage.role!r} acts on the state as {delta_summary}.",
            confidence=round(clamp01(0.45 + 0.55 * reward_score), 4),
            support=[candidate.candidate_id, f"reward={reward_score:.3f}"],
            stage_indices=[candidate.stage_index],
        )
    )
    return rules


def resolve_existing_conflicts(trace: RPMTrace, candidate: CandidateStep, constraints: ChainConstraints) -> None:
    for conflict in trace.conflicts:
        if conflict.resolved:
            continue
        if conflict.type == "high_drift" and candidate.metrics.get("drift_score", 1.0) <= constraints.max_drift:
            conflict.resolved = True
        elif conflict.type == "collapse" and candidate.metrics.get("collapse_score", 1.0) <= constraints.max_collapse:
            conflict.resolved = True
        elif conflict.type == "repetition" and candidate.metrics.get("repetition_score", 1.0) <= constraints.max_repetition:
            conflict.resolved = True
        elif conflict.type == "symbol_loss":
            lost = conflict.evidence.get("symbols", [])
            if isinstance(lost, list) and any(sym in candidate.output for sym in lost):
                conflict.resolved = True
        elif conflict.type == "operator_mismatch" and candidate.reward and candidate.reward.score >= 0.68:
            conflict.resolved = True
        elif conflict.type == "weak_closure" and candidate.reward and candidate.reward.metric_scores.get("closure", 0.0) >= 0.45:
            conflict.resolved = True
        elif conflict.type == "weak_mundane_grounding" and candidate.metrics.get("mundane_grounding_score", 0.0) >= 0.45:
            conflict.resolved = True
        elif conflict.type == "weak_impossibility" and candidate.metrics.get("quiet_impossibility_score", 0.0) >= 0.35:
            conflict.resolved = True
        elif conflict.type == "over_explanation" and candidate.metrics.get("non_explanation_score", 0.0) >= 0.78:
            conflict.resolved = True
        elif conflict.type == "fantasy_drift" and candidate.metrics.get("anti_fantasy_score", 0.0) >= 0.90:
            conflict.resolved = True


def detect_rpm_conflicts(
    trace: RPMTrace,
    stage: StageSpec,
    candidate: CandidateStep,
    cell: RPMCell,
    constraints: ChainConstraints,
) -> List[RPMConflict]:
    conflicts: List[RPMConflict] = []
    metrics = candidate.metrics
    reward = candidate.reward

    def add(conflict_type: str, severity: float, description: str, evidence: Dict[str, Any], repair: str) -> None:
        conflicts.append(
            RPMConflict(
                conflict_id=make_conflict_id(candidate.stage_index, len(conflicts) + 1, conflict_type),
                type=conflict_type,
                severity=round(clamp01(severity), 4),
                description=description,
                evidence=json_safe(evidence),
                repair_instruction=repair,
            )
        )

    drift = metrics.get("drift_score", 0.0)
    if drift > constraints.max_drift:
        add(
            "high_drift",
            safe_div(drift - constraints.max_drift, max(1e-6, 1.0 - constraints.max_drift)),
            "The accepted transition moved too far from the previous state.",
            {"drift_score": drift, "max_drift": constraints.max_drift},
            "Re-anchor the next transition in the seed scene and reuse one stable symbol before adding new material.",
        )

    repetition = metrics.get("repetition_score", 0.0)
    if repetition > constraints.max_repetition:
        add(
            "repetition",
            safe_div(repetition - constraints.max_repetition, max(1e-6, 1.0 - constraints.max_repetition)),
            "The accepted transition repeats surface units too strongly.",
            {"repetition_score": repetition, "max_repetition": constraints.max_repetition},
            "Transform repeated symbols through action, sound, or object behavior instead of repeating the same wording.",
        )

    collapse = metrics.get("collapse_score", 0.0)
    if collapse > constraints.max_collapse:
        add(
            "collapse",
            safe_div(collapse - constraints.max_collapse, max(1e-6, 1.0 - constraints.max_collapse)),
            "The accepted transition risks becoming too short, generic, or abstract.",
            {"collapse_score": collapse, "max_collapse": constraints.max_collapse},
            "Restore sensory ground: place, object, body action, and sound before symbolic abstraction.",
        )

    if cell.symbols_lost and stage.role in ("symbolizer", "integrator", "recursive"):
        add(
            "symbol_loss",
            min(1.0, len(cell.symbols_lost) / max(1, len(cell.symbols_before))),
            "Symbols that should recur disappeared during a recurrence-sensitive stage.",
            {"symbols": cell.symbols_lost, "role": stage.role},
            "Bring one lost symbol back as a changed object or sound, not as a flat keyword repetition.",
        )

    if stage.role == "expander" and metrics.get("novelty_score", 0.0) < constraints.min_novelty:
        add(
            "operator_mismatch",
            clamp01(1.0 - metrics.get("novelty_score", 0.0) / max(1e-6, constraints.min_novelty)),
            "The expander did not introduce enough controlled novelty.",
            {"novelty_score": metrics.get("novelty_score", 0.0), "operator": stage.operator},
            "Add exactly one ordinary impossible fact while preserving the existing scene.",
        )

    if stage.role == "symbolizer" and metrics.get("recurrence_score", 0.0) < constraints.min_recurrence:
        add(
            "operator_mismatch",
            clamp01(1.0 - metrics.get("recurrence_score", 0.0) / max(1e-6, constraints.min_recurrence)),
            "The symbolizer did not produce enough recurrence.",
            {"recurrence_score": metrics.get("recurrence_score", 0.0), "operator": stage.operator},
            "Choose one stable symbol and return it through a different sensory channel.",
        )

    if stage.role == "compressor" and metrics.get("compression_ratio", 1.0) > 1.25:
        add(
            "operator_mismatch",
            clamp01((metrics.get("compression_ratio", 1.0) - 1.25) / 1.75),
            "The compressor expanded instead of compressing the visible state.",
            {"compression_ratio": metrics.get("compression_ratio", 1.0), "operator": stage.operator},
            "Compress to the seed, one impossible fact, and two recurring images.",
        )

    if stage.role == "recursive" and reward and reward.metric_scores.get("closure", 0.5) < 0.45:
        add(
            "weak_closure",
            clamp01(1.0 - reward.metric_scores.get("closure", 0.0) / 0.45),
            "The recursive closure did not echo the seed strongly enough.",
            {"closure": reward.metric_scores.get("closure"), "operator": stage.operator},
            "Make the final image return to the seed in transformed form without direct explanation.",
        )

    if "magic_realism_reward" in metrics:
        if metrics.get("mundane_grounding_score", 1.0) < 0.38:
            add(
                "weak_mundane_grounding",
                clamp01(1.0 - metrics.get("mundane_grounding_score", 0.0) / 0.38),
                "The magic-realism prior lost its ordinary social ground.",
                {"mundane_grounding_score": metrics.get("mundane_grounding_score"), "operator": stage.operator},
                "Restore a concrete social place, object, routine, or procedure before adding more impossibility.",
            )
        if metrics.get("quiet_impossibility_score", 1.0) < 0.30 and stage.role in ("expander", "symbolizer", "integrator"):
            add(
                "weak_impossibility",
                clamp01(1.0 - metrics.get("quiet_impossibility_score", 0.0) / 0.30),
                "The step did not materialize a small impossible fact strongly enough.",
                {"quiet_impossibility_score": metrics.get("quiet_impossibility_score"), "operator": stage.operator},
                "Add one material impossibility inside a mundane object or procedure, without naming a magic system.",
            )
        if metrics.get("non_explanation_score", 1.0) < 0.70:
            add(
                "over_explanation",
                clamp01(1.0 - metrics.get("non_explanation_score", 0.0) / 0.70),
                "The step explained or interpreted the impossible fact too directly.",
                {"non_explanation_score": metrics.get("non_explanation_score"), "operator": stage.operator},
                "Remove explanation, revelation, dream logic, and direct interpretation; keep material consequences.",
            )
        if metrics.get("anti_fantasy_score", 1.0) < 0.80:
            add(
                "fantasy_drift",
                clamp01(1.0 - metrics.get("anti_fantasy_score", 0.0) / 0.80),
                "The step drifted toward fantasy lore rather than magic realism.",
                {"anti_fantasy_score": metrics.get("anti_fantasy_score"), "operator": stage.operator},
                "Remove fantasy-lore language and return to ordinary people, errands, work, food, documents, or weather.",
            )

    return conflicts


def recompute_symbol_stability(trace: RPMTrace) -> None:
    after_counts: Counter[str] = Counter()
    gained_counts: Counter[str] = Counter()
    lost_counts: Counter[str] = Counter()
    for cell in trace.matrix:
        after_counts.update(cell.symbols_after)
        gained_counts.update(cell.symbols_gained)
        lost_counts.update(cell.symbols_lost)
    stable = [sym for sym, count in after_counts.most_common() if count >= 2]
    unstable = [sym for sym, count in (gained_counts + lost_counts).most_common() if sym not in stable]
    trace.stable_symbols = stable[:12]
    trace.unstable_symbols = unstable[:12]


def recompute_drift_vector(trace: RPMTrace) -> None:
    if not trace.matrix:
        trace.drift_vector = {}
        return
    drift_values = [cell.metrics_after.get("drift_score", 0.0) for cell in trace.matrix]
    recurrence_values = [cell.metrics_after.get("recurrence_score", 0.0) for cell in trace.matrix]
    reward_values = [cell.reward_score or 0.0 for cell in trace.matrix]
    trace.drift_vector = {
        "mean_drift": round(sum(drift_values) / len(drift_values), 4),
        "last_drift": round(drift_values[-1], 4),
        "mean_recurrence": round(sum(recurrence_values) / len(recurrence_values), 4),
        "last_recurrence": round(recurrence_values[-1], 4),
        "mean_reward": round(sum(reward_values) / len(reward_values), 4),
        "last_reward": round(reward_values[-1], 4),
    }


def merge_rules(existing: Sequence[RuleHypothesis], new_rules: Sequence[RuleHypothesis], limit: int = 32) -> List[RuleHypothesis]:
    by_statement: Dict[str, RuleHypothesis] = {}
    for rule in list(existing) + list(new_rules):
        key = re.sub(r"\s+", " ", rule.statement.strip().lower())
        if not key:
            continue
        prior = by_statement.get(key)
        if prior is None:
            by_statement[key] = rule
        else:
            prior.confidence = max(prior.confidence, rule.confidence)
            prior.support = sorted(set(prior.support + rule.support))
            prior.stage_indices = sorted(set(prior.stage_indices + rule.stage_indices))
    ordered = sorted(by_statement.values(), key=lambda r: (r.confidence, max(r.stage_indices or [0])), reverse=True)
    return ordered[:limit]


class RPMObserver:
    def __init__(self, constraints: ChainConstraints) -> None:
        self.constraints = constraints

    def update(self, state: ChainState, stage: StageSpec, candidate: CandidateStep, metrics_before: Dict[str, float]) -> RPMCell:
        resolve_existing_conflicts(state.rpm_trace, candidate, self.constraints)
        before_symbols = list(candidate.symbols_before)
        after_symbols = list(candidate.symbols_after)
        gained = [sym for sym in after_symbols if sym not in before_symbols]
        lost = [sym for sym in before_symbols if sym not in after_symbols or sym not in candidate.output]
        delta = metric_delta(metrics_before, candidate.metrics)
        reward_score = candidate.reward.score if candidate.reward else None
        cell = RPMCell(
            row_index=len(state.rpm_trace.matrix) + 1,
            stage_name=stage.name,
            role=stage.role,
            operator=stage.operator,
            provider=candidate.provider,
            model=candidate.model,
            candidate_id=candidate.candidate_id,
            status="accepted",
            text_preview=clip_text(candidate.output.replace("\n", " "), 280),
            reward_score=reward_score,
            symbols_before=before_symbols,
            symbols_after=after_symbols,
            symbols_gained=gained,
            symbols_lost=lost,
            metrics_before=dict(metrics_before),
            metrics_after=dict(candidate.metrics),
            metric_delta=delta,
            operator_effects=operator_effects_from_delta(delta, candidate.reward),
        )
        rules = infer_rules_for_cell(stage, candidate, cell, state.seed)
        conflicts = detect_rpm_conflicts(state.rpm_trace, stage, candidate, cell, self.constraints)
        cell.rule_ids = [rule.rule_id for rule in rules]
        cell.conflict_ids = [conflict.conflict_id for conflict in conflicts]
        state.rpm_trace.matrix.append(cell)
        state.rpm_trace.inferred_rules = merge_rules(state.rpm_trace.inferred_rules, rules)
        state.rpm_trace.conflicts.extend(conflicts)
        for conflict in conflicts:
            state.rpm_trace.repair_plans.append(
                RPMRepairPlan(
                    conflict_id=conflict.conflict_id,
                    stage_index=candidate.stage_index,
                    instruction=conflict.repair_instruction,
                    applied_by_candidate_id=None,
                )
            )
        recompute_symbol_stability(state.rpm_trace)
        recompute_drift_vector(state.rpm_trace)
        unresolved = [c for c in state.rpm_trace.conflicts if not c.resolved]
        state.rpm_trace.notes = [
            f"matrix_rows={len(state.rpm_trace.matrix)}",
            f"rules={len(state.rpm_trace.inferred_rules)}",
            f"unresolved_conflicts={len(unresolved)}",
        ]
        return cell


def format_rpm_context(trace: RPMTrace, max_rules: int = 6, max_conflicts: int = 5, max_rows: int = 4) -> str:
    if not trace.matrix and not trace.inferred_rules and not trace.conflicts:
        return "RPM matrix is empty: no accepted transition has been recorded yet."
    lines: List[str] = []
    if trace.stable_symbols:
        lines.append("Stable symbols: " + ", ".join(trace.stable_symbols[:10]))
    if trace.unstable_symbols:
        lines.append("Unstable symbols: " + ", ".join(trace.unstable_symbols[:8]))
    if trace.drift_vector:
        lines.append("Drift vector: " + json.dumps(trace.drift_vector, ensure_ascii=False))
    unresolved = [c for c in trace.conflicts if not c.resolved]
    if unresolved:
        lines.append("Unresolved conflicts:")
        for conflict in unresolved[-max_conflicts:]:
            lines.append(f"- {conflict.conflict_id} [{conflict.type}, severity={conflict.severity}]: {conflict.repair_instruction}")
    if trace.inferred_rules:
        lines.append("Current rule hypotheses:")
        for rule in trace.inferred_rules[:max_rules]:
            lines.append(f"- {rule.rule_id} ({rule.kind}, conf={rule.confidence}): {rule.statement}")
    if trace.matrix:
        lines.append("Recent matrix cells:")
        for cell in trace.matrix[-max_rows:]:
            effects = ", ".join(f"{k}={v}" for k, v in cell.operator_effects.items() if k in ("drift_score", "recurrence_score", "collapse_score", "reward"))
            lines.append(f"- row {cell.row_index}: {cell.role}/{cell.operator} by {cell.provider}; reward={cell.reward_score}; effects={effects or '(none)'}")
    return "\n".join(lines)


def format_rpm_markdown(trace: RPMTrace) -> str:
    lines: List[str] = []
    lines.append("## RPM matrix trace")
    lines.append("")
    lines.append(f"- Axes: `{', '.join(trace.axes)}`")
    lines.append(f"- Stable symbols: `{', '.join(trace.stable_symbols) if trace.stable_symbols else '(none)'}`")
    lines.append(f"- Unstable symbols: `{', '.join(trace.unstable_symbols) if trace.unstable_symbols else '(none)'}`")
    lines.append(f"- Drift vector: `{json.dumps(trace.drift_vector, ensure_ascii=False) if trace.drift_vector else '{}'}`")
    unresolved = [c for c in trace.conflicts if not c.resolved]
    lines.append(f"- Conflicts: `{len(trace.conflicts)}` total / `{len(unresolved)}` unresolved")
    lines.append("")

    if trace.matrix:
        lines.append("### Matrix cells")
        lines.append("")
        lines.append("| row | role | operator | provider | reward | drift | recurrence | symbols gained/lost | conflicts |")
        lines.append("|---:|---|---|---|---:|---:|---:|---|---|")
        for cell in trace.matrix:
            gained = ", ".join(cell.symbols_gained[:4]) or "-"
            lost = ", ".join(cell.symbols_lost[:4]) or "-"
            conflicts = ", ".join(cell.conflict_ids) or "-"
            reward = "" if cell.reward_score is None else f"{cell.reward_score:.3f}"
            lines.append(
                f"| {cell.row_index} | {cell.role} | `{cell.operator}` | {cell.provider} | {reward} | "
                f"{cell.metrics_after.get('drift_score', 0.0):.3f} | {cell.metrics_after.get('recurrence_score', 0.0):.3f} | "
                f"+ {gained} / - {lost} | {conflicts} |"
            )
        lines.append("")

    if trace.inferred_rules:
        lines.append("### Rule hypotheses")
        lines.append("")
        for rule in trace.inferred_rules:
            lines.append(f"- `{rule.rule_id}` **{rule.kind}** `{rule.confidence:.3f}` - {rule.statement}")
        lines.append("")

    if trace.conflicts:
        lines.append("### Conflicts and repair plans")
        lines.append("")
        for conflict in trace.conflicts:
            status = "resolved" if conflict.resolved else "open"
            lines.append(f"- `{conflict.conflict_id}` **{conflict.type}** `{status}` severity `{conflict.severity:.3f}`: {conflict.description}")
            if conflict.repair_instruction:
                lines.append(f"  - repair: {conflict.repair_instruction}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PRM scoring
# ---------------------------------------------------------------------------


class ProcessRewardModel(Protocol):
    def score(self, state: ChainState, stage: StageSpec, candidate: CandidateStep) -> ProcessReward:
        ...


def score_inside_range(value: float, low: float, high: float) -> float:
    if low <= value <= high:
        return 1.0
    if value < low:
        return clamp01(value / low) if low > 0 else 0.0
    if high >= 1.0:
        return 1.0 if value <= high else 0.0
    return clamp01(1.0 - (value - high) / (1.0 - high))


def symbol_presence_score(text: str, symbols: Sequence[str]) -> float:
    active = [s for s in symbols if s]
    if not active:
        return 0.5
    return safe_div(sum(1 for s in active if s in text), len(active), default=0.5)


def seed_echo_score(seed: str, text: str) -> float:
    seed_units = set(metric_units(seed))
    text_units = set(metric_units(text))
    if not seed_units:
        return 0.5
    lexical = safe_div(len(seed_units & text_units), len(seed_units), default=0.0)
    seed_grams = set(char_ngrams(seed, n=3, limit=1200))
    text_grams = set(char_ngrams(text, n=3, limit=3000))
    gram = safe_div(len(seed_grams & text_grams), len(seed_grams), default=0.0) if seed_grams else 0.0
    return clamp01(0.65 * lexical + 0.35 * gram)


def stage_weights(role: str) -> Dict[str, float]:
    base = {
        "grounding": 0.14,
        "controlled_perturbation": 0.10,
        "symbol_recurrence": 0.14,
        "drift_control": 0.16,
        "novelty": 0.12,
        "repetition_control": 0.10,
        "collapse_control": 0.12,
        "integration": 0.12,
        "closure": 0.00,
    }
    by_role = {
        "grounder": {
            "grounding": 0.30,
            "drift_control": 0.24,
            "collapse_control": 0.16,
            "novelty": 0.10,
            "symbol_recurrence": 0.10,
            "repetition_control": 0.10,
            "integration": 0.00,
            "controlled_perturbation": 0.00,
            "closure": 0.00,
        },
        "expander": {
            "controlled_perturbation": 0.28,
            "novelty": 0.20,
            "drift_control": 0.18,
            "grounding": 0.12,
            "symbol_recurrence": 0.12,
            "collapse_control": 0.10,
            "repetition_control": 0.00,
            "integration": 0.00,
            "closure": 0.00,
        },
        "symbolizer": {
            "symbol_recurrence": 0.32,
            "repetition_control": 0.20,
            "novelty": 0.14,
            "integration": 0.14,
            "drift_control": 0.10,
            "collapse_control": 0.10,
            "grounding": 0.00,
            "controlled_perturbation": 0.00,
            "closure": 0.00,
        },
        "stabilizer": {
            "drift_control": 0.30,
            "integration": 0.22,
            "collapse_control": 0.18,
            "symbol_recurrence": 0.14,
            "grounding": 0.10,
            "repetition_control": 0.06,
            "novelty": 0.00,
            "controlled_perturbation": 0.00,
            "closure": 0.00,
        },
        "compressor": {
            "integration": 0.26,
            "collapse_control": 0.18,
            "symbol_recurrence": 0.18,
            "drift_control": 0.14,
            "repetition_control": 0.10,
            "grounding": 0.08,
            "novelty": 0.06,
            "controlled_perturbation": 0.00,
            "closure": 0.00,
        },
        "integrator": {
            "integration": 0.32,
            "symbol_recurrence": 0.18,
            "drift_control": 0.16,
            "collapse_control": 0.14,
            "grounding": 0.10,
            "novelty": 0.06,
            "repetition_control": 0.04,
            "controlled_perturbation": 0.00,
            "closure": 0.00,
        },
        "recursive": {
            "closure": 0.34,
            "integration": 0.24,
            "symbol_recurrence": 0.16,
            "drift_control": 0.12,
            "collapse_control": 0.10,
            "repetition_control": 0.04,
            "grounding": 0.00,
            "controlled_perturbation": 0.00,
            "novelty": 0.00,
        },
    }
    weights = by_role.get(role, base)
    total = sum(weights.values()) or 1.0
    return {k: v / total for k, v in weights.items()}


class HeuristicPRM:
    def __init__(self, constraints: ChainConstraints, accept_threshold: float = 0.62, repair_threshold: float = 0.50) -> None:
        self.constraints = constraints
        self.accept_threshold = accept_threshold
        self.repair_threshold = repair_threshold

    def score(self, state: ChainState, stage: StageSpec, candidate: CandidateStep) -> ProcessReward:
        metrics = candidate.metrics
        text = candidate.output
        drift = metrics.get("drift_score", 0.0)
        novelty = metrics.get("novelty_score", 0.0)
        repetition = metrics.get("repetition_score", 0.0)
        recurrence = metrics.get("recurrence_score", 0.0)
        entropy = metrics.get("entropy_score", 0.0)
        collapse = metrics.get("collapse_score", 0.0)
        char_len = metrics.get("char_len", 0.0)
        compression = metrics.get("compression_ratio", 1.0)

        drift_control = score_inside_range(drift, self.constraints.min_drift, self.constraints.max_drift)
        repetition_control = clamp01(1.0 - safe_div(repetition, max(self.constraints.max_repetition, 1e-6)))
        collapse_control = clamp01(1.0 - safe_div(collapse, max(self.constraints.max_collapse, 1e-6)))
        symbol_presence = symbol_presence_score(text, state.symbols)
        length_score = clamp01(char_len / 360.0)
        grounding = clamp01(0.45 * length_score + 0.35 * entropy + 0.20 * collapse_control)

        # Perturbation is rewarded when the step changes enough to matter but does not replace the entire world.
        perturbation_target = 0.54 if stage.role == "expander" else 0.45
        controlled_perturbation = clamp01(1.0 - abs(drift - perturbation_target) / 0.54)

        symbol_recurrence = clamp01(0.70 * recurrence + 0.30 * symbol_presence)
        integration = clamp01(0.42 * symbol_recurrence + 0.28 * drift_control + 0.20 * collapse_control + 0.10 * entropy)
        closure = clamp01(0.55 * seed_echo_score(state.seed, text) + 0.30 * symbol_recurrence + 0.15 * drift_control)

        # Compression role should not be punished for being shorter when it still retains integration.
        if stage.role == "compressor":
            compression_score = clamp01(1.0 - max(0.0, compression - 1.15) / 1.5)
            integration = clamp01(0.75 * integration + 0.25 * compression_score)
            grounding = clamp01(0.70 * grounding + 0.30 * min(1.0, char_len / 220.0))

        metric_scores = {
            "grounding": round(grounding, 4),
            "controlled_perturbation": round(controlled_perturbation, 4),
            "symbol_recurrence": round(symbol_recurrence, 4),
            "drift_control": round(drift_control, 4),
            "novelty": round(clamp01(novelty), 4),
            "repetition_control": round(repetition_control, 4),
            "collapse_control": round(collapse_control, 4),
            "integration": round(integration, 4),
            "closure": round(closure, 4),
        }

        weights = stage_weights(stage.role)
        base_score = sum(weights.get(k, 0.0) * metric_scores.get(k, 0.0) for k in weights)
        if state.magic_prior:
            magic_metric_map = {
                "mundane_grounding": "mundane_grounding_score",
                "quiet_impossibility": "quiet_impossibility_score",
                "non_explanation": "non_explanation_score",
                "social_normalization": "social_normalization_score",
                "anti_fantasy": "anti_fantasy_score",
                "concrete_object": "concrete_object_score",
                "symbolic_pressure": "symbolic_pressure_score",
                "ordinary_continuity": "ordinary_continuity_score",
                "restraint": "restraint_score",
                "magic_realism": "magic_realism_reward",
            }
            for axis, metric_key in magic_metric_map.items():
                if metric_key in metrics:
                    metric_scores[axis] = round(float(metrics[metric_key]), 4)
            magic_score = float(metrics.get("magic_realism_reward", 0.0) or 0.0)
            score = 0.68 * base_score + 0.32 * magic_score
        else:
            magic_score = None
            score = base_score
        score = round(clamp01(score), 4)

        reasons: List[str] = []
        if drift > self.constraints.max_drift:
            reasons.append(f"drift too high ({drift:.3f})")
        if drift < self.constraints.min_drift and stage.role not in ("grounder", "compressor"):
            reasons.append(f"drift too low ({drift:.3f}); step may be paraphrase")
        if novelty < self.constraints.min_novelty and stage.role not in ("stabilizer", "compressor", "recursive"):
            reasons.append(f"novelty low ({novelty:.3f})")
        if repetition > self.constraints.max_repetition:
            reasons.append(f"repetition high ({repetition:.3f})")
        if state.symbols and recurrence < self.constraints.min_recurrence and stage.role in ("symbolizer", "integrator", "recursive"):
            reasons.append(f"symbol recurrence weak ({recurrence:.3f})")
        if collapse > self.constraints.max_collapse:
            reasons.append(f"collapse risk high ({collapse:.3f})")
        if self.constraints.required_prefix and not text.startswith(self.constraints.required_prefix):
            reasons.append("required prefix missing")
        if state.magic_prior:
            if metrics.get("mundane_grounding_score", 1.0) < 0.40:
                reasons.append(f"mundane grounding weak ({metrics.get('mundane_grounding_score', 0.0):.3f})")
            if stage.role in ("expander", "symbolizer", "integrator") and metrics.get("quiet_impossibility_score", 1.0) < 0.30:
                reasons.append(f"quiet impossibility weak ({metrics.get('quiet_impossibility_score', 0.0):.3f})")
            if metrics.get("non_explanation_score", 1.0) < 0.70:
                reasons.append(f"over-explained magic ({metrics.get('non_explanation_score', 0.0):.3f})")
            if metrics.get("anti_fantasy_score", 1.0) < 0.80:
                reasons.append(f"fantasy drift ({metrics.get('anti_fantasy_score', 0.0):.3f})")
            if metrics.get("ordinary_continuity_score", 1.0) < 0.25 and stage.role in ("stabilizer", "compressor", "integrator", "recursive"):
                reasons.append(f"ordinary continuity weak ({metrics.get('ordinary_continuity_score', 0.0):.3f})")

        accept = score >= self.accept_threshold and not (self.constraints.required_prefix and not text.startswith(self.constraints.required_prefix))
        repairable = score >= self.repair_threshold or bool(reasons)
        repair_prompt = build_reward_repair_instruction(stage, metric_scores, reasons)

        return ProcessReward(
            score=score,
            accept=accept,
            repairable=repairable,
            metric_scores=metric_scores,
            reasons=reasons,
            repair_prompt=repair_prompt,
            judge="heuristic",
            raw={"weights": weights, "base_score": round(base_score, 4), "magic_score": round(magic_score, 4) if magic_score is not None else None},
        )


class LLMJudgePRM:
    def __init__(
        self,
        provider: BaseProvider,
        model: str,
        accept_threshold: float,
        repair_threshold: float,
        temperature: Optional[float],
        max_tokens: int,
    ) -> None:
        self.provider = provider
        self.model = model
        self.accept_threshold = accept_threshold
        self.repair_threshold = repair_threshold
        self.temperature = temperature
        self.max_tokens = max_tokens

    def score(self, state: ChainState, stage: StageSpec, candidate: CandidateStep) -> ProcessReward:
        prompt = build_llm_judge_prompt(state, stage, candidate)
        result = self.provider.generate(
            ChatRequest(
                model=self.model,
                system=PRM_JUDGE_SYSTEM,
                prompt=prompt,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
        )
        try:
            data = extract_json_object(result.text)
        except Exception as exc:
            return ProcessReward(
                score=0.0,
                accept=False,
                repairable=True,
                metric_scores={},
                reasons=[f"judge JSON parse failed: {exc}"],
                repair_prompt="Rewrite the step more concretely and preserve visible symbols.",
                judge=f"llm:{result.provider}",
                raw={"text": result.text, "usage": result.usage},
            )
        reward = normalize_judge_payload(
            data=data,
            judge=f"llm:{result.provider}",
            accept_threshold=self.accept_threshold,
            repair_threshold=self.repair_threshold,
        )
        reward.raw["usage"] = result.usage
        return reward


class HybridPRM:
    def __init__(self, heuristic: HeuristicPRM, llm: LLMJudgePRM, llm_weight: float) -> None:
        self.heuristic = heuristic
        self.llm = llm
        self.llm_weight = clamp01(llm_weight)

    def score(self, state: ChainState, stage: StageSpec, candidate: CandidateStep) -> ProcessReward:
        h = self.heuristic.score(state, stage, candidate)
        l = self.llm.score(state, stage, candidate)
        score = round(clamp01((1.0 - self.llm_weight) * h.score + self.llm_weight * l.score), 4)
        metric_scores = dict(h.metric_scores)
        for key, value in l.metric_scores.items():
            if key in metric_scores:
                metric_scores[key] = round((1.0 - self.llm_weight) * metric_scores[key] + self.llm_weight * value, 4)
            else:
                metric_scores[key] = value
        reasons = []
        if h.reasons:
            reasons.extend(f"heuristic: {r}" for r in h.reasons)
        if l.reasons:
            reasons.extend(f"llm: {r}" for r in l.reasons)
        return ProcessReward(
            score=score,
            accept=score >= self.heuristic.accept_threshold and h.accept and l.accept,
            repairable=h.repairable or l.repairable,
            metric_scores=metric_scores,
            reasons=reasons,
            repair_prompt=l.repair_prompt or h.repair_prompt,
            judge="hybrid",
            raw={"heuristic": json_safe(h), "llm": json_safe(l), "llm_weight": self.llm_weight},
        )


def normalize_judge_payload(data: Dict[str, Any], judge: str, accept_threshold: float, repair_threshold: float) -> ProcessReward:
    score = clamp01(float(data.get("score", 0.0)))
    raw_metric_scores = data.get("metric_scores", {})
    metric_scores: Dict[str, float] = {}
    if isinstance(raw_metric_scores, dict):
        for key, value in raw_metric_scores.items():
            try:
                metric_scores[str(key)] = round(clamp01(float(value)), 4)
            except Exception:
                continue
    reasons_raw = data.get("reasons", [])
    if isinstance(reasons_raw, str):
        reasons = [reasons_raw]
    elif isinstance(reasons_raw, list):
        reasons = [str(x) for x in reasons_raw]
    else:
        reasons = []
    repair_prompt = data.get("repair_prompt")
    if repair_prompt is not None:
        repair_prompt = str(repair_prompt).strip() or None
    repairable = bool(data.get("repairable", score >= repair_threshold or bool(reasons)))
    accept = bool(data.get("accept", score >= accept_threshold))
    return ProcessReward(
        score=round(score, 4),
        accept=accept,
        repairable=repairable,
        metric_scores=metric_scores,
        reasons=reasons,
        repair_prompt=repair_prompt,
        judge=judge,
        raw={"payload": json_safe(data)},
    )


def build_reward_repair_instruction(stage: StageSpec, metric_scores: Dict[str, float], reasons: Sequence[str]) -> str:
    weak = sorted(metric_scores.items(), key=lambda kv: kv[1])[:3]
    weak_text = ", ".join(f"{k}={v:.2f}" for k, v in weak)
    reason_text = "; ".join(reasons) if reasons else "score below target"
    return (
        f"Repair this visible output for stage '{stage.name}' / role '{stage.role}'. "
        f"Main issues: {reason_text}. Weak reward axes: {weak_text}. "
        "Keep the strongest concrete image, preserve seed-linked symbols, reduce generic abstraction, "
        "and return only the repaired literary output."
    )


# ---------------------------------------------------------------------------
# Routing, parsing, prompts
# ---------------------------------------------------------------------------


def parse_provider_list(value: str) -> List[str]:
    providers = [part.strip().lower() for part in value.split(",") if part.strip()]
    if not providers:
        raise argparse.ArgumentTypeError("At least one provider is required.")
    unknown = [p for p in providers if p not in PROVIDER_NAMES]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"Unknown provider(s): {', '.join(unknown)}. Choose from: {', '.join(PROVIDER_NAMES)}"
        )
    return providers


def parse_model_overrides(items: Sequence[str]) -> Dict[str, str]:
    models = dict(DEFAULT_MODELS)
    for item in items:
        if "=" not in item:
            raise argparse.ArgumentTypeError("--model must be in provider=model form, e.g. openai=gpt-5.5")
        provider, model = item.split("=", 1)
        provider = provider.strip().lower()
        model = model.strip()
        if provider not in PROVIDER_NAMES:
            raise argparse.ArgumentTypeError(f"Unknown provider in --model: {provider}")
        if not model:
            raise argparse.ArgumentTypeError(f"Empty model for provider: {provider}")
        models[provider] = model
    return models


def parse_role_provider_overrides(items: Sequence[str]) -> Dict[str, str]:
    role_map = dict(DEFAULT_ROLE_PROVIDERS)
    for item in items:
        if "=" not in item:
            raise argparse.ArgumentTypeError("--role-provider must be in role=provider form, e.g. integrator=openai")
        role, provider = item.split("=", 1)
        role = role.strip().lower()
        provider = provider.strip().lower()
        if role not in ROLES:
            raise argparse.ArgumentTypeError(f"Unknown role: {role}. Choose from: {', '.join(ROLES)}")
        if provider not in PROVIDER_NAMES:
            raise argparse.ArgumentTypeError(f"Unknown provider for role {role}: {provider}")
        role_map[role] = provider
    return role_map


def load_stages(path: Optional[str], preset: str = "default") -> List[StageSpec]:
    if not path:
        if preset == "seed-independent-magic":
            return list(SEED_INDEPENDENT_MAGIC_STAGES)
        return list(DEFAULT_STAGES)
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("stages file must be a JSON list")
    stages: List[StageSpec] = []
    for idx, item in enumerate(data, start=1):
        if not isinstance(item, dict) or "name" not in item or "instruction" not in item:
            raise ValueError(f"stages file item {idx} must contain name and instruction")
        role = str(item.get("role", "expander")).strip().lower()
        if role not in ROLES:
            raise ValueError(f"stages file item {idx} has unknown role {role!r}; choose from {', '.join(ROLES)}")
        stages.append(
            StageSpec(
                name=str(item["name"]),
                role=role,
                instruction=str(item["instruction"]),
                operator=str(item.get("operator", "")),
            )
        )
    if not stages:
        raise ValueError("stages file must contain at least one stage")
    return stages


def read_seed(args: argparse.Namespace) -> str:
    if args.prompt_file:
        seed = Path(args.prompt_file).read_text(encoding="utf-8")
    elif args.prompt:
        seed = args.prompt
    else:
        if sys.stdin.isatty():
            raise ValueError("Provide --prompt, --prompt-file, or pipe text via stdin.")
        seed = sys.stdin.read()
    seed = seed.strip()
    if not seed:
        raise ValueError("Prompt is empty.")
    return seed


def default_magic_realism_prior() -> MagicRealismPrior:
    return MagicRealismPrior()


def has_any(text: str, terms: Iterable[str]) -> bool:
    lower = text.lower()
    return any(term.lower() in lower for term in terms if term)


def unique_keep_order(items: Iterable[str], limit: int = 12) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        out.append(value)
        seen.add(value)
        if len(out) >= limit:
            break
    return out


def extract_prompt_anchor_profile(seed: str) -> PromptAnchorProfile:
    text = str(seed or "")
    anchors: List[str] = []
    actions: List[str] = []
    objects: List[str] = []
    pressures: List[str] = []
    setting = "日常の用事"

    if has_any(text, ("会社", "職場", "出勤", "通勤", "office", "work")):
        setting = "平日の通勤と会社"
        anchors.extend(["朝", "会社", "通勤", "駅", "職場"])
        actions.extend(["家を出る", "改札を通る", "エレベーターに乗る", "席に着く", "タイムカードを押す"])
        objects.extend(["靴", "鞄", "社員証", "定期券", "改札", "エレベーター", "タイムカード", "机"])
        pressures.extend(["遅刻しそう", "眠い", "会議がある"])
    if has_any(text, ("朝", "morning")):
        anchors.append("朝")
        actions.extend(["顔を洗う", "時計を見る", "駅へ向かう"])
        objects.extend(["目覚まし時計", "歯ブラシ", "弁当", "駅の時計"])
        pressures.append("時間が少ない")
    if has_any(text, ("学校", "授業", "school")):
        setting = "学校の朝"
        anchors.extend(["学校", "教室", "連絡帳"])
        actions.extend(["登校する", "靴箱を開ける", "出席を取る"])
        objects.extend(["上履き", "連絡帳", "黒板", "チャイム"])
    if has_any(text, ("病院", "hospital")):
        setting = "病院の待合"
        anchors.extend(["病院", "待合室", "受付"])
        actions.extend(["番号札を取る", "問診票を書く", "会計を待つ"])
        objects.extend(["診察券", "問診票", "体温計", "領収書"])
    if has_any(text, ("買", "店", "shop", "market")):
        setting = "店と買い物"
        anchors.extend(["商店街", "店", "レジ"])
        actions.extend(["値札を見る", "支払う", "袋に入れる"])
        objects.extend(["財布", "レシート", "値札", "買い物袋"])
    if has_any(text, ("雨", "傘", "rain")):
        anchors.append("雨")
        objects.extend(["傘", "濡れた床", "窓"])
        actions.append("傘をたたむ")

    if not anchors:
        anchors.extend(tokenize_text(text)[:4])
    if not actions:
        actions.extend(["家を出る", "用事を済ませる", "窓口で待つ"])
    if not objects:
        objects.extend(["靴", "鞄", "時計", "書類", "財布", "傘"])
    if not pressures:
        pressures.extend(["時間が少ない", "用事が残っている"])

    anchors = unique_keep_order(anchors, limit=12)
    actions = unique_keep_order(actions, limit=10)
    objects = unique_keep_order(objects, limit=12)
    pressures = unique_keep_order(pressures, limit=6)
    slot_objects = objects[:5] or ["書類", "時計", "靴"]
    impossible_slots = unique_keep_order(
        [
            f"{slot_objects[0]}が前日の声を薄く残している",
            "改札が通る人の名前を一文字だけ先に印字する",
            "エレベーターが存在しない階を一度だけ通過する",
            "社員証の写真が午前中だけ昨日の顔になる",
            "時計の針が雨の日だけ押印の音に合わせて進む",
            f"{slot_objects[-1]}の端に、まだ起きていない用事の跡がつく",
        ],
        limit=8,
    )
    return PromptAnchorProfile(
        mundane_anchors=anchors,
        social_setting=setting,
        routine_actions=actions,
        ordinary_objects=objects,
        emotional_pressure=pressures,
        impossible_fact_slots=impossible_slots,
    )


def anchor_seed_symbols(profile: Optional[PromptAnchorProfile], limit: int = 8) -> List[str]:
    if not profile:
        return []
    return unique_keep_order(
        list(profile.mundane_anchors) + list(profile.ordinary_objects) + list(profile.routine_actions),
        limit=limit,
    )


def format_anchor_profile(profile: Optional[PromptAnchorProfile]) -> str:
    if not profile:
        return "PromptAnchorProfile: inactive."
    payload = {
        "mundane_anchors": profile.mundane_anchors,
        "social_setting": profile.social_setting,
        "routine_actions": profile.routine_actions,
        "ordinary_objects": profile.ordinary_objects,
        "emotional_pressure": profile.emotional_pressure,
        "impossible_fact_slots": profile.impossible_fact_slots,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def format_magic_realism_prior(prior: Optional[MagicRealismPrior], profile: Optional[PromptAnchorProfile] = None) -> str:
    if not prior:
        return "MagicRealismPrior: inactive."
    profile_block = format_anchor_profile(profile)
    return f"""
MagicRealismPrior:
- Treat magic realism as ontology, not style: the impossible fact is materially real inside ordinary social life.
- Keep the scene in a mundane setting: kitchen, station, office, street, apartment, school, shop, hospital, town hall, bus stop, market, or family home.
- Do not make the scene fantasy, science fiction, horror, myth, dream logic, hallucination, or metaphor-only lyricism.
- Characters may notice, avoid, adapt to, or quietly disagree about the impossible fact, but they should not explain it with a magic system.
- Social reality continues: routines, paperwork, food, clocks, family habits, local customs, procedures, transport, work, and weather still matter.
- Prefer one small impossible fact, ordinary people, restrained tone, concrete objects, recurring gestures, unresolved symbolic pressure, and no explicit explanation.
- Avoid wizards, spells, portals, chosen ones, fantasy races, cosmic prophecy, dream reveal, hallucination reveal, and over-explaining the supernatural.

Prior weights:
{json.dumps(dataclasses.asdict(prior), ensure_ascii=False, indent=2)}

Anchor profile:
{profile_block}
""".strip()


class RoleRouter:
    def __init__(self, providers: Sequence[str], role_providers: Dict[str, str], routing: str) -> None:
        self.providers = list(providers)
        self.role_providers = dict(role_providers)
        self.routing = routing

    def provider_for(self, role: str, index_zero_based: int) -> str:
        if not self.providers:
            raise ProviderError("No providers configured.")
        if self.routing == "round-robin":
            return self.providers[index_zero_based % len(self.providers)]
        wanted = self.role_providers.get(role)
        if wanted in self.providers:
            return wanted
        if "openai" in self.providers:
            return "openai"
        return self.providers[0]

    def candidate_providers_for(self, role: str, index_zero_based: int, count: int) -> List[str]:
        first = self.provider_for(role, index_zero_based)
        ordered = [first] + [p for p in self.providers if p != first]
        if not ordered:
            raise ProviderError("No providers configured.")
        selected: List[str] = []
        for i in range(max(1, count)):
            selected.append(ordered[i % len(ordered)])
        return selected


def format_metrics(metrics: Dict[str, float]) -> str:
    if not metrics:
        return "(none yet)"
    keys = [
        "drift_score",
        "novelty_score",
        "repetition_score",
        "recurrence_score",
        "entropy_score",
        "collapse_score",
        "compression_ratio",
        "magic_realism_reward",
        "mundane_grounding_score",
        "quiet_impossibility_score",
        "non_explanation_score",
        "social_normalization_score",
        "ordinary_continuity_score",
    ]
    return ", ".join(f"{key}={metrics[key]}" for key in keys if key in metrics)


def format_reward(reward: Optional[ProcessReward]) -> str:
    if not reward:
        return "(not scored)"
    bits = [f"score={reward.score:.4f}", f"accept={reward.accept}", f"repairable={reward.repairable}", f"judge={reward.judge}"]
    if reward.metric_scores:
        axes = ", ".join(f"{k}={v:.2f}" for k, v in sorted(reward.metric_scores.items()))
        bits.append(f"axes=[{axes}]")
    if reward.reasons:
        bits.append("reasons=" + "; ".join(reward.reasons))
    return " | ".join(bits)


def format_stage_outputs(records: Sequence[ProcessStepRecord], max_chars: int) -> str:
    chunks: List[str] = []
    for rec in records:
        cand = rec.accepted
        reward = cand.reward.score if cand.reward else None
        chunks.append(
            f"### {rec.index}. {rec.name} / role={rec.role} / operator={rec.operator}\n"
            f"selected_provider: {cand.provider}\n"
            f"selected_reward: {reward}\n"
            f"metrics: {format_metrics(cand.metrics)}\n"
            f"symbols: {', '.join(cand.symbols_after) if cand.symbols_after else '(none)'}\n"
            f"output:\n{cand.output}"
        )
    return clip_text("\n\n".join(chunks), max_chars=max_chars)


def build_stage_prompt(
    state: ChainState,
    stage: StageSpec,
    index: int,
    total: int,
    candidate_variant: int,
    max_context_chars: int,
    memory_context: str = "No prior run memory is active for this stage.",
) -> str:
    symbols = ", ".join(state.symbols) if state.symbols else "(none yet)"
    notes = "\n".join(f"- {note}" for note in state.control_notes) if state.control_notes else "- No adaptive control note yet."
    state_memory_notes = "\n".join(f"- {note}" for note in state.memory_notes) if state.memory_notes else "- No path-local memory note yet."
    prefix_line = ""
    prefix = state.constraints.get("required_prefix")
    if prefix:
        prefix_line = f"\nRequired prefix constraint: begin the visible output exactly with {prefix!r}."
    magic_context = ""
    if state.magic_prior:
        magic_context = f"\n\nMagic realism ontology and anchor profile:\n{format_magic_realism_prior(state.magic_prior, state.anchor_profile)}"

    variant_lines = {
        1: "Candidate variant: 1\nBias: balanced; preserve continuity and produce a strong default transition.",
        2: "Candidate variant: 2\nBias: bolder imagery; increase novelty while keeping symbols stable.",
        3: "Candidate variant: 3\nBias: quieter control; reduce drift and emphasize sensory grounding.",
        4: "Candidate variant: 4\nBias: structural compression; sharpen causality without explaining the magic.",
    }
    variant = variant_lines.get(
        candidate_variant,
        f"Candidate variant: {candidate_variant}\nBias: make a distinct but controlled visible transition.",
    )

    return f"""
Seed:
{clip_text(state.seed, max_context_chars // 3)}

Current ChainState:
- symbols: {symbols}
- metrics: {format_metrics(state.metrics)}
- constraints: {json.dumps(state.constraints, ensure_ascii=False)}
{magic_context}

RPM matrix context:
{format_rpm_context(state.rpm_trace)}

Adaptive control notes for this stage:
{notes}

Run memory context:
{memory_context}

Path-local memory notes:
{state_memory_notes}

Current visible text:
{clip_text(state.text, max_context_chars)}

Stage: {stage.name}
Role: {stage.role}
Operator: {stage.operator or '(unspecified)'}
Stage {index}/{total}
{variant}

Instruction:
{stage.instruction}{prefix_line}

Return only this candidate's visible literary output. Do not include analysis notes,
private reasoning, bullet-point plans, metric commentary, or hidden chain-of-thought.
""".strip()


def build_repair_prompt(
    state: ChainState,
    stage: StageSpec,
    failed: CandidateStep,
    reward: ProcessReward,
    max_context_chars: int,
) -> str:
    reasons = "\n".join(f"- {r}" for r in reward.reasons) if reward.reasons else "- reward below target"
    metric_scores = json.dumps(reward.metric_scores, ensure_ascii=False, indent=2)
    repair_instruction = reward.repair_prompt or build_reward_repair_instruction(stage, reward.metric_scores, reward.reasons)
    magic_context = ""
    if state.magic_prior:
        magic_context = f"\n\nMagic realism ontology and anchor profile:\n{format_magic_realism_prior(state.magic_prior, state.anchor_profile)}"
    return f"""
Seed:
{clip_text(state.seed, max_context_chars // 3)}

Previous stable visible text:
{clip_text(state.text, max_context_chars)}
{magic_context}

Rejected candidate output:
{clip_text(failed.output, max_context_chars)}

Observed process reward:
- total_score: {reward.score}
- accept: {reward.accept}
- repairable: {reward.repairable}
- metric_scores: {metric_scores}
- reasons:
{reasons}

Stage: {stage.name}
Role: {stage.role}
Operator: {stage.operator or '(unspecified)'}
Instruction:
{stage.instruction}

Repair instruction:
{repair_instruction}

Rewrite the rejected output as a stronger visible literary output.
Return only the repaired literary output. Do not mention metrics, scoring, PRM, or this repair process.
""".strip()


def build_aggregation_prompt(state: ChainState, max_context_chars: int) -> str:
    stage_outputs = format_stage_outputs(state.step_history, max_chars=max_context_chars)
    symbols = ", ".join(state.symbols) if state.symbols else "(none)"
    magic_context = ""
    if state.magic_prior:
        magic_context = f"\n\nMagic realism ontology and anchor profile:\n{format_magic_realism_prior(state.magic_prior, state.anchor_profile)}"
    return f"""
Seed:
{clip_text(state.seed, max_context_chars // 3)}

Accepted visible process path:
{stage_outputs}

Final ChainState summary:
- symbols: {symbols}
- latest metrics: {format_metrics(state.metrics)}
- constraints: {json.dumps(state.constraints, ensure_ascii=False)}
{magic_context}

RPM matrix context:
{format_rpm_context(state.rpm_trace, max_rules=10, max_conflicts=8, max_rows=8)}

Stage: 再統合：PRM accepted pathから最終稿へ
Role: integrator
Operator: aggregate_high_reward_path

Task:
Reintegrate all accepted process steps into a single finished short prose piece or opening scene.
Do not simply continue the last stage. Select the strongest material from the entire accepted path.
Keep the impossible fact ordinary, preserve symbolic recurrence, and reduce over-explanation.
If a magic realism prior is active, treat the impossible fact as materially real inside ordinary social life, not as fantasy, dream, revelation, consolation, or lore.
Target length: 700〜1200 Japanese characters, or an equivalent compact length in the requested language.

Return only the finished literary draft. Do not include analysis notes or hidden chain-of-thought.
""".strip()


def build_recursive_closure_prompt(state: ChainState, aggregate_text: str, max_context_chars: int) -> str:
    symbols = ", ".join(state.symbols) if state.symbols else "(none)"
    magic_context = ""
    if state.magic_prior:
        magic_context = f"\n\nMagic realism ontology and anchor profile:\n{format_magic_realism_prior(state.magic_prior, state.anchor_profile)}"
    return f"""
Original seed:
{clip_text(state.seed, max_context_chars // 3)}

Integrated draft:
{clip_text(aggregate_text, max_context_chars)}

State symbols:
{symbols}
{magic_context}

RPM matrix context:
{format_rpm_context(state.rpm_trace, max_rules=10, max_conflicts=8, max_rows=8)}

Stage: 再帰クロージャ：Seedへの帰還
Role: recursive
Operator: close_loop_to_seed

Task:
Close the loop. Rewrite the integrated draft so that the original seed returns in transformed form.
The return should feel inevitable, not explained. Keep the strongest concrete images.
Preserve continuity, reduce drift if the draft wandered, and avoid mechanical repetition.
The final paragraph or final image should echo the seed without copying it flatly.
If a magic realism prior is active, close through ordinary continuity: work, errands, paperwork, transport, food, weather, or another routine continues after the impossible fact.

Return only the final literary output. Do not include analysis notes or hidden chain-of-thought.
""".strip()


def build_llm_judge_prompt(state: ChainState, stage: StageSpec, candidate: CandidateStep) -> str:
    return f"""
Return JSON only with this schema:
{{
  "score": 0.0,
  "accept": false,
  "repairable": true,
    "metric_scores": {{
    "grounding": 0.0,
    "controlled_perturbation": 0.0,
    "symbol_recurrence": 0.0,
    "drift_control": 0.0,
    "novelty": 0.0,
    "repetition_control": 0.0,
    "collapse_control": 0.0,
    "integration": 0.0,
    "closure": 0.0,
    "mundane_grounding": 0.0,
    "quiet_impossibility": 0.0,
    "non_explanation": 0.0,
    "social_normalization": 0.0,
    "anti_fantasy": 0.0,
    "concrete_object": 0.0,
    "symbolic_pressure": 0.0,
    "ordinary_continuity": 0.0,
    "magic_realism": 0.0
  }},
  "reasons": ["brief visible reason"],
  "repair_prompt": "brief repair instruction or null"
}}

Evaluation target:
Score the candidate as a visible process step, not as hidden reasoning.
A good step should satisfy the stage role, preserve seed-linked symbols, control drift, avoid generic abstraction,
and move the state forward.
If MagicRealismPrior is active, additionally reward mundane grounding, one quiet material impossibility,
social normalization, concrete objects, ordinary continuity, and restraint; penalize fantasy lore,
dream reveal, hallucination reveal, cosmic explanation, and over-explained supernatural logic.

Seed:
{clip_text(state.seed, 2200)}

Previous visible text:
{clip_text(state.text, 3000)}

Current symbols:
{', '.join(state.symbols) if state.symbols else '(none)'}

Magic realism context:
{format_magic_realism_prior(state.magic_prior, state.anchor_profile) if state.magic_prior else 'inactive'}

Stage:
- name: {stage.name}
- role: {stage.role}
- operator: {stage.operator or '(unspecified)'}
- instruction: {stage.instruction}

Candidate metrics measured locally:
{json.dumps(candidate.metrics, ensure_ascii=False, indent=2)}

Candidate output:
{clip_text(candidate.output, 3500)}
""".strip()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class SpiralRpmPrmRunnerV5:
    def __init__(
        self,
        providers: Sequence[str],
        models: Dict[str, str],
        role_providers: Dict[str, str],
        routing: str,
        stages: Sequence[StageSpec],
        system: str,
        constraints: ChainConstraints,
        temperature: Optional[float],
        max_tokens: int,
        dry_run: bool,
        include_prompts: bool,
        candidates: int,
        prm_mode: str,
        accept_threshold: float,
        repair_threshold: float,
        repair_attempts: int,
        judge_provider: Optional[str],
        judge_model: Optional[str],
        judge_temperature: Optional[float],
        judge_max_tokens: int,
        hybrid_llm_weight: float,
        aggregate: bool,
        recursive_closure: bool,
        max_context_chars: int,
        beam_width: int = 1,
        beam_branching: int = 0,
        beam_archive: int = 8,
        memory_profile_path: Optional[str] = None,
        save_memory_profile_path: Optional[str] = None,
        memory_weight: float = 0.25,
        memory_update: bool = True,
        magic_prior: Optional[MagicRealismPrior] = None,
        anchor_profile: Optional[PromptAnchorProfile] = None,
    ) -> None:
        self.provider_names = list(providers)
        self.models = models
        self.role_providers = role_providers
        self.routing = routing
        self.router = RoleRouter(providers, role_providers, routing)
        self.stages = list(stages)
        self.system = system
        self.constraints = constraints
        self.rpm_observer = RPMObserver(constraints)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.dry_run = dry_run
        self.include_prompts = include_prompts
        self.candidates = max(1, candidates)
        self.prm_mode = prm_mode
        self.accept_threshold = accept_threshold
        self.repair_threshold = repair_threshold
        self.repair_attempts = max(0, repair_attempts)
        self.judge_provider_name = judge_provider
        self.judge_model = judge_model
        self.judge_temperature = judge_temperature
        self.judge_max_tokens = judge_max_tokens
        self.hybrid_llm_weight = hybrid_llm_weight
        self.aggregate = aggregate
        self.recursive_closure = recursive_closure
        self.max_context_chars = max_context_chars
        self.beam_width = max(1, beam_width)
        self.beam_branching = max(1, beam_branching or self.beam_width)
        self.beam_archive_limit = max(0, beam_archive)
        self.memory_profile_path = memory_profile_path
        self.save_memory_profile_path = save_memory_profile_path or memory_profile_path
        self.memory_weight = clamp01(memory_weight)
        self.memory_update = memory_update
        self.magic_prior = magic_prior
        self.anchor_profile = anchor_profile
        self.memory_profile = load_memory_profile(memory_profile_path)
        self.memory_profile_before = profile_snapshot(self.memory_profile, limit=12)
        self.beam_archive_snapshots: List[BeamPathSnapshot] = []
        self._providers: Dict[str, BaseProvider] = {}
        self._prm: Optional[ProcessRewardModel] = None

    def get_provider(self, name: str) -> BaseProvider:
        if name not in self._providers:
            self._providers[name] = build_provider(name, dry_run=self.dry_run)
        return self._providers[name]

    def build_prm(self) -> ProcessRewardModel:
        if self._prm is not None:
            return self._prm
        heuristic = HeuristicPRM(
            constraints=self.constraints,
            accept_threshold=self.accept_threshold,
            repair_threshold=self.repair_threshold,
        )
        if self.prm_mode == "heuristic":
            self._prm = heuristic
            return self._prm

        judge_name = self.judge_provider_name or self.default_judge_provider()
        judge_model = self.judge_model or self.models[judge_name]
        llm = LLMJudgePRM(
            provider=self.get_provider(judge_name),
            model=judge_model,
            accept_threshold=self.accept_threshold,
            repair_threshold=self.repair_threshold,
            temperature=self.judge_temperature,
            max_tokens=self.judge_max_tokens,
        )
        if self.prm_mode == "llm":
            self._prm = llm
        elif self.prm_mode == "hybrid":
            self._prm = HybridPRM(heuristic=heuristic, llm=llm, llm_weight=self.hybrid_llm_weight)
        else:
            raise ValueError(f"Unknown PRM mode: {self.prm_mode}")
        return self._prm

    def default_judge_provider(self) -> str:
        for preferred in ("anthropic", "openai", "google", "mistral"):
            if preferred in self.provider_names:
                return preferred
        if not self.provider_names:
            raise ProviderError("No providers configured.")
        return self.provider_names[0]

    def provider_candidates_for_stage(self, role: str, index_zero_based: int, count: int) -> List[str]:
        providers = self.router.candidate_providers_for(role, index_zero_based, count)
        if self.memory_weight > 0 and int(self.memory_profile.get("run_count", 0) or 0) > 0:
            preferred = best_memory_provider_for_role(self.memory_profile, role, self.provider_names)
            if preferred and preferred in providers:
                providers = [preferred] + [p for p in providers if p != preferred]
            elif preferred and preferred in self.provider_names:
                providers = [preferred] + providers
        # Preserve requested candidate count after memory reordering.
        if not providers:
            return providers
        while len(providers) < max(1, count):
            providers.append(providers[len(providers) % len(providers)])
        return providers[: max(1, count)]

    def memory_context_for_stage(self, stage: StageSpec) -> str:
        return format_memory_context(
            self.memory_profile,
            role=stage.role,
            available_providers=self.provider_names,
            memory_weight=self.memory_weight,
        )

    def call_provider(self, provider_name: str, prompt: str) -> ChatResult:
        model = self.models[provider_name]
        request = ChatRequest(
            model=model,
            system=self.system,
            prompt=prompt,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        result = self.get_provider(provider_name).generate(request)
        if not result.text:
            raise ProviderError(f"{provider_name}: empty response")
        return result

    def make_candidate_from_result(
        self,
        state: ChainState,
        stage: StageSpec,
        index: int,
        candidate_id: str,
        result: ChatResult,
        prompt: str,
        repaired_from: Optional[str] = None,
        repair_attempt: int = 0,
    ) -> CandidateStep:
        symbols_after = merge_symbols(state.symbols, result.text, limit=self.constraints.symbol_limit)
        metrics = observe_transition(previous=state.text, current=result.text, symbols=symbols_after)
        if state.magic_prior:
            metrics.update(compute_magic_realism_metrics(result.text, state=state, stage=stage, transition_metrics=metrics))
        return CandidateStep(
            candidate_id=candidate_id,
            stage_index=index,
            stage_name=stage.name,
            role=stage.role,
            operator=stage.operator,
            provider=result.provider,
            model=result.model,
            output=result.text,
            metrics=metrics,
            symbols_before=list(state.symbols),
            symbols_after=symbols_after,
            reward=None,
            prompt=prompt if self.include_prompts else None,
            usage=result.usage,
            repaired_from=repaired_from,
            repair_attempt=repair_attempt,
        )

    def generate_candidates(
        self,
        state: ChainState,
        stage: StageSpec,
        index: int,
        total: int,
        branch_prefix: str = "",
    ) -> List[CandidateStep]:
        providers = self.provider_candidates_for_stage(stage.role, index - 1, self.candidates)
        candidates: List[CandidateStep] = []
        for offset, provider_name in enumerate(providers, start=1):
            prompt = build_stage_prompt(
                state=state,
                stage=stage,
                index=index,
                total=total,
                candidate_variant=offset,
                max_context_chars=self.max_context_chars,
                memory_context=self.memory_context_for_stage(stage),
            )
            result = self.call_provider(provider_name, prompt)
            candidate = self.make_candidate_from_result(
                state=state,
                stage=stage,
                index=index,
                candidate_id=f"{branch_prefix}s{index}-c{offset}-{provider_name}",
                result=result,
                prompt=prompt,
            )
            candidates.append(candidate)
        return candidates

    def score_candidates(self, state: ChainState, stage: StageSpec, candidates: Sequence[CandidateStep]) -> None:
        prm = self.build_prm()
        for candidate in candidates:
            candidate.reward = prm.score(state, stage, candidate)

    def choose_candidate(self, candidates: Sequence[CandidateStep]) -> CandidateStep:
        if not candidates:
            raise ValueError("No candidates to choose from.")
        return max(candidates, key=lambda c: (c.reward.score if c.reward else -1.0, -c.metrics.get("collapse_score", 1.0)))

    def repair_candidate(
        self,
        state: ChainState,
        stage: StageSpec,
        index: int,
        failed: CandidateStep,
        attempt: int,
    ) -> Optional[CandidateStep]:
        if not failed.reward or not failed.reward.repairable:
            return None
        repair_provider = failed.provider
        prompt = build_repair_prompt(
            state=state,
            stage=stage,
            failed=failed,
            reward=failed.reward,
            max_context_chars=self.max_context_chars,
        )
        result = self.call_provider(repair_provider, prompt)
        repaired = self.make_candidate_from_result(
            state=state,
            stage=stage,
            index=index,
            candidate_id=f"{failed.candidate_id}-r{attempt}",
            result=result,
            prompt=prompt,
            repaired_from=failed.candidate_id,
            repair_attempt=attempt,
        )
        repaired.reward = self.build_prm().score(state, stage, repaired)
        return repaired

    def compute_path_score(self, state: ChainState) -> float:
        rewards = [step.accepted.reward.score if step.accepted.reward else 0.0 for step in state.step_history]
        if not rewards:
            return 0.0
        mean_reward = sum(rewards) / len(rewards)
        last_reward = rewards[-1]
        recurrence = state.metrics.get("recurrence_score", 0.0)
        collapse = state.metrics.get("collapse_score", 0.0)
        drift = state.metrics.get("drift_score", 0.0)
        magic = state.metrics.get("magic_realism_reward", 0.0)
        unresolved = len([c for c in state.rpm_trace.conflicts if not c.resolved])
        drift_penalty = max(0.0, drift - self.constraints.max_drift)
        score = (
            0.58 * mean_reward
            + 0.26 * last_reward
            + 0.10 * recurrence
            + 0.06 * state.metrics.get("entropy_score", 0.0)
            + (0.07 * magic if self.magic_prior else 0.0)
            - 0.08 * collapse
            - 0.06 * drift_penalty
            - 0.025 * unresolved
        )
        return round(clamp01(score), 5)

    def make_beam_snapshot(self, state: ChainState, stage_index: int) -> BeamPathSnapshot:
        rewards = [round(step.accepted.reward.score, 4) if step.accepted.reward else 0.0 for step in state.step_history]
        providers = [step.accepted.provider for step in state.step_history]
        unresolved = len([c for c in state.rpm_trace.conflicts if not c.resolved])
        return BeamPathSnapshot(
            path_id=state.path_id,
            stage_index=stage_index,
            score=state.path_score,
            rewards=rewards,
            providers=providers,
            symbols=list(state.symbols[:12]),
            unresolved_conflicts=unresolved,
            final_text_preview=clip_text(state.text.replace("\n", " "), 360),
        )

    def remember_beam_states(self, states: Sequence[ChainState], stage_index: int) -> None:
        if self.beam_archive_limit <= 0:
            return
        for state in states:
            self.beam_archive_snapshots.append(self.make_beam_snapshot(state, stage_index=stage_index))
        self.beam_archive_snapshots = sorted(
            self.beam_archive_snapshots,
            key=lambda snap: (snap.score, len(snap.rewards)),
            reverse=True,
        )[: self.beam_archive_limit]

    def apply_selected_step(
        self,
        state: ChainState,
        stage: StageSpec,
        index: int,
        best: CandidateStep,
        candidates: Sequence[CandidateStep],
        repaired: Sequence[CandidateStep],
    ) -> ProcessStepRecord:
        metrics_before = dict(state.metrics)
        rejected_by_id: Dict[str, CandidateStep] = {}
        for candidate in list(candidates) + list(repaired):
            if candidate.candidate_id != best.candidate_id:
                rejected_by_id[candidate.candidate_id] = candidate
        if best.repaired_from:
            for candidate in candidates:
                if candidate.candidate_id == best.repaired_from:
                    rejected_by_id[candidate.candidate_id] = candidate

        notes = make_control_notes(best.metrics, best.symbols_after, self.constraints, best.output)
        rpm_cell = self.rpm_observer.update(state, stage, best, metrics_before=metrics_before)
        unresolved = [c for c in state.rpm_trace.conflicts if not c.resolved]
        if unresolved:
            for conflict in unresolved[-3:]:
                notes.append(f"RPM conflict {conflict.conflict_id}: {conflict.repair_instruction}")
        record = ProcessStepRecord(
            index=index,
            name=stage.name,
            role=stage.role,
            operator=stage.operator,
            accepted=best,
            rejected=list(rejected_by_id.values()),
            repaired=list(repaired),
            control_notes_for_next=notes,
        )
        _ = rpm_cell
        parent_path = state.path_id or "root"
        state.text = best.output
        state.symbols = best.symbols_after
        state.metrics = best.metrics
        state.control_notes = notes
        state.step_history.append(record)
        state.path_id = f"{parent_path}>{best.candidate_id}"
        state.path_score = self.compute_path_score(state)
        state.memory_notes = [
            f"path_score={state.path_score:.5f}",
            f"last_provider={best.provider}",
            f"last_reward={best.reward.score if best.reward else 0.0:.4f}",
        ]
        return record

    def accept_step(self, state: ChainState, stage: StageSpec, index: int, candidates: List[CandidateStep]) -> ProcessStepRecord:
        self.score_candidates(state, stage, candidates)
        repaired: List[CandidateStep] = []
        best = self.choose_candidate(candidates)

        for attempt in range(1, self.repair_attempts + 1):
            if best.reward and best.reward.accept:
                break
            candidate = self.repair_candidate(state, stage, index, best, attempt)
            if not candidate:
                break
            repaired.append(candidate)
            if candidate.reward and (not best.reward or candidate.reward.score >= best.reward.score):
                best = candidate

        return self.apply_selected_step(state, stage, index, best, candidates, repaired)

    def expand_state_for_beam_stage(
        self,
        state: ChainState,
        stage: StageSpec,
        index: int,
        total: int,
        branch_index: int,
    ) -> List[ChainState]:
        branch_prefix = f"b{branch_index}-"
        candidates = self.generate_candidates(state, stage, index, total, branch_prefix=branch_prefix)
        self.score_candidates(state, stage, candidates)
        ranked = sorted(
            candidates,
            key=lambda c: (c.reward.score if c.reward else -1.0, -c.metrics.get("collapse_score", 1.0)),
            reverse=True,
        )
        expansions: List[ChainState] = []
        for selected in ranked[: min(self.beam_branching, len(ranked))]:
            local_best = selected
            repaired: List[CandidateStep] = []
            for attempt in range(1, self.repair_attempts + 1):
                if local_best.reward and local_best.reward.accept:
                    break
                candidate = self.repair_candidate(state, stage, index, local_best, attempt)
                if not candidate:
                    break
                repaired.append(candidate)
                if candidate.reward and (not local_best.reward or candidate.reward.score >= local_best.reward.score):
                    local_best = candidate
            new_state = copy.deepcopy(state)
            self.apply_selected_step(new_state, stage, index, copy.deepcopy(local_best), copy.deepcopy(candidates), copy.deepcopy(repaired))
            expansions.append(new_state)
        return expansions

    def run_beam_generation_stages(self, initial_state: ChainState, total_visible: int) -> ChainState:
        beam_states: List[ChainState] = [initial_state]
        for stage_index, stage in enumerate(self.stages, start=1):
            expanded: List[ChainState] = []
            for branch_index, state in enumerate(beam_states, start=1):
                expanded.extend(self.expand_state_for_beam_stage(state, stage, stage_index, total_visible, branch_index))
            if not expanded:
                raise ValueError(f"Beam expansion produced no candidates at stage {stage_index}.")
            expanded = sorted(expanded, key=lambda st: st.path_score, reverse=True)
            beam_states = expanded[: self.beam_width]
            self.remember_beam_states(beam_states, stage_index=stage_index)
        return sorted(beam_states, key=lambda st: st.path_score, reverse=True)[0]

    def run_prompt_stage(self, state: ChainState, stage: StageSpec, index: int, prompt: str) -> ProcessStepRecord:
        providers = self.provider_candidates_for_stage(stage.role, index - 1, self.candidates)
        candidates: List[CandidateStep] = []
        for offset, provider_name in enumerate(providers, start=1):
            prompt_with_variant = prompt + f"\n\nRun memory context:\n{self.memory_context_for_stage(stage)}\n\nCandidate variant: {offset}\nReturn a distinct but compatible version."
            result = self.call_provider(provider_name, prompt_with_variant)
            candidate = self.make_candidate_from_result(
                state=state,
                stage=stage,
                index=index,
                candidate_id=f"s{index}-c{offset}-{provider_name}",
                result=result,
                prompt=prompt_with_variant,
            )
            candidates.append(candidate)
        return self.accept_step(state, stage, index, candidates)

    def run_generation_stage(self, state: ChainState, stage: StageSpec, index: int, total: int) -> ProcessStepRecord:
        candidates = self.generate_candidates(state, stage, index, total)
        return self.accept_step(state, stage, index, candidates)

    def run(self, seed: str, language: str, seed_symbols: Sequence[str]) -> ChainRun:
        initial_symbols = merge_symbols(seed_symbols, seed, limit=self.constraints.symbol_limit)
        rpm_trace = RPMTrace()
        if self.magic_prior:
            rpm_trace.axes = list(rpm_trace.axes) + [
                "mundane_anchor",
                "quiet_impossibility",
                "non_explanation",
                "social_normalization",
                "fantasy_drift",
                "symbolic_pressure",
                "ordinary_continuity",
            ]
        state = ChainState(
            seed=seed,
            text=seed,
            symbols=initial_symbols,
            constraints=json_safe(dataclasses.asdict(self.constraints)),
            metrics={},
            control_notes=[],
            memory_notes=[
                f"memory_profile_runs={self.memory_profile.get('run_count', 0)}",
                f"beam_width={self.beam_width}",
            ],
            magic_prior=self.magic_prior,
            anchor_profile=self.anchor_profile,
            rpm_trace=rpm_trace,
            step_history=[],
            path_id="root",
            path_score=0.0,
        )

        total_visible = len(self.stages) + (1 if self.aggregate else 0) + (1 if self.recursive_closure else 0)
        if self.beam_width > 1:
            state = self.run_beam_generation_stages(state, total_visible=total_visible)
            stage_index = len(self.stages) + 1
        else:
            stage_index = 1
            for stage in self.stages:
                self.run_generation_stage(state, stage, index=stage_index, total=total_visible)
                self.remember_beam_states([state], stage_index=stage_index)
                stage_index += 1

        if self.aggregate:
            aggregation_stage = StageSpec(
                name="再統合：PRM accepted pathから最終稿へ",
                role="integrator",
                operator="aggregate_high_reward_path",
                instruction="全accepted pathを再統合して最終稿を作る。",
            )
            aggregation_prompt = build_aggregation_prompt(state, max_context_chars=self.max_context_chars * 2)
            self.run_prompt_stage(state, aggregation_stage, index=stage_index, prompt=aggregation_prompt)
            self.remember_beam_states([state], stage_index=stage_index)
            stage_index += 1

        if self.recursive_closure:
            closure_stage = StageSpec(
                name="再帰クロージャ：Seedへの帰還",
                role="recursive",
                operator="close_loop_to_seed",
                instruction="最終稿をSeedへ変形帰還させる。",
            )
            closure_prompt = build_recursive_closure_prompt(
                state,
                aggregate_text=state.text,
                max_context_chars=self.max_context_chars * 2,
            )
            self.run_prompt_stage(state, closure_stage, index=stage_index, prompt=closure_prompt)
            self.remember_beam_states([state], stage_index=stage_index)

        prm_config = PRMConfig(
            mode=self.prm_mode,
            candidates=self.candidates,
            accept_threshold=self.accept_threshold,
            repair_threshold=self.repair_threshold,
            judge_provider=self.judge_provider_name or (self.default_judge_provider() if self.prm_mode in ("llm", "hybrid") else None),
            judge_model=self.judge_model,
            hybrid_llm_weight=self.hybrid_llm_weight,
            include_prompts=self.include_prompts,
        )
        beam_config = BeamConfig(
            enabled=self.beam_width > 1,
            beam_width=self.beam_width,
            beam_branching=self.beam_branching,
            archive_limit=self.beam_archive_limit,
        )
        memory_before = dict(self.memory_profile_before)
        provisional_run = ChainRun(
            script="chain_of_magic_realism.py",
            version="5.0",
            started_at_utc=utc_now_iso(),
            language=language,
            seed=seed,
            providers=self.provider_names,
            routing=self.routing,
            role_providers={role: self.role_providers[role] for role in ROLES if role in self.role_providers},
            models={name: self.models[name] for name in self.provider_names},
            constraints=json_safe(dataclasses.asdict(self.constraints)),
            magic_prior=self.magic_prior,
            anchor_profile=self.anchor_profile,
            prm=prm_config,
            beam=beam_config,
            beam_archive=list(self.beam_archive_snapshots),
            memory_profile_path=self.save_memory_profile_path,
            memory_profile_before=memory_before,
            memory_profile_after=profile_snapshot(self.memory_profile, limit=12),
            final=state.text,
            final_state=state,
            rpm_trace=state.rpm_trace,
            steps=state.step_history,
        )
        if self.memory_update:
            self.memory_profile = update_memory_profile_from_run(self.memory_profile, provisional_run)
            save_memory_profile(self.save_memory_profile_path, self.memory_profile)
            provisional_run.memory_profile_after = profile_snapshot(self.memory_profile, limit=12)
        return provisional_run


# ---------------------------------------------------------------------------
# Rendering and CLI
# ---------------------------------------------------------------------------


def render_markdown(run: ChainRun, show_stages: bool = True, show_candidates: bool = False, show_rpm: bool = True) -> str:
    lines: List[str] = []
    lines.append("# Chain of Magic Realism Thought")
    lines.append("")
    lines.append(f"- Started UTC: `{run.started_at_utc}`")
    lines.append(f"- Language: `{run.language}`")
    lines.append(f"- Providers: `{', '.join(run.providers)}`")
    lines.append(f"- Routing: `{run.routing}`")
    lines.append(f"- PRM: `{run.prm.mode}` / candidates per stage: `{run.prm.candidates}`")
    lines.append(f"- Beam: `enabled={run.beam.enabled}, width={run.beam.beam_width}, branching={run.beam.beam_branching}`")
    lines.append(f"- Magic realism prior: `{'enabled' if run.magic_prior else 'disabled'}`")
    lines.append(f"- Path score: `{run.final_state.path_score}`")
    lines.append(f"- Memory profile: `{run.memory_profile_path or '(not saved)'}` / runs before→after: `{run.memory_profile_before.get('run_count', 0)}`→`{run.memory_profile_after.get('run_count', 0)}`")
    lines.append(f"- Final symbols: `{', '.join(run.final_state.symbols) if run.final_state.symbols else '(none)'}`")
    unresolved = [c for c in run.rpm_trace.conflicts if not c.resolved]
    lines.append(f"- Final metrics: `{format_metrics(run.final_state.metrics)}`")
    lines.append(f"- RPM rows/rules/conflicts: `{len(run.rpm_trace.matrix)}` / `{len(run.rpm_trace.inferred_rules)}` / `{len(run.rpm_trace.conflicts)}` total, `{len(unresolved)}` unresolved")
    lines.append("")
    lines.append("## Seed")
    lines.append("")
    lines.append(run.seed)
    lines.append("")

    if run.anchor_profile:
        lines.append("## Prompt anchor profile")
        lines.append("")
        lines.append("```json")
        lines.append(format_anchor_profile(run.anchor_profile))
        lines.append("```")
        lines.append("")

    if show_rpm:
        lines.append(format_rpm_markdown(run.rpm_trace))
        lines.append("")
    if run.beam_archive:
        lines.append("## Beam archive")
        lines.append("")
        lines.append("| score | stage | path | providers | symbols | unresolved |")
        lines.append("|---:|---:|---|---|---|---:|")
        for snap in run.beam_archive[: min(12, len(run.beam_archive))]:
            path = clip_text(snap.path_id, 80).replace("\n", " ")
            providers = " → ".join(snap.providers[-6:]) if snap.providers else "(none)"
            symbols = ", ".join(snap.symbols[:6]) if snap.symbols else "(none)"
            lines.append(f"| {snap.score:.5f} | {snap.stage_index} | `{path}` | `{providers}` | `{symbols}` | {snap.unresolved_conflicts} |")
        lines.append("")

    if run.memory_profile_after:
        lines.append("## Run memory snapshot")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(run.memory_profile_after, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")

    if show_stages:
        lines.append("## PRM-scored visible process path")
        lines.append("")
        for step in run.steps:
            cand = step.accepted
            lines.append(f"### {step.index}. {step.name}")
            lines.append("")
            lines.append(f"Role: `{step.role}`  ")
            lines.append(f"Operator: `{step.operator or '(unspecified)'}`  ")
            lines.append(f"Selected: `{cand.candidate_id}` by `{cand.provider}` / `{cand.model}`  ")
            if cand.repaired_from:
                lines.append(f"Repaired from: `{cand.repaired_from}` attempt `{cand.repair_attempt}`  ")
            lines.append(f"Reward: `{format_reward(cand.reward)}`  ")
            lines.append(f"Metrics: `{format_metrics(cand.metrics)}`  ")
            lines.append(f"Symbols: `{', '.join(cand.symbols_after) if cand.symbols_after else '(none)'}`")
            if step.control_notes_for_next:
                lines.append("")
                lines.append("Control notes for next stage:")
                for note in step.control_notes_for_next:
                    lines.append(f"- {note}")
            lines.append("")
            lines.append(cand.output)
            lines.append("")

            if show_candidates:
                if step.rejected:
                    lines.append("#### Rejected candidates")
                    lines.append("")
                    for rej in step.rejected:
                        lines.append(f"- `{rej.candidate_id}` by `{rej.provider}` score `{rej.reward.score if rej.reward else None}`")
                        if rej.reward and rej.reward.reasons:
                            lines.append(f"  - reasons: {'; '.join(rej.reward.reasons)}")
                    lines.append("")
                if step.repaired:
                    lines.append("#### Repair candidates")
                    lines.append("")
                    for rep in step.repaired:
                        lines.append(
                            f"- `{rep.candidate_id}` from `{rep.repaired_from}` by `{rep.provider}` "
                            f"score `{rep.reward.score if rep.reward else None}`"
                        )
                    lines.append("")

    lines.append("## Final")
    lines.append("")
    lines.append(run.final)
    lines.append("")
    return "\n".join(lines)


def save_outputs(
    run: ChainRun,
    output_json: Optional[str],
    output_md: Optional[str],
    show_stages: bool,
    show_candidates: bool,
    show_rpm: bool,
) -> None:
    if output_json:
        payload = json_safe(dataclasses.asdict(run))
        Path(output_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if output_md:
        Path(output_md).write_text(
            render_markdown(run, show_stages=show_stages, show_candidates=show_candidates, show_rpm=show_rpm),
            encoding="utf-8",
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provider-abstracted PRM-style visible-process magic-realism harness.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    provider_group = parser.add_mutually_exclusive_group()
    provider_group.add_argument(
        "--provider",
        choices=PROVIDER_NAMES,
        help="Single provider to make available. Role routing collapses to this provider.",
    )
    provider_group.add_argument(
        "--providers",
        type=parse_provider_list,
        default=None,
        help="Comma-separated providers made available to the router.",
    )
    parser.add_argument("--routing", choices=("role", "round-robin"), default="role", help="Provider routing mode.")
    parser.add_argument("--role-provider", action="append", default=[], help="Override role routing: role=provider")
    parser.add_argument("--model", action="append", default=[], help="Override model: provider=model")
    parser.add_argument("--prompt", "-p", help="Seed prompt text.")
    parser.add_argument("--prompt-file", help="Read seed prompt from a UTF-8 file.")
    parser.add_argument("--stages-file", help="JSON list of custom stages: [{name, role, operator, instruction}, ...].")
    parser.add_argument("--stage-preset", choices=("default", "seed-independent-magic"), default="default", help="Built-in stage preset to use when --stages-file is omitted.")
    parser.add_argument("--magic-realism-prior", action="store_true", help="Inject the ontology-level magic realism prior into system, stage, repair, and aggregation prompts.")
    parser.add_argument("--anchor-profile", choices=("off", "auto"), default="off", help="Build a PromptAnchorProfile from an ordinary prompt and use it as seed-independent mundane grounding.")
    parser.add_argument("--language", default="Japanese", help="Output language instruction.")
    parser.add_argument("--temperature", type=float, default=0.8, help="Sampling temperature. Use --no-temperature to omit.")
    parser.add_argument("--no-temperature", action="store_true", help="Do not send temperature to providers.")
    parser.add_argument("--max-tokens", type=int, default=1200, help="Max output tokens per generation call.")
    parser.add_argument("--max-context-chars", type=int, default=9000, help="Prompt clipping budget for current state text.")
    parser.add_argument("--seed-symbol", action="append", default=[], help="Manually seed a recurring symbol. Repeatable.")
    parser.add_argument("--symbol-limit", type=int, default=12, help="Maximum symbols kept in ChainState.")

    parser.add_argument("--max-drift", type=float, default=0.82, help="Adaptive-control upper bound for drift_score.")
    parser.add_argument("--min-drift", type=float, default=0.18, help="Adaptive-control lower bound for drift_score.")
    parser.add_argument("--max-repetition", type=float, default=0.28, help="Adaptive-control upper bound for repetition_score.")
    parser.add_argument("--min-recurrence", type=float, default=0.15, help="Adaptive-control lower bound for recurrence_score.")
    parser.add_argument("--min-novelty", type=float, default=0.18, help="Adaptive-control lower bound for novelty_score.")
    parser.add_argument("--max-collapse", type=float, default=0.55, help="Adaptive-control upper bound for collapse_score.")
    parser.add_argument("--required-prefix", help="Prompt-level prefix constraint for visible outputs.")

    parser.add_argument("--prm", choices=("heuristic", "llm", "hybrid"), default="heuristic", help="Process reward model mode.")
    parser.add_argument("--candidates", type=int, default=2, help="Candidate steps generated per stage before PRM selection.")
    parser.add_argument("--accept-threshold", type=float, default=0.62, help="PRM score threshold for immediate acceptance.")
    parser.add_argument("--repair-threshold", type=float, default=0.50, help="PRM score threshold below which a candidate may be too weak to repair.")
    parser.add_argument("--repair-attempts", type=int, default=1, help="Optional repair calls for low-reward selected candidates.")
    parser.add_argument("--judge-provider", choices=PROVIDER_NAMES, help="Provider used for LLM PRM judge in llm/hybrid mode.")
    parser.add_argument("--judge-model", help="Model used for LLM PRM judge. Defaults to the chosen judge provider model.")
    parser.add_argument("--judge-temperature", type=float, default=0.0, help="Sampling temperature for LLM judge.")
    parser.add_argument("--judge-max-tokens", type=int, default=900, help="Max output tokens for LLM judge calls.")
    parser.add_argument("--hybrid-llm-weight", type=float, default=0.45, help="LLM judge weight in hybrid PRM mode.")

    parser.add_argument("--no-aggregate", action="store_true", help="Disable aggregation stage.")
    parser.add_argument("--no-recursive-closure", action="store_true", help="Disable recursive closure stage.")

    parser.add_argument("--beam-width", type=int, default=1, help="Keep this many top process paths after each generation stage. 1 disables beam search.")
    parser.add_argument("--beam-branching", type=int, default=0, help="From each path, keep this many top candidates before pruning. 0 uses --beam-width.")
    parser.add_argument("--beam-archive", type=int, default=8, help="Number of high-scoring path snapshots kept in the report.")

    parser.add_argument("--memory-profile", help="Load a run-memory JSON profile and use it as a soft prior.")
    parser.add_argument("--save-memory-profile", help="Write updated run-memory JSON here. Defaults to --memory-profile when provided.")
    parser.add_argument("--memory-weight", type=float, default=0.25, help="Soft influence of run memory in prompts/provider ordering.")
    parser.add_argument("--no-memory-update", action="store_true", help="Load memory if present but do not update/save it after the run.")
    parser.add_argument("--output-json", help="Write the full run to JSON.")
    parser.add_argument("--output-md", help="Write a Markdown report.")
    parser.add_argument("--show-stages", action="store_true", help="Print all accepted visible state transitions, not only final.")
    parser.add_argument("--show-candidates", action="store_true", help="Print rejected and repaired candidate IDs in Markdown output.")
    parser.add_argument("--show-rpm", action="store_true", help="Print the RPM matrix, rule hypotheses, conflicts, and repair plans.")
    parser.add_argument("--include-prompts", action="store_true", help="Include rendered prompts in JSON output.")
    parser.add_argument("--dry-run", action="store_true", help="Use fake providers; no SDK imports or API calls.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        seed = read_seed(args)
        providers = args.providers or ([args.provider] if args.provider else ["openai"])
        models = parse_model_overrides(args.model)
        role_providers = parse_role_provider_overrides(args.role_provider)
        stages = load_stages(args.stages_file, preset=args.stage_preset)
        temperature = None if args.no_temperature else args.temperature
        judge_temperature = None if args.no_temperature else args.judge_temperature
        system = DEFAULT_SYSTEM_TEMPLATE.format(language=args.language)
        magic_prior = default_magic_realism_prior() if args.magic_realism_prior or args.stage_preset == "seed-independent-magic" else None
        anchor_profile = extract_prompt_anchor_profile(seed) if args.anchor_profile == "auto" else None
        if magic_prior:
            system = f"{system}\n\n{format_magic_realism_prior(magic_prior, anchor_profile)}"
        seed_symbols = list(args.seed_symbol)
        if anchor_profile and not seed_symbols:
            seed_symbols = anchor_seed_symbols(anchor_profile, limit=args.symbol_limit)
        constraints = ChainConstraints(
            max_drift=args.max_drift,
            min_drift=args.min_drift,
            max_repetition=args.max_repetition,
            min_recurrence=args.min_recurrence,
            min_novelty=args.min_novelty,
            max_collapse=args.max_collapse,
            required_prefix=args.required_prefix,
            symbol_limit=args.symbol_limit,
        )

        runner = SpiralRpmPrmRunnerV5(
            providers=providers,
            models=models,
            role_providers=role_providers,
            routing=args.routing,
            stages=stages,
            system=system,
            constraints=constraints,
            temperature=temperature,
            max_tokens=args.max_tokens,
            dry_run=args.dry_run,
            include_prompts=args.include_prompts,
            candidates=args.candidates,
            prm_mode=args.prm,
            accept_threshold=args.accept_threshold,
            repair_threshold=args.repair_threshold,
            repair_attempts=args.repair_attempts,
            judge_provider=args.judge_provider,
            judge_model=args.judge_model,
            judge_temperature=judge_temperature,
            judge_max_tokens=args.judge_max_tokens,
            hybrid_llm_weight=args.hybrid_llm_weight,
            aggregate=not args.no_aggregate,
            recursive_closure=not args.no_recursive_closure,
            max_context_chars=args.max_context_chars,
            beam_width=args.beam_width,
            beam_branching=args.beam_branching,
            beam_archive=args.beam_archive,
            memory_profile_path=args.memory_profile,
            save_memory_profile_path=args.save_memory_profile,
            memory_weight=args.memory_weight,
            memory_update=not args.no_memory_update,
            magic_prior=magic_prior,
            anchor_profile=anchor_profile,
        )
        run = runner.run(seed=seed, language=args.language, seed_symbols=seed_symbols)
        save_outputs(
            run,
            args.output_json,
            args.output_md,
            show_stages=True,
            show_candidates=args.show_candidates,
            show_rpm=True,
        )

        if args.show_stages or args.show_rpm:
            print(render_markdown(run, show_stages=args.show_stages, show_candidates=args.show_candidates, show_rpm=args.show_rpm or args.show_stages))
        else:
            print(run.final)

        if args.output_json or args.output_md:
            written = [p for p in (args.output_json, args.output_md) if p]
            print(f"\nWrote: {', '.join(written)}", file=sys.stderr)
        return 0

    except (ValueError, ProviderError, argparse.ArgumentTypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
