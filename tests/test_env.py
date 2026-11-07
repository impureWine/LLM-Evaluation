import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm_eval.env import load_local_env


class LocalEnvironmentTests(unittest.TestCase):
    def test_loads_project_specific_variable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "LLM_EVAL_DEEPSEEK_API_KEY=test-new-key\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                load_local_env(path)
                self.assertEqual(
                    "test-new-key",
                    os.environ["LLM_EVAL_DEEPSEEK_API_KEY"],
                )

    def test_existing_process_value_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "LLM_EVAL_DEEPSEEK_API_KEY=from-file\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"LLM_EVAL_DEEPSEEK_API_KEY": "from-process"},
                clear=True,
            ):
                load_local_env(path)
                self.assertEqual(
                    "from-process",
                    os.environ["LLM_EVAL_DEEPSEEK_API_KEY"],
                )


if __name__ == "__main__":
    unittest.main()
