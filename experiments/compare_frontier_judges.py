"""Compare fixed-passage judges without turning order agreement into human gold."""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from analyze_frontier_study import analyze, verify_manifest
from frontier_study import save

CATEGORIES = ("winner", "continuity", "restraint", "freshness")


def normalize(label: str, a_phase: str) -> str:
    return "tie" if label == "tie" else a_phase if label == "A" else "on" if a_phase == "off" else "off"


def metered_cost(records: list[dict]) -> dict:
    totals = collections.Counter()
    unknown_usage = 0
    for record in records:
        usage = record.get("usage") or {}
        if any(type(usage.get(key)) is not int for key in ("input_tokens", "output_tokens")):
            unknown_usage += 1
            continue
        details = usage.get("input_tokens_details") or {}
        writes = details.get("cache_write_tokens_details") or {}
        cached = details.get("cached_tokens", 0)
        write30 = writes.get("ttl_30m_tokens", 0)
        write12 = writes.get("ttl_12h_tokens", 0)
        if (details.get("cache_write_tokens", 0) != write30 + write12 or
                usage["input_tokens"] < cached + write30 + write12):
            unknown_usage += 1
            continue
        totals.update({"input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"],
            "cached_input_tokens": cached, "write_30m_tokens": write30, "write_12h_tokens": write12,
            "uncached_input_tokens": usage["input_tokens"] - cached - write30 - write12,
            "reasoning_output_tokens": (usage.get("output_tokens_details") or {}).get("reasoning_tokens", 0)})
    usd = (10 * totals["uncached_input_tokens"] + totals["cached_input_tokens"] +
           12.5 * totals["write_30m_tokens"] + 25 * totals["write_12h_tokens"] +
           50 * totals["output_tokens"]) / 1e6
    return {"token_totals": dict(totals), "records_without_metered_usage": unknown_usage,
            "estimated_usd_for_metered_records": usd, "complete_estimated_usd": usd if not unknown_usage else None,
            "pricing_source": "https://developers.openai.com/api/docs/pricing", "pricing_date": "2026-10-27",
            "claim_limit": "usage-times-published-rates estimate, not invoice; reasoning tokens are included in output_tokens"}


def describe_judge(root: Path, studies: list[Path]) -> dict:
    manifest = verify_manifest(root)
    config = json.loads((root / "frozen.json").read_text())
    records = [json.loads(path.read_text()) for path in sorted((root / "judgments").glob("*.json"))]
    models = []
    for study in studies:
        audited = analyze(study, root)
        rows = audited["pairs"]
        by_prompt = {}
        for row in rows:
            by_prompt.setdefault(row["prompt_id"], collections.Counter())[row["blind_preference"]] += 1
        alignment = collections.Counter()
        for row in rows:
            if not row["dosed"] or row["blind_preference"] not in ("on", "off"):
                continue
            predicted = "on" if row["path_delta"] > 0 else "off" if row["path_delta"] < 0 else "tie"
            alignment["zero_score_delta" if predicted == "tie" else "same_direction"
                      if predicted == row["blind_preference"] else "opposite_direction"] += 1
        category_orders = {}
        for key in CATEGORIES:
            tally = collections.Counter()
            for row in rows:
                normalized = []
                for order in (0, 1):
                    path = root / "judgments" / f"{study.name}-{row['prompt_id']}-r{row['replicate']:02d}-o{order}.json"
                    record = json.loads(path.read_text()) if path.exists() else {}
                    normalized.append(normalize(record["judgment"][key], record["study"]["a_phase"])
                                      if record.get("status") == "complete" else None)
                category = ("invalid_or_missing" if None in normalized else "consistent" if normalized[0] == normalized[1]
                            else "order_disagreement")
                tally[category] += 1
            category_orders[key] = dict(tally)
        models.append({key: audited[key] for key in ("model_id", "directory", "manifest_sha256", "planned_pairs",
            "completed_pairs", "dosed_pairs", "dosed_prompt_clusters", "blind_preference", "blind_unknown_reasons",
            "dosed_blind_preference", "judge_presented_prompts_verified")} | {
                "no_dose_blind_preference": dict(collections.Counter(row["blind_preference"] for row in rows if not row["dosed"])),
                "by_prompt": {key: dict(value) for key, value in by_prompt.items()},
                "category_order_consistency": category_orders,
                "dosed_directional_heuristic_alignment": dict(alignment),
                "pairs": [{key: row[key] for key in ("prompt_id", "replicate", "dosed", "blind_preference",
                                                    "order_preferences", "run_sha256", "path_delta", "char_delta")} for row in rows]})
    return {"directory": root.name, "manifest_sha256": manifest, "requested_model": config["judge_model"],
            "returned_models": dict(collections.Counter(record["api"].get("model") for record in records if "api" in record)),
            "frozen": config, "status": json.loads((root / "status.json").read_text()),
            "record_statuses": dict(collections.Counter(record["status"] for record in records)),
            "label_counts": {key: dict(collections.Counter(record["judgment"][key] for record in records
                             if record["status"] == "complete")) for key in CATEGORIES},
            "metered_cost": metered_cost(records) if config.get("endpoint") == "https://api.openai.com/v1" else None,
            "models": models}


