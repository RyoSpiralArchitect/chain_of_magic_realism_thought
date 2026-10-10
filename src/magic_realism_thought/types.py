from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

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
class OntologyEntry:
    kind: str
    name: str
    description: str
    producer: str
    status: str = "active"
    observed_count: int = 0
    last_seen_stage: Optional[str] = None


@dataclass
class OntologyLedger:
    entries: List[OntologyEntry] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class CandidateDecision:
    candidate_id: str
    status: str
    provider: str
    model: str
    score: Optional[float]
    reasons: List[str] = field(default_factory=list)
    repaired_from: Optional[str] = None


@dataclass
class DecisionFrontierItem:
    frontier_id: str
    kind: str
    source_id: str
    status: str
    reason: str
    next_action: str = ""
    score: Optional[float] = None


@dataclass
class DecisionLandscapeRecord:
    contract_version: str
    decision_id: str
    stage_index: int
    stage_name: str
    operator: str
    accepted_candidate_id: str
    selected_score: Optional[float]
    selection_margin: Optional[float]
    candidates: List[CandidateDecision] = field(default_factory=list)
    frontier_items: List[DecisionFrontierItem] = field(default_factory=list)
    unresolved_conflict_ids: List[str] = field(default_factory=list)
    deferred_judgments: List[str] = field(default_factory=list)
    abandoned_path_ids: List[str] = field(default_factory=list)
    operator_conflicts: List[str] = field(default_factory=list)
    architectural_hesitations: List[str] = field(default_factory=list)
    frontier_reason: str = ""
    note: str = ""


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
    decision_landscape: List[DecisionLandscapeRecord] = field(default_factory=list)
    ontology_ledger: OntologyLedger = field(default_factory=OntologyLedger)
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
    reward_surface_audit: "RewardSurfaceAudit"
    final: str
    final_state: ChainState
    rpm_trace: RPMTrace
    steps: List[ProcessStepRecord]


@dataclass
class RewardSurfaceAudit:
    risk_level: str = "low"
    accepted_count: int = 0
    reward_mean: float = 0.0
    reward_stdev: float = 0.0
    axis_saturation: List[str] = field(default_factory=list)
    low_margin_stages: List[str] = field(default_factory=list)
    low_diversity_stages: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


def default_magic_realism_prior() -> MagicRealismPrior:
    return MagicRealismPrior()
