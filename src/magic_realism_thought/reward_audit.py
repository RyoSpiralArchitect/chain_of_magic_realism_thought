from __future__ import annotations

import difflib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from .types import ChainRun, RewardSurfaceAudit

def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stdev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = mean(values)
    return math.sqrt(sum((value - avg) ** 2 for value in values) / len(values))


def text_similarity(left: str, right: str, limit: int = 2200) -> float:
    return difflib.SequenceMatcher(None, left[:limit], right[:limit]).ratio()


def compute_reward_surface_audit_from_signals(
    rewards: Sequence[float],
    axis_values: Mapping[str, Sequence[float]],
    selection_margins: Sequence[float],
    candidate_similarities: Sequence[float],
) -> RewardSurfaceAudit:
    saturated = [
        f"{axis}:mean={mean(list(values)):.3f}"
        for axis, values in sorted(axis_values.items())
        if len(values) >= 3 and mean(list(values)) >= 0.90
    ]
    low_margin = [
        f"case:{idx} margin={margin:.4f}"
        for idx, margin in enumerate(selection_margins, start=1)
        if margin < 0.035
    ]
    low_diversity = [
        f"case:{idx} closest_rejected_similarity={similarity:.3f}"
        for idx, similarity in enumerate(candidate_similarities, start=1)
        if similarity >= 0.92
    ]

    reward_mean = mean(rewards)
    reward_stdev = stdev(rewards)
    recommendations: List[str] = []
    if rewards and reward_mean >= 0.82 and reward_stdev <= 0.035:
        recommendations.append("Run a blind or negative-control prompt; high, flat rewards can indicate a style-imitation surface.")
    if saturated:
        recommendations.append("Inspect saturated axes before increasing their weight; saturated axes stop discriminating candidates.")
    if low_margin:
        recommendations.append("Keep low-margin rejected candidates in review; selection may be judge-noise rather than a clear transition.")
    if low_diversity:
        recommendations.append("Increase candidate diversity or adjust variants; near-duplicate candidates invite reward-surface overfitting.")
    if not recommendations:
        recommendations.append("No immediate reward-surface pressure detected; keep memory as a soft prior.")

    signal_count = sum(bool(x) for x in (saturated, low_margin, low_diversity))
    if rewards and reward_mean >= 0.82 and reward_stdev <= 0.035:
        signal_count += 1
    risk_level = "high" if signal_count >= 3 else "medium" if signal_count >= 1 else "low"

    return RewardSurfaceAudit(
        risk_level=risk_level,
        accepted_count=len(rewards),
        reward_mean=round(reward_mean, 4),
        reward_stdev=round(reward_stdev, 4),
        axis_saturation=saturated,
        low_margin_stages=low_margin,
        low_diversity_stages=low_diversity,
        recommendations=recommendations,
    )


def compute_reward_surface_audit(run: ChainRun) -> RewardSurfaceAudit:
    rewards = [step.accepted.reward.score for step in run.steps if step.accepted.reward]
    axis_values: Dict[str, List[float]] = {}
    for step in run.steps:
        if not step.accepted.reward:
            continue
        for axis, value in step.accepted.reward.metric_scores.items():
            axis_values.setdefault(axis, []).append(float(value))

    selection_margins: List[float] = []
    for decision in run.rpm_trace.decision_landscape:
        candidate_count = len(decision.candidates)
        if candidate_count >= 2 and decision.selection_margin is not None and decision.selection_margin < 0.035:
            selection_margins.append(decision.selection_margin)

    candidate_similarities: List[float] = []
    for step in run.steps:
        rejected = [candidate for candidate in step.rejected if candidate.output]
        if not rejected:
            continue
        closest = max(text_similarity(step.accepted.output, candidate.output) for candidate in rejected)
        candidate_similarities.append(closest)

    audit = compute_reward_surface_audit_from_signals(
        rewards=rewards,
        axis_values=axis_values,
        selection_margins=selection_margins,
        candidate_similarities=candidate_similarities,
    )
    audit.low_margin_stages = [
        f"{decision.stage_index}:{decision.stage_name} margin={decision.selection_margin:.4f}"
        for decision in run.rpm_trace.decision_landscape
        if len(decision.candidates) >= 2 and decision.selection_margin is not None and decision.selection_margin < 0.035
    ]
    audit.low_diversity_stages = []
    for step in run.steps:
        rejected = [candidate for candidate in step.rejected if candidate.output]
        if not rejected:
            continue
        closest = max(text_similarity(step.accepted.output, candidate.output) for candidate in rejected)
        if closest >= 0.92:
            audit.low_diversity_stages.append(f"{step.index}:{step.name} closest_rejected_similarity={closest:.3f}")
    return audit


def evaluate_reward_audit_cases(path: str | Path) -> List[Dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("reward audit eval fixture must be a JSON list")
    results: List[Dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("each reward audit eval case must be a JSON object")
        audit = compute_reward_surface_audit_from_signals(
            rewards=[float(value) for value in item.get("rewards", [])],
            axis_values={
                str(axis): [float(value) for value in values]
                for axis, values in dict(item.get("axis_values", {})).items()
            },
            selection_margins=[float(value) for value in item.get("selection_margins", [])],
            candidate_similarities=[float(value) for value in item.get("candidate_similarities", [])],
        )
        expected = str(item.get("expected_risk", ""))
        results.append(
            {
                "name": str(item.get("name", "unnamed")),
                "expected_risk": expected,
                "actual_risk": audit.risk_level,
                "passed": audit.risk_level == expected,
                "audit": {
                    "risk_level": audit.risk_level,
                    "reward_mean": audit.reward_mean,
                    "reward_stdev": audit.reward_stdev,
                    "axis_saturation": audit.axis_saturation,
                    "low_margin_stages": audit.low_margin_stages,
                    "low_diversity_stages": audit.low_diversity_stages,
                    "recommendations": audit.recommendations,
                },
            }
        )
    return results


def format_reward_surface_audit_markdown(audit: RewardSurfaceAudit) -> str:
    lines: List[str] = []
    lines.append("## Reward surface audit")
    lines.append("")
    lines.append(f"- Risk level: `{audit.risk_level}`")
    lines.append(f"- Accepted rewards: `count={audit.accepted_count}, mean={audit.reward_mean}, stdev={audit.reward_stdev}`")
    if audit.axis_saturation:
        lines.append(f"- Axis saturation: `{', '.join(audit.axis_saturation)}`")
    if audit.low_margin_stages:
        lines.append(f"- Low-margin stages: `{', '.join(audit.low_margin_stages)}`")
    if audit.low_diversity_stages:
        lines.append(f"- Low-diversity stages: `{', '.join(audit.low_diversity_stages)}`")
    lines.append("- Recommendations:")
    for recommendation in audit.recommendations:
        lines.append(f"  - {recommendation}")
    return "\n".join(lines)
