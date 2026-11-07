import json
import tempfile
import unittest
from pathlib import Path

from llm_eval.errors import ConfigurationError
from llm_eval.prompts import PromptBundle, render_template


class PromptBundleTests(unittest.TestCase):
    def test_initial_messages_contain_shared_schema_and_data(self):
        bundle = PromptBundle.from_directory()
        messages = bundle.initial_messages(
            {"id": "scenario-1", "budget_wan": 20},
            [{"id": "car-1", "model": "Test Car", "price_wan": 18}],
        )

        self.assertEqual(["system", "user"], [message.role for message in messages])
        self.assertIn('"effective_constraints"', messages[0].content)
        self.assertIn('"scenario-1"', messages[1].content)
        self.assertIn('"car-1"', messages[1].content)
        self.assertNotIn("{{", messages[0].content + messages[1].content)

    def test_fingerprint_is_stable_for_same_files(self):
        first = PromptBundle.from_directory()
        second = PromptBundle.from_directory()
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertEqual(64, len(first.fingerprint))
        self.assertEqual("v1", first.public_fingerprint()["prompt_version"])

    def test_followup_preserves_turn_and_user_change(self):
        bundle = PromptBundle.from_directory()
        message = bundle.followup_message(
            3,
            "预算提高到 30 万元，但必须保留七座。",
            "新预算从第 3 轮起生效。",
        )
        self.assertEqual("user", message.role)
        self.assertIn("第 3 轮", message.content)
        self.assertIn("预算提高到 30 万元", message.content)
        self.assertIn("新预算从第 3 轮起生效", message.content)

    def test_template_rejects_missing_values(self):
        with self.assertRaises(ConfigurationError):
            render_template("{{REQUIRED_VALUE}}", {})

    def test_bundle_rejects_invalid_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "system_v1.md").write_text("system {{OUTPUT_SCHEMA}}", encoding="utf-8")
            (root / "initial_user_v1.md").write_text("initial", encoding="utf-8")
            (root / "followup_user_v1.md").write_text("followup", encoding="utf-8")
            (root / "output_schema_v1.json").write_text("[]", encoding="utf-8")
            with self.assertRaises(ConfigurationError):
                PromptBundle.from_directory(root)


if __name__ == "__main__":
    unittest.main()

