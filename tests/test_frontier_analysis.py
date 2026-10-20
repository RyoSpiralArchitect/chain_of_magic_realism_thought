from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "experiments")]

from analyze_frontier_study import verify_judge_source, verify_manifest
from frontier_study import canonical, save
from furnace_runtime import digest


class FrontierEvidenceIntegrityTest(unittest.TestCase):
    def test_evidence_mutation_is_rejected_before_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save(root / "run.json", {"status": "complete"})
            files = {"run.json": digest(root / "run.json")}
            save(root / "manifest.json", {"files": files, "sha256": canonical(files)})
            self.assertEqual(verify_manifest(root), digest(root / "manifest.json"))
            save(root / "run.json", {"status": "changed"})
            with self.assertRaisesRegex(ValueError, "artifact integrity"):
                verify_manifest(root)

    def test_manifest_cannot_substitute_a_file_outside_the_evidence_root(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "study"
            save(parent / "unrelated.json", {"status": "not study evidence"})
            root.mkdir()
            files = {"../unrelated.json": digest(parent / "unrelated.json")}
            save(root / "manifest.json", {"files": files, "sha256": canonical(files)})
            with self.assertRaisesRegex(ValueError, "inventory|artifact integrity"):
                verify_manifest(root)

    def test_unlisted_evidence_cannot_enter_an_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save(root / "manifest.json", {"files": {}, "sha256": canonical({})})
            save(root / "extra.json", {"status": "not manifested"})
            with self.assertRaisesRegex(ValueError, "inventory mismatch"):
                verify_manifest(root)

    def test_judge_must_reference_the_exact_source_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save(root / "judge/frozen.json", {"studies": {"/remote/model-study": "expected"}})
            verify_judge_source(root / "judge", root / "model-study", "expected")
            with self.assertRaisesRegex(ValueError, "source manifest mismatch"):
                verify_judge_source(root / "judge", root / "model-study", "different")
            with self.assertRaisesRegex(ValueError, "source manifest mismatch"):
                verify_judge_source(root / "judge", root / "other-study", "expected")


if __name__ == "__main__":
    unittest.main()
