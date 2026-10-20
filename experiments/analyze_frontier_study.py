"""Audit saved evidence and describe coverage, adherence, and blind judgments."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import statistics
from pathlib import Path

from frontier_study import canonical, complete_pairs, save
from furnace_runtime import digest


def verify_manifest(root: Path) -> str:
    manifest = json.loads((root / "manifest.json").read_text())
    if canonical(manifest["files"]) != manifest["sha256"]:
        raise ValueError(f"manifest identity mismatch: {root.name}")
    inventory = {str(path.relative_to(root)) for path in root.rglob("*.json") if path.name != "manifest.json"}
    if inventory != set(manifest["files"]):
        raise ValueError(f"manifest inventory mismatch: {root.name}")
    for relative, expected in manifest["files"].items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file() or digest(path) != expected:
            raise ValueError(f"artifact integrity failure: {root.name}/{relative}")
    return digest(root / "manifest.json")


def verify_judge_source(judge: Path, study: Path, manifest_sha: str) -> None:
    config = json.loads((judge / "frozen.json").read_text())
    sources = [value for name, value in config["studies"].items() if Path(name).name == study.name]
    if sources != [manifest_sha]:
        raise ValueError(f"judge source manifest mismatch: {study.name}")


def describe(values: list[float]) -> dict:
    return {"count": len(values), "mean": statistics.mean(values) if values else None,
            "median": statistics.median(values) if values else None,
            "min": min(values) if values else None, "max": max(values) if values else None}


def analyze(study: Path, judge: Path | None = None) -> dict:
    manifest_sha = verify_manifest(study)
    if judge:
        verify_judge_source(judge, study, manifest_sha)
    config = json.loads((study / "frozen.json").read_text())
    model_identity = json.loads((study / "model_identity.json").read_text()) if (study / "model_identity.json").exists() else None
    runtime = json.loads((study / "runtime.json").read_text()) if (study / "runtime.json").exists() else None
    trials = [json.loads(path.read_text()) for path in (study / "runs").glob("*.json")]
    by_phase = {}
    for phase in ("calibration", "off", "on"):
        group = [trial for trial in trials if trial["study"]["phase"] == phase]
        by_phase[phase] = dict(collections.Counter(trial["status"] for trial in group))
    profiles = {path.stem: json.loads(path.read_text()) for path in (study / "profiles").glob("*.json")}
    for prompt_id, profile in profiles.items():
        source = study / "runs" / f"{prompt_id}-calibration-r00.json"
        if profile["sources"][0]["sha256"] != digest(source):
            raise ValueError("calibration provenance mismatch")
    calls = [json.loads(path.read_text()) for path in (study / "calls").glob("*.json")]
    request_batches = [batch for path in (study / "sessions").glob("*/requests.json")
                       for batch in json.loads(path.read_text())]
    requests = [request for batch in request_batches for request in batch.get("requests", [])]
    seconds = sum(batch.get("elapsed_seconds", 0) for batch in request_batches)
    tokens = sum(request["completion_tokens"] for request in requests)
    rows = []
    lengths = {"off": [], "on": []}
    step_lengths = {"off": [], "on": []}
    preferences = collections.Counter()
    order_unknown = collections.Counter()
    reuse = collections.Counter()
    root_replay = collections.Counter()
    presented_prompts_verified = 0
    for _, item, replicate, paths, runs in complete_pairs(study):
        control = runs[1]["frontier_control"]
        if control["sha256"] != digest(study / "profiles" / f"{item['id']}.json"):
            raise ValueError("delivered control profile hash mismatch")
        applied = len(control["applied_note_ids"])
        row = {"prompt_id": item["id"], "replicate": replicate, "dosed": applied > 0,
               "applied_note_ids": control["applied_note_ids"], "identical_final": runs[0]["final"] == runs[1]["final"],
               "run_files": [f"{study.name}/runs/{path.name}" for path in paths],
               "run_sha256": [digest(path) for path in paths],
               "path_delta": runs[1]["final_state"]["path_score"] - runs[0]["final_state"]["path_score"],
               "char_delta": len(runs[1]["final"]) - len(runs[0]["final"])}
        if not applied:
            for ordinal in (0, 1):
                source_calls = [study / "calls" / f"{item['id']}-{phase}-r{replicate:02d}-q{ordinal:02d}.json"
                                for phase in ("off", "on")]
                if all(path.exists() for path in source_calls):
                    left, right = [json.loads(path.read_text()) for path in source_calls]
                    root_replay["paired_root_calls"] += 1
                    same = left["sampling_seed"] == right["sampling_seed"] and left["request"] == right["request"]
                    root_replay["matching_input_and_seed"] += int(same)
                    if same and left["status"] == right["status"] == "complete":
                        root_replay["identical_output"] += int(left["result"]["text"] == right["result"]["text"])
        candidates = []
        for phase, run in zip(("off", "on"), runs):
            lengths[phase].append(len(run["final"]))
            step_lengths[phase].extend(len(step["accepted"]["output"]) for step in run["steps"])
            candidates.append({(step["index"], candidate["candidate_id"]): candidate["output"]
                               for step in run["steps"]
                               for candidate in [step["accepted"], *step["rejected"], *step["repaired"]]})
        for key in set(candidates[0]) & set(candidates[1]):
            reuse["shared_ids"] += 1
            reuse["same_text" if candidates[0][key] == candidates[1][key] else "different_text"] += 1
        if judge:
            records = []
            for order in (0, 1):
                path = judge / "judgments" / f"{study.name}-{item['id']}-r{replicate:02d}-o{order}.json"
                record = json.loads(path.read_text()) if path.exists() else {}
                if record:
                    spec = record["study"]
                    if (spec["input_sha256"] != row["run_sha256"] or spec["generator"] != study.name
                            or spec["prompt_id"] != item["id"] or spec["replicate"] != replicate
                            or spec["a_phase"] != ("on" if order else "off")):
                        raise ValueError("judge passage provenance mismatch")
                    if record.get("status") == "complete":
                        left, right = runs[::-1] if order else runs
                        presented = f"Seed:\n{item['seed']}\n\nPassage A:\n{left['final']}\n\nPassage B:\n{right['final']}"
                        if (record.get("usage") or {}).get("prompt_sha256") != hashlib.sha256(presented.encode()).hexdigest():
                            raise ValueError("judge presented prompt mismatch")
                        presented_prompts_verified += 1
                records.append(record)
            orders = [record.get("preferred_phase") if record.get("status") == "complete" else None for record in records]
            if any(value is None for value in orders):
                preference = "unknown"
                order_unknown["invalid_or_missing"] += 1
            elif orders[0] != orders[1]:
                preference = "unknown"
                order_unknown["order_disagreement"] += 1
            else:
                preference = orders[0]
            row.update(blind_preference=preference, order_preferences=orders)
            preferences[preference] += 1
        rows.append(row)
    active = [row for row in rows if row["dosed"]]
    empty = [row for row in rows if not row["dosed"]]
    return {"model_id": config["model_id"], "directory": study.name, "manifest_sha256": manifest_sha,
            "terminal_status": json.loads((study / "status.json").read_text()),
            "frozen_sha256": digest(study / "frozen.json"), "model_identity": model_identity, "runtime": runtime,
            "source": config["source"], "backend": config["backend"], "max_tokens": config["max_tokens"],
            "fallback_receipt": config.get("fallback_receipt"),
            "harmony_render_contract": config.get("harmony_render_contract"),
            "planned_pairs": config["planned_pairs"], "completed_pairs": len(rows), "phase_statuses": by_phase,
            "profile_note_counts": {key: len(value["notes"]) for key, value in sorted(profiles.items())},
            "calibration_eligible_pairs": sum(bool(value["notes"]) for value in profiles.values()) * config["replicates"],
            "calibration_eligible_prompt_clusters": sum(bool(value["notes"]) for value in profiles.values()),
            "dosed_pairs": len(active), "dosed_prompt_clusters": len({row["prompt_id"] for row in active}),
            "dosed_path_delta": describe([row["path_delta"] for row in active]),
            "no_dose_path_delta": describe([row["path_delta"] for row in empty]),
            "no_dose_pairs": len(empty), "identical_no_dose_finals": sum(row["identical_final"] for row in empty),
            "no_dose_root_replay": dict(root_replay),
            "final_chars": {key: describe(value) for key, value in lengths.items()},
            "accepted_step_length_compliance": {key: {"within_140_240": sum(140 <= value <= 240 for value in values),
                     "completed_paired_steps": len(values)} for key, values in step_lengths.items()},
            "candidate_identity": dict(reuse), "blind_preference": dict(preferences) if judge else None,
            "judge_presented_prompts_verified": presented_prompts_verified if judge else None,
            "blind_unknown_reasons": dict(order_unknown),
            "dosed_blind_preference": dict(collections.Counter(row["blind_preference"] for row in active)) if judge else None,
            "requests_including_canary": len(requests), "request_statuses": dict(collections.Counter(row["status"] for row in requests)),
            "completion_tokens_including_canary": tokens, "engine_batch_seconds": seconds,
            "engine_completion_tokens_per_second": tokens / seconds if seconds else None,
            "saved_call_statuses": dict(collections.Counter(call["status"] for call in calls)), "pairs": rows}


def plot(models: list[dict], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure, axes = plt.subplots(1, 3, figsize=(12, 3.8), constrained_layout=True)
    labels = [model["model_id"].split("/")[-1] for model in models]
    positions = range(len(models))
    axes[0].bar(positions, [model["planned_pairs"] for model in models], color="#dce2e4", label="planned")
    axes[0].bar(positions, [model["completed_pairs"] for model in models], color="#287b91", label="complete")
    axes[0].bar(positions, [model["dosed_pairs"] for model in models], color="#d64e45", label="dosed")
    axes[0].set_title("Coverage, paired units")
    axes[0].legend(frameon=False, fontsize=8)
    for column, key, title in ((1, "path_delta", "Heuristic path score: on - off"),
                                (2, "char_delta", "Final characters: on - off")):
        axes[column].axhline(0, color="#737d83", linewidth=0.8)
        for index, model in enumerate(models):
            for row in model["pairs"]:
                jitter = (int(row["prompt_id"][1:]) - 4.5) * 0.018 + row["replicate"] * 0.008
                axes[column].scatter(index + jitter, row[key], s=17,
                    color="#d64e45" if row["dosed"] else "#9ba6ab", alpha=0.8)
        axes[column].set_title(title)
    for axis in axes:
        axis.set_xticks(list(positions), labels, rotation=15, ha="right", fontsize=8)
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", alpha=0.15)
    figure.suptitle("Exploratory fixed-bank study; red = reminders applied", fontsize=11)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=170)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--studies", type=Path, nargs="+", required=True)
    parser.add_argument("--judge", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plot", type=Path)
    args = parser.parse_args()
    judge_sha = verify_manifest(args.judge) if args.judge else None
    models = [analyze(path, args.judge) for path in args.studies]
    judge_report = None
    if args.judge:
        records = [json.loads(path.read_text()) for path in sorted((args.judge / "judgments").glob("*.json"))]
        judge_report = {
            "frozen": json.loads((args.judge / "frozen.json").read_text()),
            "model_identity": json.loads((args.judge / "model_identity.json").read_text())
                              if (args.judge / "model_identity.json").exists() else None,
            "runtime": json.loads((args.judge / "runtime.json").read_text())
                       if (args.judge / "runtime.json").exists() else None,
            "status": json.loads((args.judge / "status.json").read_text()),
            "record_statuses": dict(collections.Counter(record.get("status") for record in records)),
            "label_counts": {key: dict(collections.Counter(record["judgment"][key] for record in records
                             if record.get("status") == "complete"))
                             for key in ("winner", "continuity", "restraint", "freshness")},
            "presented_prompts_verified_for_requested_studies": sum(model["judge_presented_prompts_verified"] for model in models),
            "claim_limit": "valid JSON is not judge qualification; evaluate order consistency separately",
        }
    save(args.output, {"contract": "frontier-study-audit-1.0", "judge_manifest_sha256": judge_sha,
         "judge": judge_report, "models": models, "analysis_scope": "coverage and adherence are descriptive; no outcome-based case selection or reward tuning",
         "claim_limits": ["eight authored prompt clusters per model", "model judgments are not human gold",
                          "model family, quantization, and backend confound size comparisons"]})
    if args.plot:
        plot(models, args.plot)
    print(json.dumps({"verified_models": len(models), "output": str(args.output)}))


if __name__ == "__main__":
    main()
