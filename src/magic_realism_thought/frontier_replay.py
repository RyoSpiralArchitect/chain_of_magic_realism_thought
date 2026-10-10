from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, DefaultDict, Dict, Iterable, List, Optional, Sequence, Tuple

from .utils import clip_text, json_safe


FRONTIER_REPLAY_CONTRACT = "frontier-replay-1.0"


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_float(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _run_id(path: Path, payload: Dict[str, Any]) -> str:
    explicit = payload.get("run_id") or payload.get("started_at_utc")
    return str(explicit) if explicit else path.stem


def _trace(payload: Dict[str, Any]) -> Dict[str, Any]:
    return _as_dict(payload.get("rpm_trace"))


def _decisions(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [_as_dict(item) for item in _as_list(_trace(payload).get("decision_landscape"))]


def _ledger_entries(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    ledger = _as_dict(_trace(payload).get("ontology_ledger"))
    return [_as_dict(item) for item in _as_list(ledger.get("entries"))]


def _ledger_warnings(payload: Dict[str, Any]) -> List[str]:
    ledger = _as_dict(_trace(payload).get("ontology_ledger"))
    return [str(item) for item in _as_list(ledger.get("warnings"))]


def _stage_key(decision: Dict[str, Any]) -> str:
    stage_index = decision.get("stage_index", "?")
    return f"stage:{stage_index}"


def _conflict_type_from_source(source_id: str) -> str:
    parts = source_id.split("-", 2)
    if len(parts) == 3:
        return parts[2]
    return source_id or "unknown"


def _conflict_type(decision: Dict[str, Any], item: Dict[str, Any]) -> str:
    reason = str(item.get("reason") or "")
    if ":" in reason:
        head = reason.split(":", 1)[0].strip()
        if head:
            return head
    return _conflict_type_from_source(str(item.get("source_id") or ""))


def _frontier_key(decision: Dict[str, Any], item: Dict[str, Any]) -> str:
    kind = str(item.get("kind") or "unknown")
    if kind == "deferred_judgment":
        return f"{_stage_key(decision)}:deferred:{_conflict_type(decision, item)}"
    return f"{_stage_key(decision)}:{kind}:{item.get('source_id') or 'unknown'}"


def _decision_lookup(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {_stage_key(decision): decision for decision in _decisions(payload)}


def _candidate_status_by_stage(decision: Dict[str, Any]) -> Dict[str, str]:
    statuses: Dict[str, str] = {}
    for candidate in _as_list(decision.get("candidates")):
        candidate_dict = _as_dict(candidate)
        candidate_id = str(candidate_dict.get("candidate_id") or "")
        if candidate_id:
            statuses[candidate_id] = str(candidate_dict.get("status") or "")
    for item in _as_list(decision.get("frontier_items")):
        item_dict = _as_dict(item)
        source_id = str(item_dict.get("source_id") or "")
        if source_id:
            statuses.setdefault(source_id, str(item_dict.get("status") or ""))
    return statuses


def _deferred_items(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    items: Dict[str, Dict[str, Any]] = {}
    for decision in _decisions(payload):
        for item in _as_list(decision.get("frontier_items")):
            item_dict = _as_dict(item)
            if item_dict.get("kind") != "deferred_judgment":
                continue
            key = _frontier_key(decision, item_dict)
            items[key] = {
                "key": key,
                "decision_id": decision.get("decision_id"),
                "stage_index": decision.get("stage_index"),
                "stage_name": decision.get("stage_name"),
                "operator": decision.get("operator"),
                "source_id": item_dict.get("source_id"),
                "conflict_type": _conflict_type(decision, item_dict),
                "status": item_dict.get("status") or "open",
                "score": _as_float(item_dict.get("score")),
                "reason": item_dict.get("reason") or "",
                "next_action": item_dict.get("next_action") or "",
            }
    return items


def _abandoned_by_stage(decision: Dict[str, Any]) -> List[str]:
    abandoned = [str(item) for item in _as_list(decision.get("abandoned_path_ids")) if item]
    for item in _as_list(decision.get("frontier_items")):
        item_dict = _as_dict(item)
        if item_dict.get("status") == "abandoned" and item_dict.get("source_id"):
            abandoned.append(str(item_dict["source_id"]))
    return sorted(set(abandoned))


def _frontier_counts(payload: Dict[str, Any]) -> Dict[str, int]:
    counts = {
        "decisions": 0,
        "frontier_items": 0,
        "active": 0,
        "abandoned": 0,
        "deferred": 0,
        "hesitations": 0,
        "operator_conflicts": 0,
    }
    decisions = _decisions(payload)
    counts["decisions"] = len(decisions)
    for decision in decisions:
        counts["hesitations"] += len(_as_list(decision.get("architectural_hesitations")))
        counts["operator_conflicts"] += len(_as_list(decision.get("operator_conflicts")))
        for item in _as_list(decision.get("frontier_items")):
            item_dict = _as_dict(item)
            counts["frontier_items"] += 1
            status = item_dict.get("status")
            kind = item_dict.get("kind")
            if status == "active":
                counts["active"] += 1
            if status == "abandoned":
                counts["abandoned"] += 1
            if kind == "deferred_judgment":
                counts["deferred"] += 1
    return counts


def _term_map(payload: Dict[str, Any]) -> Dict[str, List[str]]:
    terms: DefaultDict[str, set[str]] = defaultdict(set)
    for entry in _ledger_entries(payload):
        kind = str(entry.get("kind") or "unknown")
        name = str(entry.get("name") or "")
        if name:
            terms[kind].add(name)
    return {kind: sorted(values) for kind, values in terms.items()}


def _summarize_run(path: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    decisions = _decisions(payload)
    accepted_path = [
        {
            "decision_id": decision.get("decision_id"),
            "stage_index": decision.get("stage_index"),
            "stage_name": decision.get("stage_name"),
            "accepted_candidate_id": decision.get("accepted_candidate_id"),
            "selected_score": decision.get("selected_score"),
            "selection_margin": decision.get("selection_margin"),
            "frontier_reason": decision.get("frontier_reason"),
        }
        for decision in decisions
    ]
    return {
        "run_id": _run_id(path, payload),
        "path": str(path),
        "seed": payload.get("seed") or payload.get("prompt") or "",
        "started_at_utc": payload.get("started_at_utc"),
        "final_preview": clip_text(str(payload.get("final") or ""), 180),
        "counts": _frontier_counts(payload),
        "accepted_path": accepted_path,
        "open_deferred": list(_deferred_items(payload).values()),
        "ontology_terms": _term_map(payload),
        "ontology_warnings": _ledger_warnings(payload),
    }


def _compare_deferred(prev: Dict[str, Any], curr: Dict[str, Any]) -> List[Dict[str, Any]]:
    prev_items = _deferred_items(prev)
    curr_items = _deferred_items(curr)
    events: List[Dict[str, Any]] = []

    for key, prev_item in sorted(prev_items.items()):
        curr_item = curr_items.get(key)
        if curr_item:
            prev_score = prev_item.get("score")
            curr_score = curr_item.get("score")
            delta = None
            if isinstance(prev_score, float) and isinstance(curr_score, float):
                delta = round(curr_score - prev_score, 4)
            state = "still_open"
            if isinstance(delta, float) and delta <= -0.05:
                state = "improved_but_open"
            elif isinstance(delta, float) and delta >= 0.05:
                state = "worsened"
            events.append(
                {
                    "kind": "deferred_judgment",
                    "state": state,
                    "key": key,
                    "conflict_type": prev_item.get("conflict_type"),
                    "stage_index": prev_item.get("stage_index"),
                    "previous_score": prev_score,
                    "current_score": curr_score,
                    "score_delta": delta,
                    "next_action": curr_item.get("next_action") or prev_item.get("next_action"),
                }
            )
        else:
            events.append(
                {
                    "kind": "deferred_judgment",
                    "state": "resolved",
                    "key": key,
                    "conflict_type": prev_item.get("conflict_type"),
                    "stage_index": prev_item.get("stage_index"),
                    "previous_score": prev_item.get("score"),
                    "current_score": None,
                    "score_delta": None,
                    "next_action": "mark as closed unless later runs reintroduce this conflict",
                }
            )

    for key, curr_item in sorted(curr_items.items()):
        if key in prev_items:
            continue
        events.append(
            {
                "kind": "deferred_judgment",
                "state": "new",
                "key": key,
                "conflict_type": curr_item.get("conflict_type"),
                "stage_index": curr_item.get("stage_index"),
                "previous_score": None,
                "current_score": curr_item.get("score"),
                "score_delta": None,
                "next_action": curr_item.get("next_action"),
            }
        )
    return events


def _compare_accepted_paths(prev: Dict[str, Any], curr: Dict[str, Any]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    prev_decisions = _decision_lookup(prev)
    curr_decisions = _decision_lookup(curr)
    for stage_key in sorted(set(prev_decisions) | set(curr_decisions)):
        prev_decision = prev_decisions.get(stage_key)
        curr_decision = curr_decisions.get(stage_key)
        if not prev_decision or not curr_decision:
            events.append(
                {
                    "kind": "stage_presence",
                    "state": "added" if curr_decision else "removed",
                    "stage_key": stage_key,
                    "stage_name": (curr_decision or prev_decision or {}).get("stage_name"),
                }
            )
            continue
        prev_accepted = str(prev_decision.get("accepted_candidate_id") or "")
        curr_accepted = str(curr_decision.get("accepted_candidate_id") or "")
        if prev_accepted == curr_accepted:
            continue
        prev_abandoned = _abandoned_by_stage(prev_decision)
        state = "accepted_path_shift"
        if curr_accepted in prev_abandoned:
            state = "contradicted_prior_abandonment"
        events.append(
            {
                "kind": "accepted_path",
                "state": state,
                "stage_key": stage_key,
                "stage_name": curr_decision.get("stage_name") or prev_decision.get("stage_name"),
                "previous_accepted": prev_accepted,
                "current_accepted": curr_accepted,
                "previous_candidate_statuses": _candidate_status_by_stage(prev_decision),
                "current_candidate_statuses": _candidate_status_by_stage(curr_decision),
                "review_note": "a previously abandoned candidate became accepted"
                if state == "contradicted_prior_abandonment"
                else "accepted candidate changed between runs",
            }
        )
    return events


def _compare_ontology(prev: Dict[str, Any], curr: Dict[str, Any]) -> List[Dict[str, Any]]:
    prev_terms = _term_map(prev)
    curr_terms = _term_map(curr)
    growth: List[Dict[str, Any]] = []
    for kind in sorted(set(prev_terms) | set(curr_terms)):
        added = sorted(set(curr_terms.get(kind, [])) - set(prev_terms.get(kind, [])))
        if not added:
            continue
        growth.append(
            {
                "kind": kind,
                "added_terms": added,
                "status": "requires_rationale",
                "rationale_prompt": "Explain which downstream decision, repair, score, or review path each new term changes.",
            }
        )
    return growth


def _compare_pair(
    prev_path: Path,
    prev_payload: Dict[str, Any],
    curr_path: Path,
    curr_payload: Dict[str, Any],
) -> Dict[str, Any]:
    deferred_events = _compare_deferred(prev_payload, curr_payload)
    accepted_events = _compare_accepted_paths(prev_payload, curr_payload)
    ontology_growth = _compare_ontology(prev_payload, curr_payload)
    return {
        "from_run": _run_id(prev_path, prev_payload),
        "to_run": _run_id(curr_path, curr_payload),
        "from_path": str(prev_path),
        "to_path": str(curr_path),
        "events": accepted_events + deferred_events,
        "ontology_growth_gate": ontology_growth,
    }


def _latest_frontier(payload: Dict[str, Any]) -> Dict[str, Any]:
    latest_decisions = _decisions(payload)[-3:]
    open_items: List[Dict[str, Any]] = []
    hesitations: List[Dict[str, Any]] = []
    for decision in latest_decisions:
        for item in _as_list(decision.get("frontier_items")):
            item_dict = _as_dict(item)
            if item_dict.get("status") in {"open", "deferred"} or item_dict.get("kind") == "deferred_judgment":
                open_items.append(
                    {
                        "decision_id": decision.get("decision_id"),
                        "stage_index": decision.get("stage_index"),
                        "stage_name": decision.get("stage_name"),
                        "kind": item_dict.get("kind"),
                        "source_id": item_dict.get("source_id"),
                        "score": item_dict.get("score"),
                        "reason": item_dict.get("reason"),
                        "next_action": item_dict.get("next_action"),
                    }
                )
        for hesitation in _as_list(decision.get("architectural_hesitations")):
            hesitations.append(
                {
                    "decision_id": decision.get("decision_id"),
                    "stage_index": decision.get("stage_index"),
                    "stage_name": decision.get("stage_name"),
                    "hesitation": hesitation,
                }
            )
    return {"open_items": open_items, "architectural_hesitations": hesitations}


def _recommendations(report: Dict[str, Any]) -> List[str]:
    recommendations: List[str] = []
    if report["run_count"] < 2:
        recommendations.append("Add at least two runs for replay; one trace can only show the latest frontier.")
    if report["latest_frontier"]["open_items"]:
        recommendations.append("Review latest open deferred judgments before treating the path as settled.")
    if any(
        event.get("state") == "contradicted_prior_abandonment"
        for transition in report["transitions"]
        for event in transition["events"]
    ):
        recommendations.append("Inspect revived abandoned candidates; the replay surfaced a visible ranking reversal.")
    if any(transition["ontology_growth_gate"] for transition in report["transitions"]):
        recommendations.append("Attach rationale for new ontology terms before promoting them into durable trace vocabulary.")
    if not recommendations:
        recommendations.append("No unresolved replay pressure detected under the current visible criteria.")
    return recommendations


def load_run_payload(path: str | Path) -> Tuple[Path, Dict[str, Any]]:
    resolved = Path(path)
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"run JSON must be an object: {resolved}")
    if "rpm_trace" not in payload:
        raise ValueError(f"run JSON is missing rpm_trace: {resolved}")
    return resolved, payload


def build_frontier_replay_report(paths: Iterable[str | Path]) -> Dict[str, Any]:
    loaded = [load_run_payload(path) for path in paths]
    if not loaded:
        raise ValueError("at least one run JSON is required")

    seeds = [str(payload.get("seed") or payload.get("prompt") or "") for _, payload in loaded]
    transitions = [
        _compare_pair(prev_path, prev_payload, curr_path, curr_payload)
        for (prev_path, prev_payload), (curr_path, curr_payload) in zip(loaded, loaded[1:])
    ]
    latest_payload = loaded[-1][1]
    report: Dict[str, Any] = {
        "contract_version": FRONTIER_REPLAY_CONTRACT,
        "run_count": len(loaded),
        "seed_consistency": len(set(seeds)) <= 1,
        "seed": seeds[-1],
        "runs": [_summarize_run(path, payload) for path, payload in loaded],
        "transitions": transitions,
        "latest_frontier": _latest_frontier(latest_payload),
    }
    report["recommendations"] = _recommendations(report)
    return json_safe(report)


def format_frontier_replay_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Frontier Replay Report")
    lines.append("")
    lines.append(f"- Contract: `{report.get('contract_version')}`")
    lines.append(f"- Runs: `{report.get('run_count')}`")
    lines.append(f"- Seed consistency: `{report.get('seed_consistency')}`")
    if report.get("seed"):
        lines.append(f"- Seed: {report['seed']}")
    lines.append("")

    lines.append("## Runs")
    lines.append("")
    lines.append("| run | decisions | frontier | active | abandoned | deferred | hesitations |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for run in _as_list(report.get("runs")):
        run_dict = _as_dict(run)
        counts = _as_dict(run_dict.get("counts"))
        lines.append(
            f"| `{run_dict.get('run_id')}` | {counts.get('decisions', 0)} | "
            f"{counts.get('frontier_items', 0)} | {counts.get('active', 0)} | "
            f"{counts.get('abandoned', 0)} | {counts.get('deferred', 0)} | "
            f"{counts.get('hesitations', 0)} |"
        )
    lines.append("")

    lines.append("## Replay Transitions")
    lines.append("")
    transitions = _as_list(report.get("transitions"))
    if not transitions:
        lines.append("- No adjacent run pair to compare.")
    for transition in transitions:
        transition_dict = _as_dict(transition)
        lines.append(f"### `{transition_dict.get('from_run')}` -> `{transition_dict.get('to_run')}`")
        lines.append("")
        events = _as_list(transition_dict.get("events"))
        if events:
            lines.append("| kind | state | stage | detail |")
            lines.append("|---|---|---:|---|")
            for event in events:
                event_dict = _as_dict(event)
                detail = event_dict.get("key") or event_dict.get("review_note") or event_dict.get("stage_name") or ""
                if event_dict.get("kind") == "accepted_path":
                    detail = f"{event_dict.get('previous_accepted')} -> {event_dict.get('current_accepted')}: {event_dict.get('review_note')}"
                lines.append(
                    f"| {event_dict.get('kind')} | `{event_dict.get('state')}` | "
                    f"{event_dict.get('stage_index') or event_dict.get('stage_key') or '-'} | {detail} |"
                )
        else:
            lines.append("- No accepted-path or deferred-judgment changes detected.")
        growth = _as_list(transition_dict.get("ontology_growth_gate"))
        if growth:
            lines.append("")
            lines.append("Ontology growth gate:")
            for item in growth:
                item_dict = _as_dict(item)
                terms = ", ".join(f"`{term}`" for term in _as_list(item_dict.get("added_terms")))
                lines.append(f"- `{item_dict.get('kind')}` added {terms}: {item_dict.get('status')}")
        lines.append("")

    latest = _as_dict(report.get("latest_frontier"))
    lines.append("## Latest Frontier")
    lines.append("")
    open_items = _as_list(latest.get("open_items"))
    if open_items:
        for item in open_items:
            item_dict = _as_dict(item)
            lines.append(
                f"- `{item_dict.get('decision_id')}` {item_dict.get('kind')} "
                f"`{item_dict.get('source_id')}` score `{item_dict.get('score')}`: "
                f"{item_dict.get('next_action') or item_dict.get('reason') or ''}"
            )
    else:
        lines.append("- No open frontier items in the latest run.")
    hesitations = _as_list(latest.get("architectural_hesitations"))
    if hesitations:
        lines.append("")
        lines.append("Architectural hesitations:")
        for item in hesitations:
            item_dict = _as_dict(item)
            lines.append(f"- `{item_dict.get('decision_id')}` {item_dict.get('hesitation')}")
    lines.append("")

    lines.append("## Recommendations")
    lines.append("")
    for recommendation in _as_list(report.get("recommendations")):
        lines.append(f"- {recommendation}")
    lines.append("")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay saved decision-landscape traces across runs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("runs", nargs="+", help="Run JSON files to replay in chronological order.")
    parser.add_argument("--output-json", help="Write replay report JSON.")
    parser.add_argument("--output-md", help="Write replay report Markdown.")
    parser.add_argument("--json", action="store_true", help="Print the JSON report instead of Markdown.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        report = build_frontier_replay_report(args.runs)
        if args.output_json:
            Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if args.output_md:
            Path(args.output_md).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output_md).write_text(format_frontier_replay_markdown(report), encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_frontier_replay_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