def compare(studies: list[Path], previous: Path, current: Path) -> dict:
    old, new = [describe_judge(path, studies) for path in (previous, current)]
    transitions = collections.Counter()
    for left, right in zip(old["models"], new["models"]):
        if left["manifest_sha256"] != right["manifest_sha256"]:
            raise ValueError("comparison source mismatch")
        for before, after in zip(left["pairs"], right["pairs"]):
            if before["run_sha256"] != after["run_sha256"]:
                raise ValueError("comparison passage mismatch")
            transitions[f"{before['blind_preference']}->{after['blind_preference']}"] += 1
    return {"contract": "frontier-judge-comparison-1.0", "previous": old, "current": new,
            "preference_transitions": dict(transitions),
            "claim_limits": ["same 91 complete pairs; five generator pairs remain incomplete",
                "eight shared authored prompt clusters, four replicates; no independent-pair inference",
                "judge model, backend, renderer, reasoning, sampling, and output allowance differ",
                "order consistency is necessary diagnostic evidence, not literary correctness or human gold",
                "dosed and no-dose results are descriptive; no automatic tuning or candidate revival"]}


def plot(report: dict, output: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    old, new = report["previous"], report["current"]
    figure, axes = plt.subplots(1, 2, figsize=(10, 3.8), constrained_layout=True)
    labels = ["Gemma 4B", "Gemma 12B", "GPT-OSS 20B"]
    for offset, judge, color, name in ((-0.18, old, "#899599", "Nemo 12B"),
                                     (0.18, new, "#247c8d", "GPT-6 Astra")):
        counts = [sum(m["blind_preference"].get(key, 0) for key in ("on", "off", "tie")) for m in judge["models"]]
        rates = [100 * count / m["completed_pairs"] for count, m in zip(counts, judge["models"])]
        bars = axes[0].bar([i + offset for i in range(len(labels))], rates, width=0.34, color=color, label=name)
        axes[0].bar_label(bars, labels=[f"{n}/{m['completed_pairs']}" for n, m in zip(counts, judge["models"])], fontsize=9, padding=3)
    axes[0].set_xticks(range(len(labels)), labels)
    axes[0].set_ylim(0, 115)
    axes[0].set_yticks([0, 25, 50, 75, 100])
    axes[0].set_ylabel("Order-consistent pairs (%)")
    axes[0].legend(frameon=False, loc="upper left", fontsize=8)
    keys = ("on", "off", "tie", "unknown")
    colors = ("#247c8d", "#d5634e", "#d9bd57", "#abb2b4")
    left = [0] * len(labels)
    for key, color in zip(keys, colors):
        counts = [m["dosed_blind_preference"].get(key, 0) for m in new["models"]]
        bars = axes[1].barh(range(len(labels)), counts, left=left, color=color, label=key)
        for i, count in enumerate(counts):
            if count:
                axes[1].text(left[i] + count / 2, i, str(count), ha="center", va="center", fontsize=10)
        left = [a + b for a, b in zip(left, counts)]
    axes[1].set_yticks(range(len(labels)), labels)
    axes[1].set_xlabel("Dosed complete pairs, API judge")
    axes[1].legend(frameon=False, loc="lower right", fontsize=8)
    axes[1].set_xlim(0, max(left) + 1)
    for axis in axes:
        axis.spines[["top", "right"]].set_visible(False)
    figure.suptitle("Same 91 pairs; order consistency is not human-gold correctness", fontsize=11)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=170)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--studies", type=Path, nargs="+", required=True)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plot", type=Path)
    args = parser.parse_args()
    report = compare(args.studies, args.previous, args.current)
    save(args.output, report)
    if args.plot:
        plot(report, args.plot)
    print(json.dumps({"labels": report["current"]["label_counts"]["winner"],
                      "models": [{key: model[key] for key in ("model_id", "blind_preference", "dosed_blind_preference")}
                                 for model in report["current"]["models"]],
                      "cost": report["current"]["metered_cost"]}, indent=2))


if __name__ == "__main__":
    main()
