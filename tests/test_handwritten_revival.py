from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from magic_realism_thought.frontier_replay import build_frontier_replay_report
from magic_realism_thought.story_reader import build_story_reader, main, render_story_reader


class HandwrittenRevivalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.paths = [ROOT / f"examples/frontiers/handwritten_revival/run_{letter}.json" for letter in "ab"]
        self.payloads = [json.loads(path.read_text(encoding="utf-8")) for path in self.paths]
        self.reader = build_story_reader(self.paths)

    def test_full_prose_and_source_are_preserved_for_every_candidate(self) -> None:
        for path, payload, run in zip(self.paths, self.payloads, self.reader["runs"]):
            with self.subTest(run=run["id"]):
                self.assertEqual(len(run["stages"]), 1)
                decision = payload["rpm_trace"]["decision_landscape"][0]
                candidates = run["stages"][0]["candidates"]
                self.assertEqual(len(candidates), 2)
                self.assertEqual(sum(candidate["selected"] for candidate in candidates), 1)
                self.assertEqual(sum(candidate["discarded"] for candidate in candidates), 1)
                for candidate, saved in zip(candidates, decision["candidates"]):
                    self.assertEqual(candidate["id"], saved["candidate_id"])
                    self.assertEqual(candidate["output"], saved["output"])
                    self.assertEqual(len(candidate["output"].split("\n\n")), 3)
                    self.assertEqual(candidate["status"], saved["status"])
                    self.assertEqual(candidate["reasons"], saved["reasons"])
                    self.assertEqual(candidate["text_source"],
                                     "rpm_trace.decision_landscape[stage_index=1]."
                                     f"candidates[candidate_id={candidate['id']}].output")
                self.assertEqual(run["final"], payload["final"])
                self.assertEqual(run["final"], next(candidate["output"] for candidate in candidates if candidate["selected"]))
                self.assertEqual(run["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_same_discarded_passage_returns_via_existing_replay(self) -> None:
        before, after = self.reader["runs"]
        before_candidates = {candidate["id"]: candidate for candidate in before["stages"][0]["candidates"]}
        after_candidates = {candidate["id"]: candidate for candidate in after["stages"][0]["candidates"]}
        revived_id = "handwritten-s01-c02"
        self.assertEqual(set(before_candidates), set(after_candidates))
        for candidate_id in before_candidates:
            self.assertEqual(before_candidates[candidate_id]["output"], after_candidates[candidate_id]["output"])
            self.assertIsNone(before_candidates[candidate_id]["revived_from"])
        self.assertTrue(before_candidates[revived_id]["discarded"])
        self.assertFalse(before_candidates[revived_id]["selected"])
        self.assertTrue(after_candidates[revived_id]["selected"])
        self.assertFalse(after_candidates[revived_id]["discarded"])
        self.assertEqual(after_candidates[revived_id]["revived_from"], before["id"])
        self.assertTrue(after_candidates["handwritten-s01-c01"]["discarded"])
        self.assertIsNone(after_candidates["handwritten-s01-c01"]["revived_from"])
        existing = build_frontier_replay_report(self.paths)
        transition = self.reader["replay"]["transitions"][0]
        self.assertEqual(transition["events"], existing["transitions"][0]["events"])
        self.assertEqual(len(transition["events"]), 1)
        self.assertEqual(transition["events"][0]["state"], "contradicted_prior_abandonment")
        self.assertEqual(transition["events"][0]["stage_key"], "stage:1")
        self.assertEqual(transition["events"][0]["current_accepted"], revived_id)
        self.assertEqual(transition["ontology_growth_gate"], [])

    def test_handwritten_provenance_and_absence_of_measurements(self) -> None:
        def assert_unmeasured(value: object) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    self.assertNotIn(key, {"score", "selected_score", "selection_margin", "reward",
                                           "usage", "elapsed_seconds", "started_at_utc"})
                    assert_unmeasured(child)
            elif isinstance(value, list):
                for child in value:
                    assert_unmeasured(child)

        for sequence, (payload, run) in enumerate(zip(self.payloads, self.reader["runs"]), 1):
            self.assertEqual(payload["fixture"]["kind"], "handwritten")
            self.assertEqual(payload["fixture"]["family"], "umbrella-handwriting-v1")
            self.assertEqual(payload["fixture"]["sequence"], sequence)
            self.assertIn("Assistant-authored", payload["fixture"]["authoring"])
            assert_unmeasured(payload)
            self.assertIsNone(run["started_at"])
            for candidate in run["stages"][0]["candidates"]:
                self.assertEqual(candidate["provenance"], "handwritten fixture")
                self.assertEqual(candidate["provider"], "handwritten-fixture")
                self.assertEqual(candidate["model"], "fixture")
                self.assertIsNone(candidate["score"])

    def test_html_preserves_full_prose_and_handwritten_label(self) -> None:
        rendered = render_story_reader(self.reader)
        embedded = rendered.split('id="reader-data">', 1)[1].split("</script>", 1)[0]
        self.assertEqual(json.loads(embedded), self.reader)
        self.assertIn("手書き fixture / 比較用に書き起こした本文・実測なし", rendered)
        self.assertNotIn(str(ROOT), rendered)

    def test_export_leaves_fixture_families_unchanged(self) -> None:
        protected = self.paths + [ROOT / f"examples/frontiers/replay_run_{letter}.json" for letter in "ab"]
        before = {path: path.read_bytes() for path in protected}
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            output = Path(directory) / "reader.html"
            self.assertEqual(main([*(str(path) for path in self.paths), "--output-html", str(output)]), 0)
            self.assertEqual(output.read_text(encoding="utf-8"), render_story_reader(self.reader))
        for path, saved in before.items():
            self.assertEqual(path.read_bytes(), saved)

    def test_revival_does_not_fill_missing_text_from_previous_record(self) -> None:
        current = self.payloads[1]
        del current["rpm_trace"]["decision_landscape"][0]["candidates"][1]["output"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "without-prose.json"
            path.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
            result = build_story_reader([self.paths[0], path])
        revived = result["runs"][1]["stages"][0]["candidates"][1]
        self.assertEqual(revived["revived_from"], "handwritten-revival-a")
        self.assertEqual(revived["output"], "")
        self.assertEqual(revived["text_source"], "")


if __name__ == "__main__":
    unittest.main()
