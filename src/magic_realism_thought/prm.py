from __future__ import annotations

import json
from typing import Dict, List, Optional, Protocol, Sequence

from .metrics import char_ngrams, metric_units
from .prompts import build_llm_judge_prompt, build_reward_repair_instruction
from .providers import BaseProvider
from .types import ChatRequest, ChainConstraints, ChainState, CandidateStep, PRM_JUDGE_SYSTEM, ProcessReward, StageSpec
from .utils import clamp01, extract_json_object, json_safe, safe_div

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
