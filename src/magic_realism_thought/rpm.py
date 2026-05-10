from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .types import (
    CandidateDecision,
    CandidateStep,
    ChainConstraints,
    ChainState,
    DecisionFrontierItem,
    DecisionLandscapeRecord,
    OntologyEntry,
    OntologyLedger,
    ProcessReward,
    RPMCell,
    RPMConflict,
    RPMRepairPlan,
    RPMTrace,
    RuleHypothesis,
    StageSpec,
)
from .utils import clamp01, clip_text, json_safe, safe_div

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


def make_decision_id(stage_index: int, offset: int = 1) -> str:
    return f"d{stage_index:02d}-{offset:02d}"


AXIS_DESCRIPTIONS: Dict[str, str] = {
    "text": "visible text state",
    "symbols": "tracked recurring symbols",
    "constraints": "runtime control bounds",
    "drift": "distance from the previous visible state",
    "recurrence": "symbol survival across transitions",
    "reward": "PRM score surface for visible transitions",
    "operator": "declared stage transformation",
    "mundane_anchor": "ordinary social and material grounding",
    "quiet_impossibility": "small material impossibility without explanation",
    "non_explanation": "restraint against explaining the impossible fact",
    "social_normalization": "ordinary adaptation to the impossible fact",
    "fantasy_drift": "pressure toward fantasy or lore instead of realism",
    "symbolic_pressure": "concrete symbolic recurrence without flat repetition",
    "ordinary_continuity": "work, errands, transport, food, or procedure continuing",
}


CONFLICT_DESCRIPTIONS: Dict[str, str] = {
    "high_drift": "accepted transition moved too far from the prior state",
    "repetition": "surface wording repeats too strongly",
    "collapse": "state became too short, generic, or abstract",
    "symbol_loss": "recurrence-sensitive symbol disappeared",
    "operator_mismatch": "output did not match the declared operator role",
    "weak_closure": "recursive stage did not echo the seed enough",
    "weak_mundane_grounding": "magic-realism stage lost ordinary social ground",
    "weak_impossibility": "impossible fact was not material enough",
    "over_explanation": "step explained or interpreted the impossible fact too directly",
    "fantasy_drift": "step drifted toward fantasy lore",
}


RULE_KIND_DESCRIPTIONS: Dict[str, str] = {
    "symbolic_recurrence": "a symbol acts as a stable recurrence rule",
    "operator_effect": "an operator produced an observed metric-direction effect",
}


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


def recompute_ontology_ledger(trace: RPMTrace) -> None:
    entries: List[OntologyEntry] = []
    last_stage_by_operator = {cell.operator or cell.role: cell.stage_name for cell in trace.matrix}

    for axis in trace.axes:
        entries.append(
            OntologyEntry(
                kind="axis",
                name=axis,
                description=AXIS_DESCRIPTIONS.get(axis, "locally declared trace axis"),
                producer="RPMTrace.axes",
                observed_count=len(trace.matrix),
                last_seen_stage=trace.matrix[-1].stage_name if trace.matrix else None,
            )
        )

    conflict_counts = Counter(conflict.type for conflict in trace.conflicts)
    for conflict_type, count in sorted(conflict_counts.items()):
        last_seen = next(
            (cell.stage_name for cell in reversed(trace.matrix) if any(cid.endswith(conflict_type) for cid in cell.conflict_ids)),
            None,
        )
        entries.append(
            OntologyEntry(
                kind="conflict_type",
                name=conflict_type,
                description=CONFLICT_DESCRIPTIONS.get(conflict_type, "locally observed conflict type"),
                producer="detect_rpm_conflicts",
                observed_count=count,
                last_seen_stage=last_seen,
            )
        )

    operator_counts = Counter(cell.operator or cell.role for cell in trace.matrix)
    for operator, count in sorted(operator_counts.items()):
        entries.append(
            OntologyEntry(
                kind="operator",
                name=operator,
                description="declared visible-state transformation",
                producer="StageSpec.operator",
                observed_count=count,
                last_seen_stage=last_stage_by_operator.get(operator),
            )
        )

    rule_counts = Counter(rule.kind for rule in trace.inferred_rules)
    for rule_kind, count in sorted(rule_counts.items()):
        entries.append(
            OntologyEntry(
                kind="rule_kind",
                name=rule_kind,
                description=RULE_KIND_DESCRIPTIONS.get(rule_kind, "locally inferred rule kind"),
                producer="infer_rules_for_cell",
                observed_count=count,
                last_seen_stage=None,
            )
        )

    warnings: List[str] = []
    if len(trace.axes) > 14:
        warnings.append(f"ontology_pressure: {len(trace.axes)} axes are active; consider merging or demoting report-only axes before adding more.")
    if len(conflict_counts) > 8:
        warnings.append(f"ontology_pressure: {len(conflict_counts)} conflict types observed; prefer reusing an existing type unless behavior changes.")
    if len(operator_counts) > max(8, len(trace.matrix)):
        warnings.append(f"ontology_pressure: {len(operator_counts)} operators observed across {len(trace.matrix)} rows.")
    if len(trace.inferred_rules) >= 32:
        warnings.append("ontology_pressure: rule hypothesis ledger reached its cap; promote only repeated rules with downstream consumers.")

    trace.ontology_ledger = OntologyLedger(entries=entries, warnings=warnings)


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


