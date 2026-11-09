"""Data contract regressions: budget edges, supersession, provenance and leakage."""

import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from llm_eval.dataset import constraint_history, derive_references, fits, make_lock, validate_inputs


ROOT = Path(__file__).resolve().parents[1]


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.design = json.loads((ROOT / "configs/evaluation-v1.json").read_text(encoding="utf-8-sig"))
        self.rules = json.loads((ROOT / "configs/scenario-rules-v1.json").read_text(encoding="utf-8-sig"))

    def test_budget_is_inclusive_without_rounding_over_budget(self):
        limit = {"field": "price_wan", "operator": "lte", "value": 19}
        self.assertTrue(fits({"price_wan": 19}, limit))
        self.assertFalse(fits({"price_wan": 19.0001}, limit))

    def test_energy_does_not_equate_phev_and_bev(self):
        self.assertFalse(fits({"energy": "插电混动"}, {"field": "energy", "operator": "eq", "value": "纯电"}))

    def test_budget_replaced_from_turn_two_only(self):
        rule = next(s for s in self.rules["scenarios"] if s["id"] == "change")
        self.assertEqual([c["value"] for c in constraint_history(rule, 1) if c["id"] == "budget"], [24])
        for turn in (2, 3, 4):
            history = constraint_history(rule, turn)
            self.assertEqual([(c["value"], c["status"]) for c in history if c["id"] == "budget"],
                             [(24, "superseded"), (19, "active")])
            self.assertEqual({c["field"] for c in history if c["status"] == "active"},
                             {"price_wan", "seats", "energy"})

    def test_added_energy_retains_seven_seats(self):
        references = derive_references(self.design, self.rules)
        family = next(s for s in references["scenarios"] if s["scenario_id"] == "family")
        self.assertEqual(family["turns"][0]["eligible_source_ids"], ["SIM-C", "SIM-D"])
        self.assertEqual(family["turns"][1]["eligible_source_ids"], ["SIM-C"])
        exclusions = {v["source_id"]: v["failed_constraints"] for v in family["turns"][1]["excluded"]}
        self.assertIn("seats", exclusions["SIM-B"])
        self.assertIn("energy", exclusions["SIM-D"])

    def test_wrong_embedded_reference_is_rejected(self):
        self.design["scenarios"][2]["expected_final"] = ["SIM-C"]
        with self.assertRaisesRegex(ValueError, "Reference mismatch"):
            derive_references(self.design, self.rules)

    def test_duplicate_rule_is_rejected(self):
        self.rules["scenarios"].append(copy.deepcopy(self.rules["scenarios"][0]))
        with self.assertRaisesRegex(ValueError, "Scenario rules"):
            derive_references(self.design, self.rules)

    def test_invalid_replacement_is_rejected(self):
        rule = self.rules["scenarios"][2]
        rule["events"][0]["constraint"]["id"] = "missing-budget"
        with self.assertRaisesRegex(ValueError, "Replacement"):
            constraint_history(rule, 2)

    def test_repository_sources_scripts_and_reference_isolation(self):
        result = validate_inputs(ROOT)
        self.assertEqual(len(result["scenarios"]), 3)
        expected = json.loads((ROOT / "data/reference-answers-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(result, expected)

    def test_source_and_script_drift_are_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for folder in ("configs", "data", "prompts"):
                shutil.copytree(ROOT / folder, root / folder)
            path = root / "data/vehicle-sources-v1.json"
            original = path.read_text(encoding="utf-8")
            changed = json.loads(original)
            changed["sources"][0]["year"] = 2025
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Source identity mismatch"):
                validate_inputs(root)
            path.write_text(original, encoding="utf-8")
            path = root / "configs/scenario-rules-v1.json"
            changed = json.loads(path.read_text(encoding="utf-8"))
            changed["scenarios"][0]["turn_scripts"][2]["user_message"] = "changed"
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "script differs"):
                validate_inputs(root)

    def test_release_fingerprints_match(self):
        saved = json.loads((ROOT / "data/release-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(make_lock(ROOT), saved)


if __name__ == "__main__":
    unittest.main()
