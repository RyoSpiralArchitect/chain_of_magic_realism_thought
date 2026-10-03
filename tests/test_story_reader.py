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


class StoryReaderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dry_run = ROOT / "examples/runs/dry_run.json"
        self.replay_paths = [ROOT / f"examples/frontiers/replay_run_{letter}.json" for letter in "ab"]

    def test_preserves_actual_selected_and_discarded_text(self) -> None:
        original = json.loads(self.dry_run.read_text())
        result = build_story_reader([self.dry_run])
        stage = result["runs"][0]["stages"][0]
        selected = next(candidate for candidate in stage["candidates"] if candidate["selected"])
        discarded = next(candidate for candidate in stage["candidates"] if candidate["discarded"])
        self.assertEqual(selected["output"], original["steps"][0]["accepted"]["output"])
        self.assertEqual(discarded["output"], original["steps"][0]["rejected"][0]["output"])
        self.assertEqual(selected["provenance"], "dry-run")
        self.assertEqual(selected["provider"], "openai")
        self.assertEqual(result["runs"][0]["sha256"], hashlib.sha256(self.dry_run.read_bytes()).hexdigest())
        self.assertEqual(len(result["runs"][0]["stages"]), 7)

    def test_uses_existing_replay_for_revival_and_tensions(self) -> None:
        reader = build_story_reader(self.replay_paths)
        existing = build_frontier_replay_report(self.replay_paths)
        self.assertEqual(reader["replay"]["transitions"][0]["events"], existing["transitions"][0]["events"])
        self.assertEqual(reader["replay"]["transitions"][0]["ontology_growth_gate"], existing["transitions"][0]["ontology_growth_gate"])
        candidate = reader["runs"][1]["stages"][0]["candidates"][1]
        self.assertEqual(candidate["id"], "s01-c02")
        self.assertTrue(candidate["selected"])
        self.assertFalse(candidate["discarded"])
        self.assertEqual(candidate["revived_from"], "frontier-replay-a")
        self.assertEqual(candidate["output"], "")
        self.assertEqual(candidate["text_source"], "")
        self.assertEqual(candidate["provenance"], "fixture")

    def test_preserves_rejected_repair_status(self) -> None:
        candidates = build_story_reader([self.dry_run])["runs"][0]["stages"][-1]["candidates"]
        repaired = next(candidate for candidate in candidates if candidate["status"] == "rejected_repair")
        self.assertTrue(repaired["discarded"])
        self.assertFalse(repaired["selected"])
        self.assertTrue(repaired["repaired_from"])

    def write_run(self, directory: str, payload: dict, name: str = "run.json") -> Path:
        path = Path(directory) / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_join_by_id_not_position(self) -> None:
        payload = json.loads(self.dry_run.read_text())
        payload["rpm_trace"]["decision_landscape"][0]["candidates"].reverse()
        with tempfile.TemporaryDirectory() as directory:
            result = build_story_reader([self.write_run(directory, payload)])
        selected = result["runs"][0]["stages"][0]["candidates"][0]
        self.assertTrue(selected["selected"])
        self.assertEqual(selected["output"], payload["steps"][0]["accepted"]["output"])

    def test_does_not_borrow_text_from_another_stage(self) -> None:
        payload = json.loads(self.dry_run.read_text())
        payload["rpm_trace"]["decision_landscape"][0]["candidates"][0]["candidate_id"] = payload["steps"][1]["accepted"]["candidate_id"]
        with tempfile.TemporaryDirectory() as directory:
            result = build_story_reader([self.write_run(directory, payload)])
        self.assertEqual(result["runs"][0]["stages"][0]["candidates"][0]["output"], "")

    def test_supports_legacy_saved_steps(self) -> None:
        result = build_story_reader([ROOT / "examples/runs/openai_single_run.json"])
        candidates = [candidate for stage in result["runs"][0]["stages"] for candidate in stage["candidates"]]
        self.assertTrue(any(candidate["selected"] and candidate["output"] for candidate in candidates))
        self.assertTrue(any(candidate["discarded"] and candidate["output"] for candidate in candidates))
        self.assertEqual(candidates[0]["provenance"], "saved / unverified")

    def test_rejects_mismatched_or_missing_seeds(self) -> None:
        with self.assertRaisesRegex(ValueError, "same non-empty seed"):
            build_story_reader([self.dry_run, ROOT / "examples/runs/openai_seed_independent_run.json"])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "same non-empty seed"):
                build_story_reader([self.write_run(directory, {"rpm_trace": {}})])

    def test_rejects_duplicate_run_ids(self) -> None:
        with self.assertRaisesRegex(ValueError, "run IDs must be unique"):
            build_story_reader([self.dry_run, self.dry_run])

    def test_empty_trace_is_readable_and_invalid_trace_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_run(directory, {"seed": "雨", "rpm_trace": {}})
            self.assertEqual(build_story_reader([path])["runs"][0]["stages"], [])
            path = self.write_run(directory, {"seed": "雨", "rpm_trace": []})
            with self.assertRaisesRegex(ValueError, "must be an object"):
                build_story_reader([path])

    def test_script_escaping_and_data_minimization(self) -> None:
        payload = json.loads(self.dry_run.read_text())
        dangerous = '</script><img src=x onerror=alert(1)> & \u2028'
        payload["steps"][0]["accepted"]["output"] = dangerous
        payload["steps"][0]["accepted"]["prompt"] = "DO NOT EXPORT PRIVATE PROMPT"
        with tempfile.TemporaryDirectory() as directory:
            result = build_story_reader([self.write_run(directory, payload)])
            rendered = render_story_reader(result)
            self.assertNotIn(directory, rendered)
        self.assertNotIn(dangerous, rendered)
        self.assertNotIn("DO NOT EXPORT PRIVATE PROMPT", rendered)
        self.assertIn("\\u003c/script\\u003e", rendered)
        embedded = rendered.split('id="reader-data">', 1)[1].split("</script>", 1)[0]
        self.assertEqual(json.loads(embedded), result)
        self.assertNotIn("innerHTML", rendered)
        self.assertIn("connect-src 'none'", rendered)

    def test_export_does_not_change_inputs(self) -> None:
        before = self.dry_run.read_bytes()
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            output = Path(directory) / "nested/reader.html"
            self.assertEqual(main([str(self.dry_run), "--output-html", str(output)]), 0)
            self.assertIn("物語の分岐を読む", output.read_text())
        self.assertEqual(before, self.dry_run.read_bytes())

    def test_cli_missing_file_invalid_json_and_overwrite_guard(self) -> None:
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()):
            path = Path(directory) / "run.json"
            output = str(Path(directory) / "reader.html")
            self.assertEqual(main([str(path), "--output-html", output]), 2)
            path.write_text("[not json]")
            self.assertEqual(main([str(path), "--output-html", output]), 2)
            self.assertEqual(main([str(path), "--output-html", str(path)]), 2)
            self.assertEqual(path.read_text(), "[not json]")

    def test_requires_at_least_one_run(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            build_story_reader([])


if __name__ == "__main__":
    unittest.main()