def candidate_score(candidate: CandidateStep) -> Optional[float]:
    return candidate.reward.score if candidate.reward else None


def build_decision_landscape_record(
    trace: RPMTrace,
    stage: StageSpec,
    stage_index: int,
    accepted: CandidateStep,
    candidates: Sequence[CandidateStep],
    repaired: Sequence[CandidateStep],
) -> DecisionLandscapeRecord:
    by_id: Dict[str, CandidateStep] = {}
    for candidate in list(candidates) + list(repaired):
        by_id[candidate.candidate_id] = candidate
    by_id[accepted.candidate_id] = accepted

    scored = sorted(
        [c for c in by_id.values() if c.reward is not None],
        key=lambda c: c.reward.score if c.reward else -1.0,
        reverse=True,
    )
    margin: Optional[float] = None
    if len(scored) >= 2 and accepted.reward:
        margin = round(accepted.reward.score - (scored[1].reward.score if scored[1].reward else 0.0), 4)

    decisions: List[CandidateDecision] = []
    frontier_items: List[DecisionFrontierItem] = []
    abandoned_path_ids: List[str] = []
    for candidate in by_id.values():
        if candidate.candidate_id == accepted.candidate_id:
            status = "accepted_repair" if candidate.repaired_from else "accepted"
        elif candidate.repaired_from:
            status = "rejected_repair"
        else:
            status = "rejected"
        reason = "; ".join(candidate.reward.reasons if candidate.reward else []) or (
            "selected visible transition" if candidate.candidate_id == accepted.candidate_id else "lower ranked visible candidate"
        )
        decisions.append(
            CandidateDecision(
                candidate_id=candidate.candidate_id,
                status=status,
                provider=candidate.provider,
                model=candidate.model,
                score=candidate_score(candidate),
                reasons=list(candidate.reward.reasons if candidate.reward else []),
                repaired_from=candidate.repaired_from,
            )
        )
        frontier_kind = "accepted_candidate" if candidate.candidate_id == accepted.candidate_id else (
            "repair_candidate" if candidate.repaired_from else "rejected_candidate"
        )
        frontier_status = "active" if candidate.candidate_id == accepted.candidate_id else "abandoned"
        if frontier_status == "abandoned":
            abandoned_path_ids.append(candidate.candidate_id)
        frontier_items.append(
            DecisionFrontierItem(
                frontier_id=f"{make_decision_id(stage_index)}-f{len(frontier_items) + 1:02d}",
                kind=frontier_kind,
                source_id=candidate.candidate_id,
                status=frontier_status,
                reason=reason,
                next_action="continue accepted path" if frontier_status == "active" else "preserve as review evidence",
                score=candidate_score(candidate),
            )
        )

    unresolved = [conflict for conflict in trace.conflicts if not conflict.resolved]
    deferred = [
        f"{conflict.conflict_id}:{conflict.type}"
        for conflict in unresolved[-5:]
    ]
    for conflict in unresolved[-5:]:
        frontier_items.append(
            DecisionFrontierItem(
                frontier_id=f"{make_decision_id(stage_index)}-f{len(frontier_items) + 1:02d}",
                kind="deferred_judgment",
                source_id=conflict.conflict_id,
                status="open",
                reason=f"{conflict.type}: {conflict.description}",
                next_action=conflict.repair_instruction,
                score=conflict.severity,
            )
        )

    operator_conflicts = [conflict.conflict_id for conflict in unresolved if conflict.type == "operator_mismatch"]
    hesitations: List[str] = []
    if margin is not None and margin < 0.035:
        hesitations.append(f"low_selection_margin={margin:.4f}")
    if accepted.reward and not accepted.reward.accept:
        hesitations.append(f"accepted_below_threshold={accepted.reward.score:.4f}")
    if any(conflict.type in {"operator_mismatch", "weak_closure", "symbol_loss"} for conflict in unresolved):
        hesitations.append("open_structural_conflict")

    if unresolved:
        frontier_reason = "open conflicts keep the next transition provisional"
    elif hesitations:
        frontier_reason = "selection is accepted but carries review pressure"
    else:
        frontier_reason = "accepted path is clear under current visible criteria"

    note = "visible decision only: records accepted, rejected, repaired, and unresolved state transitions without hidden reasoning"
    return DecisionLandscapeRecord(
        contract_version="decision-landscape-2.0",
        decision_id=make_decision_id(stage_index),
        stage_index=stage_index,
        stage_name=stage.name,
        operator=stage.operator,
        accepted_candidate_id=accepted.candidate_id,
        selected_score=candidate_score(accepted),
        selection_margin=margin,
        candidates=decisions,
        frontier_items=frontier_items,
        unresolved_conflict_ids=[conflict.conflict_id for conflict in unresolved],
        deferred_judgments=deferred,
        abandoned_path_ids=abandoned_path_ids,
        operator_conflicts=operator_conflicts,
        architectural_hesitations=hesitations,
        frontier_reason=frontier_reason,
        note=note,
    )


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
        recompute_ontology_ledger(state.rpm_trace)
        unresolved = [c for c in state.rpm_trace.conflicts if not c.resolved]
        state.rpm_trace.notes = [
            f"matrix_rows={len(state.rpm_trace.matrix)}",
            f"rules={len(state.rpm_trace.inferred_rules)}",
            f"unresolved_conflicts={len(unresolved)}",
            f"ontology_entries={len(state.rpm_trace.ontology_ledger.entries)}",
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
    if trace.ontology_ledger.warnings:
        lines.append("Ontology pressure warnings:")
        for warning in trace.ontology_ledger.warnings[:3]:
            lines.append(f"- {warning}")
    unresolved = [c for c in trace.conflicts if not c.resolved]
    if unresolved:
        lines.append("Unresolved conflicts:")
        for conflict in unresolved[-max_conflicts:]:
            lines.append(f"- {conflict.conflict_id} [{conflict.type}, severity={conflict.severity}]: {conflict.repair_instruction}")
    if trace.decision_landscape:
        lines.append("Recent visible decisions:")
        for decision in trace.decision_landscape[-max_rows:]:
            margin = "(n/a)" if decision.selection_margin is None else f"{decision.selection_margin:.4f}"
            deferred = ", ".join(decision.deferred_judgments[:3]) or "-"
            frontier = decision.frontier_reason or "-"
            lines.append(
                f"- {decision.decision_id}: accepted={decision.accepted_candidate_id}; "
                f"margin={margin}; deferred={deferred}; frontier={frontier}"
            )
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

    if trace.decision_landscape:
        lines.append("### Decision landscape")
        lines.append("")
        lines.append("| decision | stage | accepted | score | margin | frontier | rejected/repair candidates | deferred |")
        lines.append("|---|---:|---|---:|---:|---|---|---|")
        for decision in trace.decision_landscape:
            rejected = [
                f"{item.candidate_id}:{item.status}:{item.score if item.score is not None else 'n/a'}"
                for item in decision.candidates
                if item.candidate_id != decision.accepted_candidate_id
            ]
            deferred = ", ".join(decision.deferred_judgments[:4]) or "-"
            score = "" if decision.selected_score is None else f"{decision.selected_score:.3f}"
            margin = "" if decision.selection_margin is None else f"{decision.selection_margin:.3f}"
            lines.append(
                f"| `{decision.decision_id}` | {decision.stage_index} | `{decision.accepted_candidate_id}` | "
                f"{score} | {margin} | {decision.frontier_reason or '-'} | {', '.join(rejected[:5]) or '-'} | {deferred} |"
            )
        lines.append("")

        lines.append("#### Frontier items")
        lines.append("")
        lines.append("| frontier | kind | source | status | score | next action |")
        lines.append("|---|---|---|---|---:|---|")
        for decision in trace.decision_landscape:
            for item in decision.frontier_items[:8]:
                score = "" if item.score is None else f"{item.score:.3f}"
                lines.append(
                    f"| `{item.frontier_id}` | {item.kind} | `{item.source_id}` | {item.status} | {score} | {item.next_action or '-'} |"
                )
        lines.append("")

        hesitations = [
            f"{decision.decision_id}:{item}"
            for decision in trace.decision_landscape
            for item in decision.architectural_hesitations
        ]
        if hesitations:
            lines.append("#### Architectural hesitations")
            lines.append("")
            for hesitation in hesitations:
                lines.append(f"- {hesitation}")
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

    if trace.ontology_ledger.entries:
        lines.append("### Ontology ledger")
        lines.append("")
        counts = Counter(entry.kind for entry in trace.ontology_ledger.entries)
        lines.append("- Entry counts: `" + ", ".join(f"{kind}={count}" for kind, count in sorted(counts.items())) + "`")
        if trace.ontology_ledger.warnings:
            lines.append("- Warnings:")
            for warning in trace.ontology_ledger.warnings:
                lines.append(f"  - {warning}")
        lines.append("")
        lines.append("| kind | name | producer | observed | status |")
        lines.append("|---|---|---|---:|---|")
        for entry in trace.ontology_ledger.entries[:24]:
            lines.append(
                f"| {entry.kind} | `{entry.name}` | `{entry.producer}` | {entry.observed_count} | {entry.status} |"
            )
        if len(trace.ontology_ledger.entries) > 24:
            lines.append(f"| ... | ... | ... | {len(trace.ontology_ledger.entries) - 24} more | ... |")
        lines.append("")
    return "\n".join(lines)
