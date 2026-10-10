from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from magic_realism_thought.cli import main
from magic_realism_thought.reward_audit import evaluate_reward_audit_cases


class CliTraceContractTest(unittest.TestCase):
    def test_dry_run_emits_decision_ontology_and_reward_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_json = Path(tmp) / "nested" / "run.json"
            stdout = io.StringIO()
            stderr = io.StringIO()
            args = [
                "--dry-run",
                "--provider",
                "openai",
                "--prompt",
                "朝、会社に行く。",
                "--stage-preset",
                "seed-independent-magic",
                "--anchor-profile",
                "auto",
                "--no-aggregate",
                "--no-recursive-closure",
                "--candidates",
                "2",
                "--output-json",
                str(output_json),
            ]
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                status = main(args)

            self.assertEqual(status, 0, stderr.getvalue())
            payload = json.loads(output_json.read_text(encoding="utf-8"))
            trace = payload["rpm_trace"]

            self.assertIn("decision_landscape", trace)
            self.assertGreaterEqual(len(trace["decision_landscape"]), 1)
            first_decision = trace["decision_landscape"][0]
            self.assertEqual(first_decision["contract_version"], "decision-landscape-2.0")
            self.assertIn("accepted_candidate_id", first_decision)
            self.assertIn("candidates", first_decision)
            self.assertIn("frontier_items", first_decision)
            self.assertTrue(any(item["kind"] == "accepted_candidate" for item in first_decision["frontier_items"]))
            self.assertIn("frontier_reason", first_decision)

            self.assertIn("ontology_ledger", trace)
            ledger = trace["ontology_ledger"]
            self.assertGreaterEqual(len(ledger["entries"]), 1)
            self.assertTrue(any(entry["kind"] == "axis" for entry in ledger["entries"]))

            audit = payload["reward_surface_audit"]
            self.assertIn(audit["risk_level"], {"low", "medium", "high"})
            self.assertIn("recommendations", audit)

    def test_reward_audit_eval_fixture(self) -> None:
        results = evaluate_reward_audit_cases(ROOT / "examples" / "evals" / "reward_audit_cases.json")

        self.assertTrue(results)
        self.assertTrue(all(result["passed"] for result in results), results)


if __name__ == "__main__":
    unittest.main()
