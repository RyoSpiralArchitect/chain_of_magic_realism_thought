from __future__ import annotations

import argparse
import contextlib
import io
import json
import queue
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "experiments")]

import frontier_study
from furnace_runtime import QueuedProvider, execute_tasks
from magic_realism_thought.providers import DryRunProvider
from magic_realism_thought.types import ChatRequest, ProviderError


class FakeEngine:
    def __init__(self, *args):
        self.identity = {"sha256": "fake"}
        self.load_seconds = 0
        self.batch_receipts = []

    def generate(self, requests):
        self.batch_receipts.append({"seeds": [seed for _, seed in requests]})
        return [DryRunProvider("local").generate(request) for request, _ in requests]


class FrontierStudyTest(unittest.TestCase):
    def test_request_seeds_pair_by_call_ordinal_and_deliver_batch_errors(self):
        engine = FakeEngine()
        def worker(task, inbox):
            provider = QueuedProvider(inbox, 7)
            return [provider.generate(ChatRequest("fake", "", "Seed: test", 0.8, 10)).text for _ in range(2)]
        results = execute_tasks(engine, ["off", "on"], worker, 2)
        self.assertEqual(results[0], results[1])
        seeds = [seed for batch in engine.batch_receipts for seed in batch["seeds"]]
        self.assertEqual(len(set(seeds)), 2)
        self.assertTrue(all(seeds.count(seed) == 2 for seed in set(seeds)))

        class FailingEngine(FakeEngine):
            def generate(self, requests):
                return [ProviderError("incomplete") for _ in requests]
        def failing(task, inbox):
            try:
                QueuedProvider(inbox, 1).generate(ChatRequest("fake", "", "", 0.8, 10))
            except ProviderError:
                return "retained_failure"
        self.assertEqual(execute_tasks(FailingEngine(), [1, 2], failing, 2), ["retained_failure"] * 2)

    def test_calibration_eval_resume_and_source_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pack = json.loads((ROOT / "experiments/frontier_prompts.json").read_text())
            pack["prompts"] = pack["prompts"][:1]
            prompt_path = root / "prompts.json"
            frontier_study.save(prompt_path, pack)
            args = argparse.Namespace(prompts=prompt_path, model_id="fake", model_dir=root,
                replicates=1, concurrency=2, max_tokens=512, harmony_adapter=None,
                canary_only=False, output=root / "study")
            with patch.object(frontier_study, "TrtEngine", FakeEngine), patch("importlib.metadata.version", return_value="fake"):
                with contextlib.redirect_stdout(io.StringIO()):
                    frontier_study.run_generation(args)
                    saved = {path.name: path.read_bytes() for path in (args.output / "runs").glob("*.json")}
                    frontier_study.run_generation(args)
            self.assertEqual(len(saved), 3)
            self.assertEqual(saved, {path.name: path.read_bytes() for path in (args.output / "runs").glob("*.json")})
            self.assertEqual(len(list((args.output / "sessions").glob("*/canary.json"))), 2)
            profile = json.loads((args.output / "profiles/p01.json").read_text())
            self.assertEqual(profile["sources"][0]["sha256"], frontier_study.digest(args.output / "runs/p01-calibration-r00.json"))
            pairs = list(frontier_study.complete_pairs(args.output))
            self.assertEqual(len(pairs), 1)
            self.assertEqual(pairs[0][-1][0]["study"]["sampling_seed"], pairs[0][-1][1]["study"]["sampling_seed"])
            self.assertEqual(json.loads((args.output / "status.json").read_text())["completed"], 2)

    def test_frozen_configuration_and_prompt_cluster_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frozen.json"
            first = frontier_study.frozen(path, {"n": 4})
            self.assertEqual(first, frontier_study.frozen(path, {"n": 4}))
            with self.assertRaisesRegex(ValueError, "configuration changed"):
                frontier_study.frozen(path, {"n": 5})
        summary = frontier_study.cluster_interval({"p1": [1, 1, 1, 1], "p2": [-1, -1, -1, -1]}, iterations=100)
        self.assertEqual(summary["prompt_clusters"], 2)
        self.assertEqual(summary["mean"], 0)
        self.assertIsNone(frontier_study.cluster_interval({})["mean"])


if __name__ == "__main__":
    unittest.main()
