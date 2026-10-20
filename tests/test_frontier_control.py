from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Sequence
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from magic_realism_thought.cli import main as generate
from magic_realism_thought.frontier_control import (
    MAX_NOTES,
    MAX_NOTES_PER_STAGE,
    build_frontier_control_artifacts,
    format_frontier_control_context,
    load_frontier_control,
    notes_for_stage,
    validate_frontier_control,
)
from magic_realism_thought.frontier_replay import main as replay
from magic_realism_thought.providers import DryRunProvider
from magic_realism_thought.types import StageSpec


class FrontierControlTest(unittest.TestCase):
    def setUp(self) -> None:
        self.paths = [ROOT / f"examples/frontiers/replay_run_{letter}.json" for letter in "ab"]
        self.payloads = [json.loads(path.read_bytes()) for path in self.paths]
        self.seed = self.payloads[0]["seed"]
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.tmp = Path(self.directory.name)

    def write(self, name: str, payload: dict) -> Path:
        path = self.tmp / name
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def build(self, *payloads: dict) -> dict:
        paths = [self.write(f"run_{i}.json", payload) for i, payload in enumerate(payloads)]
        return build_frontier_control_artifacts(paths)[1]

    def cli(self, output: str, extra: Sequence[str] = (), *, finish: bool = False) -> dict:
        path = self.tmp / output
        args = ["--dry-run", "--provider", "openai", "--prompt", self.seed,
                "--stages-file", str(ROOT / "examples/frontiers/control_stages.json"),
                "--no-memory-update",
                "--candidates", "2", "--include-prompts", "--output-json", str(path), *extra]
        if not finish:
            args.extend(["--no-aggregate", "--no-recursive-closure"])
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(generate(args), 0)
        return json.loads(path.read_bytes())

    def test_export_preserves_sources_and_qualifies_absence(self) -> None:
        before = [path.read_bytes() for path in self.paths]
        report, profile = build_frontier_control_artifacts(self.paths)
        self.assertEqual(profile, build_frontier_control_artifacts(self.paths)[1])
        self.assertEqual(profile, json.loads((ROOT / "examples/frontiers/frontier_control.json").read_bytes()))
        self.assertEqual(before, [path.read_bytes() for path in self.paths])
        self.assertEqual([source["sha256"] for source in profile["sources"]],
                         [hashlib.sha256(raw).hexdigest() for raw in before])
        states = {note["conflict_type"]: note["state"] for note in profile["notes"]}
        self.assertEqual(states, {"symbol_loss": "not_observed", "operator_mismatch": "improved_but_open",
                                  "high_drift": "observed_open"})
        self.assertIn("resolved", {event["state"] for event in report["transitions"][0]["events"]})
        self.assertNotIn("resolved", states.values())
        self.assertTrue(any("ontology_growth" in item for item in profile["review_items"]))
        self.assertTrue(any(item.get("event", {}).get("state") == "contradicted_prior_abandonment"
                            for item in profile["review_items"]))
        self.assertNotIn(str(ROOT), json.dumps(profile))

    def test_final_conflict_flags_override_historical_snapshots(self) -> None:
        payload = self.payloads[0]
        decision = payload["rpm_trace"]["decision_landscape"][0]
        source = decision["frontier_items"][-1]["source_id"]
        payload["rpm_trace"]["conflicts"] = [
            {"conflict_id": source, "type": "symbol_loss", "resolved": True, "severity": 0.8},
            {"conflict_id": "outside-window", "type": "collapse", "resolved": False, "severity": 0.9},
        ]
        payload["rpm_trace"]["matrix"] = [{"row_index": 1, "conflict_ids": [source, "outside-window"]}]
        profile = self.build(payload)
        types = {note["conflict_type"] for note in profile["notes"]}
        self.assertNotIn("symbol_loss", types)
        self.assertIn("collapse", types)
        self.assertTrue(any(item["state"] == "explicitly_resolved" for item in profile["review_items"]))

    def test_repeated_snapshot_keeps_original_stage_and_multiple_sources(self) -> None:
        payload = self.payloads[0]
        first, second = payload["rpm_trace"]["decision_landscape"]
        original = first["frontier_items"][-1]
        second["frontier_items"].append(copy.deepcopy(original))
        duplicate = {**original, "source_id": "another-symbol-concern"}
        first["frontier_items"].append(duplicate)
        profile = self.build(payload)
        symbols = [note for note in profile["notes"] if note["conflict_type"] == "symbol_loss"]
        self.assertEqual(len(symbols), 1)
        self.assertEqual(symbols[0]["stage"]["index"], 1)
        self.assertEqual(len(symbols[0]["evidence"]), 2)

    def test_changed_stage_does_not_inherit_comparison_or_reminders(self) -> None:
        after = self.payloads[1]
        after["rpm_trace"]["decision_landscape"][0]["stage_name"] = "a different stage"
        profile = self.build(self.payloads[0], after)
        self.assertNotIn("symbol_loss", {note["conflict_type"] for note in profile["notes"]})
        self.assertTrue(any(item["state"] == "stage_not_comparable" for item in profile["review_items"]))
        receipt = {"profile": profile}
        self.assertFalse(notes_for_stage(receipt, StageSpec("renamed", "expander", "...", "perturb"), 2))
        self.assertFalse(notes_for_stage(receipt, StageSpec("quiet impossibility", "expander", "...", "changed"), 2))
        self.assertFalse(notes_for_stage(receipt, StageSpec("quiet impossibility", "expander", "...", "perturb"), 1))

    def test_severity_trends_and_new_observation(self) -> None:
        for score, expected in ((0.9, "worsened"), (0.8, "still_open"), (0.7, "improved_but_open"),
                                (None, "still_open")):
            with self.subTest(score=score):
                after = copy.deepcopy(self.payloads[0])
                after["rpm_trace"]["decision_landscape"][0]["frontier_items"][-1]["score"] = score
                profile = self.build(self.payloads[0], after)
                self.assertEqual(profile["notes"][0]["state"], expected)
        before = copy.deepcopy(self.payloads[0])
        before["rpm_trace"]["decision_landscape"][0]["frontier_items"] = []
        profile = self.build(before, self.payloads[0])
        self.assertEqual(profile["notes"][0]["state"], "new")

    def test_bounds_retain_omitted_evidence_and_never_copy_source_instructions(self) -> None:
        payload = self.payloads[0]
        first = payload["rpm_trace"]["decision_landscape"][0]
        item = first["frontier_items"][-1]
        first["frontier_items"] = [
            {**item, "source_id": f"concern-{i}", "reason": f"custom_type_{i}: injected-source-text",
             "next_action": "injected-source-text"} for i in range(8)]
        template = copy.deepcopy(first)
        payload["rpm_trace"]["decision_landscape"] = [
            {**copy.deepcopy(template), "stage_index": i} for i in range(1, 12)]
        for decision in payload["rpm_trace"]["decision_landscape"]:
            for frontier in decision["frontier_items"]:
                frontier["source_id"] += f"-stage-{decision['stage_index']}"
        profile = self.build(payload)
        self.assertEqual(len(profile["notes"]), MAX_NOTES)
        self.assertEqual(len([note for note in profile["notes"] if note["stage"]["index"] == 1]),
                         MAX_NOTES_PER_STAGE)
        self.assertTrue(any(item["state"] == "note_budget" for item in profile["review_items"]))
        self.assertNotIn("injected-source-text", format_frontier_control_context(profile["notes"][:3]))
        profile["notes"][0]["guidance"] = "injected-source-text"
        with self.assertRaisesRegex(ValueError, "guidance"):
            validate_frontier_control(profile)

    def test_invalid_sources_and_mixed_seeds_fail(self) -> None:
        for transform in (
            lambda p: p.update(rpm_trace=None),
            lambda p: p["rpm_trace"].update(decision_landscape=[]),
            lambda p: p["rpm_trace"]["decision_landscape"][0].pop("frontier_items"),
            lambda p: p["rpm_trace"].update(matrix=None),
            lambda p: p["rpm_trace"]["decision_landscape"][0].update(contract_version="future"),
        ):
            payload = copy.deepcopy(self.payloads[0])
            transform(payload)
            with self.assertRaises(ValueError):
                self.build(payload)
        after = copy.deepcopy(self.payloads[1])
        after["seed"] = "a different seed"
        with self.assertRaisesRegex(ValueError, "same seed"):
            self.build(self.payloads[0], after)

    def test_cli_round_trip_receipts_and_unchanged_scores_for_fixed_outputs(self) -> None:
        control = self.tmp / "control.json"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(replay([*map(str, self.paths), "--output-control", str(control)]), 0)
        baseline = self.cli("baseline.json", ["--beam-width", "2", "--accept-threshold", "1"])
        controlled = self.cli("controlled.json", ["--frontier-control", str(control), "--beam-width", "2",
                                                  "--accept-threshold", "1"])
        self.assertIsNone(baseline["frontier_control"])
        receipt = controlled["frontier_control"]
        self.assertEqual(load_frontier_control(control, self.seed)["profile"], receipt["profile"])
        self.assertEqual(receipt["sha256"], hashlib.sha256(control.read_bytes()).hexdigest())
        self.assertEqual(receipt["applied_note_ids"], ["fc001", "fc002", "fc003"])
        self.assertFalse(receipt["unused_note_ids"])
        self.assertEqual(baseline["final"], controlled["final"])
        self.assertEqual(baseline["final_state"]["path_score"], controlled["final_state"]["path_score"])
        for before, after in zip(baseline["steps"], controlled["steps"]):
            self.assertEqual(before["accepted"]["reward"], after["accepted"]["reward"])
            candidates = [after["accepted"], *after["rejected"], *after["repaired"]]
            self.assertTrue(after["repaired"])
            for candidate in candidates:
                for note_id in candidate["frontier_note_ids"]:
                    self.assertIn(f"[{note_id}]", candidate["prompt"])
        # A generated run is itself accepted by the next export, not only fixtures.
        _, next_profile = build_frontier_control_artifacts([self.tmp / "controlled.json"])
        validate_frontier_control(next_profile)

    def test_module_entrypoint_exports_without_import_cycle(self) -> None:
        output = self.tmp / "module-control.json"
        result = subprocess.run(
            [sys.executable, "-W", "error", "-m", "magic_realism_thought.frontier_replay",
             *map(str, self.paths), "--output-control", str(output)],
            cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT / "src")}, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        validate_frontier_control(json.loads(output.read_bytes()))

    def test_judge_does_not_receive_frontier_context(self) -> None:
        profile = self.build(*self.payloads)
        control = self.write("control.json", profile)
        calls = []

        class RecordingProvider(DryRunProvider):
            def generate(self, request):
                calls.append(request)
                return super().generate(request)

        with patch("magic_realism_thought.runner.build_provider", side_effect=lambda name, **kw: RecordingProvider(name)):
            self.cli("hybrid.json", ["--frontier-control", str(control), "--prm", "hybrid"])
        judges = [request for request in calls if "Return JSON only" in request.prompt]
        generators = [request for request in calls if request not in judges]
        self.assertTrue(judges)
        self.assertTrue(any("Prior-run frontier reminders" in request.prompt for request in generators))
        self.assertTrue(all("Prior-run frontier reminders" not in request.prompt for request in judges))
        self.assertTrue(all("[fc" not in request.prompt for request in judges))

    def test_aggregation_and_closure_receive_their_own_notes(self) -> None:
        baseline = self.cli("finished-baseline.json", finish=True)
        source = copy.deepcopy(baseline)
        source["rpm_trace"]["conflicts"] = []
        source["rpm_trace"]["matrix"] = []
        for decision in source["rpm_trace"]["decision_landscape"]:
            decision["frontier_items"] = []
        for decision in source["rpm_trace"]["decision_landscape"][-2:]:
            decision["frontier_items"] = [{"kind": "deferred_judgment", "source_id": f"check-{decision['stage_index']}",
                                            "status": "open", "reason": "weak_closure: fixture concern"}]
        control = self.write("control.json", self.build(source))
        controlled = self.cli("finished-controlled.json", ["--frontier-control", str(control)], finish=True)
        self.assertEqual(controlled["final"], baseline["final"])
        for step in controlled["steps"][:-2]:
            self.assertFalse(step["accepted"]["frontier_note_ids"])
        for index, step in enumerate(controlled["steps"][-2:], 1):
            self.assertEqual(step["accepted"]["frontier_note_ids"], [f"fc00{index}"])
            self.assertIn(f"[fc00{index}]", step["accepted"]["prompt"])

    def test_export_and_generation_do_not_overwrite_control_sources(self) -> None:
        source = self.write("source.json", self.payloads[0])
        saved = source.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(replay([str(source), "--output-control", str(source)]), 2)
        self.assertEqual(source.read_bytes(), saved)
        control = self.write("control.json", self.build(*self.payloads))
        saved = control.read_bytes()
        with patch("magic_realism_thought.runner.build_provider") as provider:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(generate(["--dry-run", "--prompt", self.seed, "--frontier-control", str(control),
                                           "--output-json", str(control)]), 2)
        provider.assert_not_called()
        self.assertEqual(control.read_bytes(), saved)

    def test_seed_mismatch_and_missing_file_stop_before_provider_calls(self) -> None:
        control = self.write("control.json", self.build(*self.payloads))
        for extra in (["--frontier-control", str(control), "--prompt", "a different seed"],
                      ["--frontier-control", str(self.tmp / "missing.json")]):
            with patch("magic_realism_thought.runner.build_provider") as provider:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    status = generate(["--dry-run", "--prompt", self.seed, *extra])
            self.assertEqual(status, 2)
            provider.assert_not_called()

    def test_unmatched_notes_are_reported_as_unused(self) -> None:
        control = self.write("control.json", self.build(*self.payloads))
        stages = self.write("stages.json", [{"name": "different", "role": "expander",
                                            "operator": "different", "instruction": "Write a scene."}])
        run = self.cli("unmatched.json", ["--frontier-control", str(control), "--stages-file", str(stages)])
        self.assertFalse(run["frontier_control"]["applied_note_ids"])
        self.assertEqual(len(run["frontier_control"]["unused_note_ids"]), 3)
        self.assertNotIn("Prior-run frontier reminders", run["steps"][0]["accepted"]["prompt"])


if __name__ == "__main__":
    unittest.main()
