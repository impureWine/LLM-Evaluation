import json
import tempfile
import unittest
from pathlib import Path

from llm_eval.config import load_model_registry, registry_as_public_dict
from llm_eval.errors import ConfigurationError


class ModelRegistryTests(unittest.TestCase):
    def test_default_registry_has_two_distinct_models(self):
        registry = load_model_registry()
        specs = registry.ordered()
        self.assertGreaterEqual(len(specs), 2)
        self.assertEqual(len({spec.model_id for spec in specs}), len(specs))
        self.assertEqual(
            {"deepseek-flash", "deepseek-v4-pro"},
            {spec.model_id for spec in specs},
        )

    def test_shared_generation_parameters_are_applied(self):
        registry = load_model_registry()
        for spec in registry.ordered():
            self.assertEqual(0.0, spec.parameters["temperature"])
            self.assertEqual(1.0, spec.parameters["top_p"])
            self.assertEqual(4096, spec.parameters["max_tokens"])
            self.assertEqual(
                {"type": "json_object"},
                spec.parameters["response_format"],
            )

    def test_public_registry_contains_no_credential(self):
        public = json.dumps(
            registry_as_public_dict(load_model_registry()),
            ensure_ascii=False,
        )
        self.assertNotIn("sk-", public)

    def test_registry_rejects_embedded_like_secret(self):
        source = Path("configs/models.json").read_text(encoding="utf-8")
        test_value = '"leak": "' + 'sk-' + 'test-placeholder"'
        source = source.replace('"schema_version": 1', '"schema_version": 1, ' + test_value)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "models.json"
            path.write_text(source, encoding="utf-8")
            with self.assertRaises(ConfigurationError):
                load_model_registry(path)


if __name__ == "__main__":
    unittest.main()

