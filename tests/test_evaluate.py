import tempfile
import unittest
from pathlib import Path

from llm_eval.evaluate import extract_parameter_comparison, write_run_record


class EvaluationRecordTests(unittest.TestCase):
    def setUp(self):
        self.vehicles = [
            {"source_id": "SIM-A", "model": "教学车型 A", "trim": "通勤版", "year": 2026,
             "price_wan": 14.8, "energy": "纯电", "seats": 5, "adas": "L2"},
            {"source_id": "SIM-B", "model": "教学车型 B", "trim": "长途版", "year": 2026,
             "price_wan": 18.6, "energy": "插电混动", "seats": 5, "adas": "L2"},
        ]

    def test_parameter_table_uses_only_matching_frozen_source_rows(self):
        payload = {"candidate_cars": [
            {"model": "教学车型 A", "trim": "通勤版", "year": 2026, "evidence_ids": ["SIM-A"]},
            {"model": "编造车型", "trim": "不存在", "year": 2025, "evidence_ids": ["SIM-Z"]},
        ]}
        table = extract_parameter_comparison(payload, self.vehicles)
        self.assertEqual(table["source"], "frozen_vehicle_data")
        self.assertEqual(table["rows"][0]["energy"], "纯电")
        self.assertEqual(table["unmatched_candidates"][0]["model"], "编造车型")

    def test_run_record_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.json"
            write_run_record(path, {"run_id": "one"})
            with self.assertRaises(FileExistsError):
                write_run_record(path, {"run_id": "replacement"})

    def test_malformed_candidates_are_retained_as_unmatched_not_crashing(self):
        table = extract_parameter_comparison(
            {"candidate_cars": [None, {"model": "X", "evidence_ids": None}]}, self.vehicles
        )
        self.assertEqual(table["rows"], [])
        self.assertEqual(len(table["unmatched_candidates"]), 2)


if __name__ == "__main__":
    unittest.main()
