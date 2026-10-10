from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from .metrics import tokenize_text
from .providers import ProviderError
from .rpm import format_rpm_context
from .types import (
    DEFAULT_MODELS,
    DEFAULT_ROLE_PROVIDERS,
    DEFAULT_STAGES,
    PROVIDER_NAMES,
    ROLES,
    SEED_INDEPENDENT_MAGIC_STAGES,
    CandidateStep,
    ChainState,
    MagicRealismPrior,
    ProcessReward,
    PromptAnchorProfile,
    StageSpec,
    default_magic_realism_prior,
)
from .utils import clip_text

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
