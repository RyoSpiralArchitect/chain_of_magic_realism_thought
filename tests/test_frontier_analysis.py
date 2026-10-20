from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "experiments")]

from analyze_frontier_study import verify_manifest
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
            files = {"../unrelated.json": digest(parent / "unrelated.json")}
            save(root / "manifest.json", {"files": files, "sha256": canonical(files)})
            with self.assertRaisesRegex(ValueError, "artifact integrity"):
                verify_manifest(root)


if __name__ == "__main__":
    unittest.main()
