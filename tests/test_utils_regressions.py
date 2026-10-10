import os
import unittest
from unittest.mock import patch

from magic_realism_thought.utils import extract_json_object, first_env


class UtilsRegressionTest(unittest.TestCase):
    def test_extract_json_response_shapes(self):
        for response in ('{"score": 0.8}', '```json\n{"score": 0.8}\n```', 'Result: {"score": 0.8} end'):
            with self.subTest(response=response):
                self.assertEqual(extract_json_object(response), {"score": 0.8})

    def test_first_env_uses_environment_and_handles_missing_values(self):
        with patch.dict(os.environ, {"MAGIC_TEST_KEY": "test-only"}, clear=True):
            self.assertEqual(first_env(["MISSING", "MAGIC_TEST_KEY"]), "test-only")
            self.assertIsNone(first_env(["MISSING"]))

    def test_missing_json_is_rejected(self):
        with self.assertRaises(ValueError):
            extract_json_object("no object here")
