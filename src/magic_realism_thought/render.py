from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import List, Optional

from .prompts import format_anchor_profile, format_metrics, format_reward
from .reward_audit import format_reward_surface_audit_markdown
from .rpm import format_rpm_markdown
from .types import ChainRun
from .utils import clip_text, json_safe

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
    lines.append(f"- Reward surface audit: `risk={run.reward_surface_audit.risk_level}`")
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

    lines.append(format_reward_surface_audit_markdown(run.reward_surface_audit))
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
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        payload = json_safe(dataclasses.asdict(run))
        Path(output_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(
            render_markdown(run, show_stages=show_stages, show_candidates=show_candidates, show_rpm=show_rpm),
            encoding="utf-8",
        )
