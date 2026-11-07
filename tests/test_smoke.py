import json
import tempfile
import unittest
from pathlib import Path

from llm_eval.config import load_model_registry
from llm_eval.prompts import PromptBundle


class SmokeAssetTests(unittest.TestCase):
    def test_smoke_case_renders_for_all_registered_models(self):
        case_path = Path("examples/smoke_case.json")
        case = json.loads(case_path.read_text(encoding="utf-8"))
        bundle = PromptBundle.from_directory()
        messages = bundle.initial_messages(case["scenario"], case["vehicle_data"])
        self.assertEqual(2, len(messages))
        self.assertIn("smoke-city-commute-01", messages[1].content)
        self.assertIn("smoke-car-001", messages[1].content)

        registry = load_model_registry()
        self.assertEqual(2, len(registry.ordered()))


if __name__ == "__main__":
    unittest.main()

