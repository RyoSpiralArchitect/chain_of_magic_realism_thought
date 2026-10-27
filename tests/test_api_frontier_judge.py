from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "experiments")]

import api_frontier_judge as api
import frontier_study
from analyze_frontier_study import verify_manifest
from compare_frontier_judges import metered_cost, normalize


def response(status="completed", content=None):
    data = {"id": "response-test", "model": "gpt-6-astra", "status": status,
            "usage": {"input_tokens": 12, "output_tokens": 30, "total_tokens": 42},
            "output": [{"type": "reasoning", "summary": "PRIVATE-REASONING-MUST-NOT-BE-SAVED"},
                       {"type": "message", "role": "assistant", "status": "completed",
                        "content": content if content is not None else [{"type": "output_text", "text": json.dumps(
                            {"winner": "A", "continuity": "A", "restraint": "tie", "freshness": "B", "reason": "Concrete observable detail."})}]}]}
    return SimpleNamespace(model_dump=lambda **kwargs: data, _request_id="request-test")


class FakeClient:
    def __init__(self):
        self.calls = []
        self.responses = SimpleNamespace(create=self.create)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return response()

    def close(self):
        pass


class ApiFrontierJudgeTest(unittest.TestCase):
    def test_order_normalization_and_metered_cost_do_not_double_count_reasoning(self):
        self.assertEqual(normalize("A", "off"), "off")
        self.assertEqual(normalize("B", "on"), "off")
        self.assertEqual(normalize("tie", "on"), "tie")
        usage = {"input_tokens": 100, "output_tokens": 20,
                 "input_tokens_details": {"cached_tokens": 30, "cache_write_tokens": 50,
                    "cache_write_tokens_details": {"ttl_30m_tokens": 50, "ttl_12h_tokens": 0}},
                 "output_tokens_details": {"reasoning_tokens": 10}}
        measured = metered_cost([{"usage": usage}])
        self.assertAlmostEqual(measured["complete_estimated_usd"], 0.001855)
        self.assertEqual(measured["token_totals"]["output_tokens"], 20)
        self.assertEqual(measured["token_totals"]["reasoning_output_tokens"], 10)
        self.assertIsNone(metered_cost([{}])["complete_estimated_usd"])
        usage["input_tokens_details"]["cache_write_tokens"] = 60
        self.assertIsNone(metered_cost([{"usage": usage}])["complete_estimated_usd"])

    def test_admits_only_completed_final_and_never_saves_reasoning(self):
        record = api.response_record(response(), "quoted passages")
        self.assertEqual(record["status"], "complete")
        self.assertNotIn("PRIVATE-REASONING", json.dumps(record))
        self.assertEqual(record["usage"]["prompt_sha256"], api.sha_text("quoted passages"))
        incomplete = api.response_record(response(status="incomplete"), "prompt")
        self.assertEqual(incomplete["status"], "unknown")
        self.assertNotIn("response", incomplete)
        refused = api.response_record(response(content=[{"type": "refusal", "refusal": "not an answer"}]), "prompt")
        self.assertEqual(refused["error_type"], "refused_or_nontext_final")
        invalid = api.response_record(response(content=[{"type": "output_text", "text": '{"winner":"A"}'}]), "prompt")
        self.assertEqual(invalid["error_type"], "invalid_judgment_json")

    def task(self):
        prompt = frontier_study.judge_prompt("seed", "left", "right")
        return {"trial_id": "study-p01-r00-o0", "generator": "study", "prompt_id": "p01", "replicate": 0,
                "a_phase": "off", "input_sha256": ["left-sha", "right-sha"], "prompt": prompt,
                "budget": api.cost_ceiling(prompt, 2048)}

    def config(self):
        return {"judge_model": "gpt-6-astra", "max_tokens": 2048}

    def test_issued_before_call_resume_reuses_result_and_no_unsupported_sampling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task, config, client = self.task(), self.config(), FakeClient()
            first = api.execute_one(client, task, root, config, "config-sha")
            self.assertTrue((root / "issued" / (task["trial_id"] + ".json")).exists())
            self.assertEqual(api.execute_one(client, task, root, config, "config-sha"), first)
            self.assertEqual(len(client.calls), 1)
            payload = client.calls[0]
            self.assertFalse(payload["store"])
            self.assertNotIn("temperature", payload)
            self.assertNotIn("top_p", payload)
            self.assertEqual(payload["instructions"], frontier_study.JUDGE_SYSTEM)
            self.assertEqual(first["preferred_phase"], "off")
            with self.assertRaisesRegex(ValueError, "identity mismatch"):
                api.execute_one(client, task, root, config, "other-config")

    def test_ambiguous_remote_outcome_is_never_resent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task, client = self.task(), FakeClient()
            frontier_study.save(root / "issued" / (task["trial_id"] + ".json"), {"status": "issued"})
            with self.assertRaisesRegex(ValueError, "refusing automatic resend"):
                api.execute_one(client, task, root, self.config(), "config-sha")
            self.assertEqual(client.calls, [])

    def test_transport_errors_do_not_leak_credentials_and_are_not_retried(self):
        class FailingClient(FakeClient):
            def create(self, **kwargs):
                self.calls.append(kwargs)
                raise RuntimeError("SECRET-KEY and private request body")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = FailingClient()
            record = api.execute_one(client, self.task(), root, self.config(), "config-sha")
            self.assertEqual(record["status"], "unknown")
            self.assertNotIn("SECRET-KEY", json.dumps(record))
            self.assertEqual(len(client.calls), 1)
            api.execute_one(client, self.task(), root, self.config(), "config-sha")
            self.assertEqual(len(client.calls), 1)

    def test_budget_and_manifest_checked_before_client_construction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "study"
            frontier_study.save(study / "frozen.json", {"model_id": "generator", "prompts": [{"id": "p01", "seed": "seed"}], "replicates": 1})
            for phase in ("off", "on"):
                frontier_study.save(study / "runs" / f"p01-{phase}-r00.json", {"final": phase})
            frontier_study.save_manifest(study)
            args = argparse.Namespace(studies=[study], output=root / "judge", model="gpt-6-astra", max_tokens=2048,
                budget_usd=0.001, concurrency=1, timeout=10, plan_only=False, limit=1)
            with self.assertRaisesRegex(ValueError, "exceeds budget"):
                api.prepare(args)
            self.assertFalse(args.output.exists())
            args.budget_usd = 1
            client = FakeClient()
            with contextlib.redirect_stdout(io.StringIO()):
                api.run(args, client_factory=lambda: client)
            self.assertEqual(len(client.calls), 1)
            verify_manifest(args.output)
            before = {str(p.relative_to(args.output)): p.read_bytes() for p in args.output.rglob("*.json")}
            args.max_tokens = 1024
            with self.assertRaisesRegex(ValueError, "configuration changed"):
                api.run(args, client_factory=lambda: self.fail("must not construct client"))
            self.assertEqual(before, {str(p.relative_to(args.output)): p.read_bytes() for p in args.output.rglob("*.json")})
            args.max_tokens = 2048
            with contextlib.redirect_stdout(io.StringIO()):
                api.run(args, client_factory=lambda: client)
            self.assertEqual(len(client.calls), 2)
            self.assertEqual(json.loads((args.output / "status.json").read_text())["phase"], "complete")
            frontier_study.save(study / "runs/p01-off-r00.json", {"final": "tampered"})
            with self.assertRaisesRegex(ValueError, "artifact integrity"):
                api.prepare(args)


if __name__ == "__main__":
    unittest.main()
