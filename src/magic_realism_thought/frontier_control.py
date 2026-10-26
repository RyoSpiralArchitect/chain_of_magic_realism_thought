"""Translate saved visible observations into bounded, opt-in prompt reminders."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

from .types import StageSpec


FRONTIER_CONTROL_CONTRACT = "frontier-control-1.0"
MAX_NOTES = 24
MAX_NOTES_PER_STAGE = 3
OBSERVATIONS = {
    "new": "A new concern was recorded in the latest saved run.",
    "still_open": "The concern remained open across the last two saved runs.",
    "improved_but_open": "The recorded severity decreased, but the concern remained open.",
    "worsened": "The recorded severity increased while the concern remained open.",
    "observed_open": "A saved decision recorded an open concern; its final resolution is unverified.",
    "not_observed": "An earlier concern was absent from the latest observations; resolution is unverified.",
}
CHECKS = {
    "high_drift": "Check continuity with the seed scene and its concrete objects.",
    "symbol_loss": "Check whether a seed-linked symbol can recur through changed action or sensation.",
    "operator_mismatch": "Check that the visible transition fulfills the current stage instruction.",
    "weak_closure": "Check whether the ending echoes the seed through a transformed concrete image.",
    "repetition": "Check for repeated wording and vary how recurring objects act.",
    "collapse": "Check for concrete place, objects, and action before adding abstraction.",
    "weak_mundane_grounding": "Check that ordinary objects and routines remain tangible.",
    "weak_impossibility": "Check whether a small material impossibility is visible in the scene.",
    "over_explanation": "Check whether the scene explains its impossible fact more than it needs to.",
    "fantasy_drift": "Check for ordinary continuity around the impossible fact.",
}


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _stage(decision: dict[str, Any]) -> dict[str, Any]:
    return {"index": decision.get("stage_index"), "name": decision.get("stage_name"), "operator": decision.get("operator")}


def _stage_key(stage: dict[str, Any]) -> tuple[int, str, str]:
    return stage["index"], stage["name"], stage["operator"]


def _guidance(state: str, conflict_type: str) -> str:
    check = CHECKS.get(conflict_type, "Check the stage instruction and seed-linked continuity.")
    return f"{OBSERVATIONS[state]} {check} Use only what fits this candidate."


def _validate_stage(stage: Any) -> None:
    if (not isinstance(stage, dict) or type(stage.get("index")) is not int or stage["index"] < 1
            or not isinstance(stage.get("name"), str) or not stage["name"]
            or not isinstance(stage.get("operator"), str)):
        raise ValueError("frontier control requires a stage index, name, and operator")


def _validate_run(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ValueError("frontier control source must be a run JSON object")
    seed = payload.get("seed") or payload.get("prompt")
    if not isinstance(seed, str) or not seed.strip():
        raise ValueError("frontier control source requires a nonempty seed")
    trace = payload.get("rpm_trace")
    if not isinstance(trace, dict) or not isinstance(trace.get("decision_landscape"), list):
        raise ValueError("frontier control requires a decision_landscape list")
    decisions = trace["decision_landscape"]
    if not decisions:
        raise ValueError("frontier control requires at least one saved decision")
    indices = set()
    for decision in decisions:
        if not isinstance(decision, dict) or decision.get("contract_version") != "decision-landscape-2.0":
            raise ValueError("frontier control requires decision-landscape-2.0")
        _validate_stage(_stage(decision))
        if not isinstance(decision.get("decision_id"), str) or not decision["decision_id"]:
            raise ValueError("saved decisions require a decision_id")
        if decision["stage_index"] in indices:
            raise ValueError("frontier control source has duplicate stage indices")
        indices.add(decision["stage_index"])
        if not isinstance(decision.get("frontier_items"), list):
            raise ValueError("frontier control requires explicit frontier_items, including empty lists")
        for item in decision["frontier_items"]:
            if not isinstance(item, dict):
                raise ValueError("frontier_items must contain objects")
            if item.get("kind") == "deferred_judgment":
                if (not isinstance(item.get("source_id"), str) or not item["source_id"]
                        or item.get("status") not in ("open", "deferred", "resolved")):
                    raise ValueError("deferred judgments require source_id and explicit status")
    conflicts = trace.get("conflicts", [])
    if not isinstance(conflicts, list):
        raise ValueError("rpm_trace.conflicts must be a list when present")
    seen = set()
    for conflict in conflicts:
        if (not isinstance(conflict, dict) or not isinstance(conflict.get("conflict_id"), str)
                or type(conflict.get("resolved")) is not bool or not isinstance(conflict.get("type"), str)):
            raise ValueError("saved conflicts require conflict_id, type, and boolean resolved")
        if conflict["conflict_id"] in seen:
            raise ValueError("duplicate saved conflict_id")
        seen.add(conflict["conflict_id"])
    matrix = trace.get("matrix", [])
    if not isinstance(matrix, list):
        raise ValueError("rpm_trace.matrix must be a list when present")
    for cell in matrix:
        if (not isinstance(cell, dict) or type(cell.get("row_index")) is not int
                or not isinstance(cell.get("conflict_ids"), list)
                or any(not isinstance(item, str) for item in cell["conflict_ids"])):
            raise ValueError("saved matrix rows require row_index and conflict_ids")


def _observations(payload: dict[str, Any], source: int) -> tuple[dict, list]:
    """Use final conflict flags when available; keep snapshots provisional otherwise."""
    trace = payload["rpm_trace"]
    final = {item["conflict_id"]: item for item in trace.get("conflicts", [])}
    decisions = sorted(trace["decision_landscape"], key=lambda item: item["stage_index"])
    by_index = {item["stage_index"]: item for item in decisions}
    origins = {}
    for cell in trace.get("matrix", []):
        if isinstance(cell, dict):
            for conflict_id in cell.get("conflict_ids", []):
                if isinstance(conflict_id, str) and cell.get("row_index") in by_index:
                    origins[conflict_id] = by_index[cell["row_index"]]
    snapshots = {}
    for decision in decisions:
        for item in decision["frontier_items"]:
            if item.get("kind") == "deferred_judgment":
                origins.setdefault(item["source_id"], decision)
                snapshots[item["source_id"]] = item

    # A conflict can fall out of the last-five snapshot window and still be open.
    observations = {}
    reviews = []
    for conflict_id in sorted(set(final) | set(snapshots)):
        item = snapshots.get(conflict_id, {})
        conflict = final.get(conflict_id, {})
        decision = origins.get(conflict_id)
        if decision is None:
            reviews.append({"state": "unmapped_conflict", "source": source, "source_id": conflict_id})
            continue
        resolved = conflict.get("resolved") if conflict else item.get("status") == "resolved"
        ref = {"source": source, "decision_id": decision.get("decision_id"), "source_id": conflict_id}
        if resolved:
            reviews.append({"state": "explicitly_resolved", "evidence": ref})
            continue
        conflict_type = conflict.get("type") or str(item.get("reason") or "").split(":", 1)[0].strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", conflict_type):
            conflict_type = "unknown"
        stage = _stage(decision)
        key = (*_stage_key(stage), conflict_type)
        observation = observations.setdefault(key, {"stage": stage, "conflict_type": conflict_type,
                                                    "evidence": [], "scores": []})
        observation["evidence"].append(ref)
        score = conflict.get("severity") if conflict else item.get("score")
        observation["scores"].append(float(score) if type(score) in (int, float) and math.isfinite(score) else None)
    return observations, reviews


def build_frontier_control_artifacts(paths: Iterable[str | Path]) -> tuple[dict[str, Any], dict[str, Any]]:
    from .frontier_replay import replay_loaded_runs

    loaded = []
    sources = []
    for path in paths:
        path = Path(path)
        raw = path.read_bytes()
        payload = json.loads(raw)
        _validate_run(payload)
        loaded.append((path, payload))
        sources.append({"file": path.name, "sha256": _sha256(raw),
                        "run_id": str(payload.get("run_id") or payload.get("started_at_utc") or path.stem)})
    if not loaded:
        raise ValueError("at least one run is required for frontier control")
    seeds = [(payload.get("seed") or payload["prompt"]).strip() for _, payload in loaded]
    if len(set(seeds)) != 1:
        raise ValueError("frontier control sources must have the same seed")
    report = replay_loaded_runs(loaded)
    current, reviews = _observations(loaded[-1][1], len(loaded) - 1)
    previous = {}
    if len(loaded) > 1:
        previous, _ = _observations(loaded[-2][1], len(loaded) - 2)
    latest_stages = {_stage_key(_stage(item)) for item in loaded[-1][1]["rpm_trace"]["decision_landscape"]}
    notes = []
    for key in sorted(set(current) | set(previous)):
        now, before = current.get(key), previous.get(key)
        observation = now or before
        if now:
            state = "observed_open"
            if before:
                state = "still_open"
                if len(now["scores"]) == len(before["scores"]) == 1:
                    a, b = before["scores"][0], now["scores"][0]
                    if a is not None and b is not None:
                        delta = round(b - a, 4)
                        state = "improved_but_open" if delta <= -0.05 else "worsened" if delta >= 0.05 else state
            elif len(loaded) > 1:
                prev_stages = {_stage_key(_stage(item)) for item in loaded[-2][1]["rpm_trace"]["decision_landscape"]}
                if _stage_key(now["stage"]) in prev_stages:
                    state = "new"
        else:
            if _stage_key(before["stage"]) not in latest_stages:
                reviews.append({"state": "stage_not_comparable", "evidence": before["evidence"]})
                continue
            state = "not_observed"
        notes.append({"stage": observation["stage"], "conflict_type": observation["conflict_type"],
                      "state": state, "guidance": _guidance(state, observation["conflict_type"]),
                      "evidence": (before["evidence"] if before else []) + (now["evidence"] if now else [])})
    priority = {state: index for index, state in enumerate(
        ("worsened", "new", "still_open", "improved_but_open", "observed_open", "not_observed"))}
    notes.sort(key=lambda note: (note["stage"]["index"], priority[note["state"]], note["conflict_type"]))
    kept = []
    counts: dict[tuple, int] = {}
    for note in notes:
        key = _stage_key(note["stage"])
        if len(kept) >= MAX_NOTES or counts.get(key, 0) >= MAX_NOTES_PER_STAGE:
            reviews.append({"state": "note_budget", "note": note})
            continue
        counts[key] = counts.get(key, 0) + 1
        kept.append({"note_id": f"fc{len(kept) + 1:03d}", **note})
    for transition in report["transitions"][-1:]:
        reviews.extend({"state": "review_only", "event": event} for event in transition["events"]
                       if event["kind"] != "deferred_judgment")
        reviews.extend({"state": "review_only", "ontology_growth": item} for item in transition["ontology_growth_gate"])
    profile = {"contract_version": FRONTIER_CONTROL_CONTRACT, "mode": "prompt_only",
               "seed_sha256": _sha256(seeds[-1].encode("utf-8")), "sources": sources,
               "notes": kept, "review_items": reviews}
    validate_frontier_control(profile)
    return report, profile


def validate_frontier_control(profile: Any) -> None:
    if (not isinstance(profile, dict) or profile.get("contract_version") != FRONTIER_CONTROL_CONTRACT
            or profile.get("mode") != "prompt_only"):
        raise ValueError("unsupported frontier control contract or mode")
    if not isinstance(profile.get("seed_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", profile["seed_sha256"]):
        raise ValueError("frontier control requires a seed SHA-256")
    sources = profile.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("frontier control requires source receipts")
    for source in sources:
        if (not isinstance(source, dict) or not isinstance(source.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", source["sha256"])
                or not isinstance(source.get("file"), str) or not isinstance(source.get("run_id"), str)):
            raise ValueError("invalid frontier control source receipt")
    notes = profile.get("notes")
    if not isinstance(notes, list) or len(notes) > MAX_NOTES:
        raise ValueError("frontier control note budget exceeded or notes missing")
    ids = set()
    counts: dict[tuple, int] = {}
    for note in notes:
        if not isinstance(note, dict) or not isinstance(note.get("note_id"), str) or not re.fullmatch(r"fc[0-9]{3}", note["note_id"]):
            raise ValueError("invalid frontier control note ID")
        if note["note_id"] in ids:
            raise ValueError("duplicate frontier control note ID")
        ids.add(note["note_id"])
        _validate_stage(note.get("stage"))
        key = _stage_key(note["stage"])
        counts[key] = counts.get(key, 0) + 1
        if counts[key] > MAX_NOTES_PER_STAGE:
            raise ValueError("frontier control per-stage note budget exceeded")
        state, kind = note.get("state"), note.get("conflict_type")
        if (not isinstance(state, str) or state not in OBSERVATIONS or not isinstance(kind, str)
                or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", kind)
                or note.get("guidance") != _guidance(state, kind)):
            raise ValueError("invalid frontier control observation or guidance")
        if not isinstance(note.get("evidence"), list) or not note["evidence"]:
            raise ValueError("frontier control note requires evidence")
        for ref in note["evidence"]:
            if (not isinstance(ref, dict) or type(ref.get("source")) is not int
                    or not 0 <= ref["source"] < len(sources) or not isinstance(ref.get("source_id"), str)
                    or not isinstance(ref.get("decision_id"), str)):
                raise ValueError("invalid frontier control evidence reference")
    if not isinstance(profile.get("review_items"), list):
        raise ValueError("frontier control requires a review_items list")


def load_frontier_control(path: str | Path, seed: str) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    profile = json.loads(raw)
    validate_frontier_control(profile)
    if profile["seed_sha256"] != _sha256(seed.strip().encode("utf-8")):
        raise ValueError("frontier control seed does not match this run")
    return {"file": Path(path).name, "sha256": _sha256(raw), "profile": profile}


def notes_for_stage(receipt: dict[str, Any] | None, stage: StageSpec, index: int) -> list[dict[str, Any]]:
    if not receipt:
        return []
    return [note for note in receipt["profile"]["notes"]
            if _stage_key(note["stage"]) == (index, stage.name, stage.operator)]


def format_frontier_control_context(notes: list[dict[str, Any]]) -> str:
    if not notes:
        return ""
    lines = ["Prior-run frontier reminders (optional):",
             "These are fallible observations, not score targets. Follow the current stage instruction."]
    lines.extend(f"- [{note['note_id']}] {note['guidance']}" for note in notes)
    return "\n".join(lines)
