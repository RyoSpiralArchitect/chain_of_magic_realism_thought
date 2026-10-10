"""Export saved visible story branches to a self-contained, offline reader."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from importlib.resources import files
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from .frontier_replay import build_frontier_replay_report, load_run_payload


def _objects(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _score(value: Any) -> Optional[float]:
    return float(value) if type(value) in (int, float) and math.isfinite(value) else None


def _strings(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _stages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Join text only on (stage index, candidate ID), never by list position."""
    steps = _objects(payload.get("steps"))
    decisions = _objects(_object(payload.get("rpm_trace")).get("decision_landscape"))
    if not decisions:
        # Older saved runs have full steps but no decision-landscape summary.
        decisions = [{"stage_index": step.get("index"), "stage_name": step.get("name"),
                      "operator": step.get("operator")} for step in steps]
    stages = []
    for decision in decisions:
        index = decision.get("stage_index")
        step = next((item for item in steps if item.get("index") == index), {})
        texts: dict[str, tuple[dict[str, Any], str, str]] = {}
        for status, field in (("accepted", "accepted"), ("rejected", "rejected"), ("repaired", "repaired")):
            values = [_object(step.get(field))] if field == "accepted" else _objects(step.get(field))
            for position, candidate in enumerate(values):
                candidate_id = _text(candidate.get("candidate_id"))
                if candidate_id:
                    suffix = "" if field == "accepted" else f"[{position}]"
                    texts[candidate_id] = (candidate, status, f"steps[index={index}].{field}{suffix}.output")
        candidates = _objects(decision.get("candidates"))
        known = {_text(candidate.get("candidate_id")) for candidate in candidates}
        candidates += [{"candidate_id": key, "status": status}
                       for key, (_, status, _) in texts.items() if key not in known]
        accepted_id = _text(decision.get("accepted_candidate_id")) or _text(_object(step.get("accepted")).get("candidate_id"))
        normalized = []
        for candidate in candidates:
            candidate_id = _text(candidate.get("candidate_id"))
            source, step_status, source_field = texts.get(candidate_id, ({}, "", ""))
            reward = _object(source.get("reward"))
            frontier = next((item for item in _objects(decision.get("frontier_items"))
                             if item.get("source_id") == candidate_id), {})
            status = _text(candidate.get("status")) or step_status or "unknown"
            selected = bool(candidate_id and candidate_id == accepted_id)
            discarded = not selected and (status.startswith("rejected") or frontier.get("status") == "abandoned")
            output = _text(source.get("output"))
            # Some external traces store visible output directly in the landscape.
            if not output and isinstance(candidate.get("output"), str):
                output = candidate["output"]
                source_field = f"rpm_trace.decision_landscape[stage_index={index}].candidates[candidate_id={candidate_id}].output"
            is_dry_run = _object(source.get("usage")).get("dry_run") is True
            provider = _text(candidate.get("provider")) or _text(source.get("provider"))
            model = _text(candidate.get("model")) or _text(source.get("model"))
            fixture = provider == "dry-run" or model == "fixture"
            handwritten = provider == "handwritten-fixture" and model == "fixture"
            normalized.append({
                "id": candidate_id, "status": status, "selected": selected, "discarded": discarded,
                "output": output, "text_source": source_field if output else "",
                "score": _score(candidate.get("score", reward.get("score"))),
                "reasons": _strings(candidate.get("reasons", reward.get("reasons"))),
                "frontier_reason": _text(frontier.get("reason")),
                "provider": provider, "model": model,
                "provenance": ("dry-run" if is_dry_run else "handwritten fixture" if handwritten
                               else "fixture" if fixture else "saved / unverified"),
                "repaired_from": candidate.get("repaired_from") or source.get("repaired_from"),
                "revived_from": None,
            })
        stages.append({"index": index, "name": _text(decision.get("stage_name")),
                       "operator": _text(decision.get("operator")),
                       "decision_id": _text(decision.get("decision_id")),
                       "frontier_reason": _text(decision.get("frontier_reason")),
                       "candidates": normalized,
                       "open_items": [item for item in _objects(decision.get("frontier_items"))
                                      if item.get("kind") == "deferred_judgment"],
                       "hesitations": _strings(decision.get("architectural_hesitations"))})
    return stages


def build_story_reader(paths: Iterable[str | Path]) -> dict[str, Any]:
    paths = [Path(path) for path in paths]
    if not paths:
        raise ValueError("at least one saved run is required")
    loaded = [load_run_payload(path) for path in paths]
    seeds = [_text(payload.get("seed") or payload.get("prompt")) for _, payload in loaded]
    if any(not seed for seed in seeds) or len(set(seeds)) != 1:
        raise ValueError("reader runs must have the same non-empty seed; export different seeds separately")
    for path, payload in loaded:
        if not isinstance(payload.get("rpm_trace"), dict):
            raise ValueError(f"rpm_trace must be an object: {path}")
    # Replay is owned by the existing harness; the reader only presents its result.
    replay = build_frontier_replay_report(paths)
    run_ids = [run["run_id"] for run in replay["runs"]]
    if len(set(run_ids)) != len(run_ids):
        raise ValueError("run IDs must be unique; give each saved run a distinct run_id")
    runs = []
    for number, ((path, payload), summary) in enumerate(zip(loaded, replay["runs"])):
        stages = _stages(payload)
        if number:
            for event in replay["transitions"][number - 1]["events"]:
                if event.get("state") != "contradicted_prior_abandonment":
                    continue
                for stage in stages:
                    if f"stage:{stage['index']}" == event.get("stage_key"):
                        for candidate in stage["candidates"]:
                            if candidate["id"] == event.get("current_accepted"):
                                candidate["revived_from"] = run_ids[number - 1]
        runs.append({"id": summary["run_id"], "file": path.name,
                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                     "started_at": payload.get("started_at_utc"),
                     "final": _text(payload.get("final")), "stages": stages})
    # Paths in the HTML are filenames only: no private absolute directory disclosure.
    for run, path in zip(replay["runs"], paths):
        run["path"] = path.name
    for transition, before, after in zip(replay["transitions"], paths, paths[1:]):
        transition["from_path"], transition["to_path"] = before.name, after.name
    return {"contract_version": "story-reader-1.0", "seed": seeds[0], "runs": runs, "replay": replay}


def render_story_reader(data: dict[str, Any]) -> str:
    serialized = json.dumps(data, ensure_ascii=False, allow_nan=False)
    # JSON is embedded in a script element; escaping < prevents </script> injection.
    for character, escape in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e"),
                              ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        serialized = serialized.replace(character, escape)
    template = files("magic_realism_thought").joinpath("story_reader.html").read_text(encoding="utf-8")
    return template.replace("__STORY_READER_DATA__", serialized)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Read saved story branches offline, without provider calls.")
    parser.add_argument("runs", nargs="+", help="Same-seed saved run JSON files, in replay order.")
    parser.add_argument("--output-html", required=True, help="Self-contained HTML to open in a browser.")
    args = parser.parse_args(argv)
    output = Path(args.output_html)
    try:
        if output.resolve() in {Path(path).resolve() for path in args.runs}:
            raise ValueError("output HTML must not overwrite a source run")
        rendered = render_story_reader(build_story_reader(args.runs))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Saved offline reader: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
