import csv
import hashlib
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from llm_eval.config import project_root
from llm_eval.prompts import PromptBundle
from llm_eval.report import build_report
from llm_eval.report import SCORE_FIELDS


class ReportTests(unittest.TestCase):
    def make_run(self, root):
        design = json.loads((root / "configs/evaluation-v1.json").read_text(encoding="utf-8"))
        vehicle = design["vehicle_data"][0]
        candidate = {
            "model": vehicle["model"], "trim": vehicle["trim"], "year": vehicle["year"],
            "price_wan": vehicle["price_wan"], "meets_constraints": ["budget"],
            "why_fit": "固定参数符合场景。", "risks": [], "evidence_ids": [vehicle["source_id"]],
        }
        comparison = dict(vehicle)
        outputs = [
            {"candidate_cars": [candidate], "parameter_comparison": []},
            {"candidate_cars": [candidate], "parameter_comparison": []},
            {"candidate_cars": [candidate], "parameter_comparison": [comparison]},
            {
                "candidate_cars": [candidate], "parameter_comparison": [],
                "final_recommendation": {
                    "model": vehicle["model"], "trim": vehicle["trim"], "year": vehicle["year"],
                    "reason": "满足已给硬约束。", "tradeoffs": ["仅使用教学模拟数据"],
                },
            },
        ]
        turns = [
            {
                "turn": number,
                "model_key": "zhipu_glm_47_flash",
                "total_usage": {"total_tokens": 20, "reported": True},
                "parsed_output": output,
                "comparison_audit": {"passed": number != 3 or comparison["price_wan"] == vehicle["price_wan"]},
            }
            for number, output in enumerate(outputs, start=1)
        ]
        scoring_hash = hashlib.sha256(
            (root / "docs/evaluation-protocol-v1.md").read_text(encoding="utf-8-sig").encode("utf-8")
        ).hexdigest()
        manifest_hash = hashlib.sha256(
            (root / "configs/evaluation-v1.json").read_text(encoding="utf-8-sig").encode("utf-8")
        ).hexdigest()
        return {
            "run_id": "zhipu_glm_47_flash-city-1", "batch_kind": "evaluation_candidate",
            "model_key": "zhipu_glm_47_flash", "requested_model": "glm-4.7-flash",
            "scenario_id": "city", "repetition": 1, "output_contract_completed": True, "elapsed_ms": 1000,
            "manifest_sha256": manifest_hash, "prompt_sha256": PromptBundle.from_directory().fingerprint,
            "scoring_sha256": scoring_hash, "turns": turns,
        }

    def test_exports_three_outputs_and_summary_from_matching_candidate_runs(self):
        root = project_root()
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            runs = temp_path / "runs"
            output = temp_path / "out"
            runs.mkdir()
            (runs / "run.json").write_text(json.dumps(self.make_run(root), ensure_ascii=False), encoding="utf-8")

            report = build_report(root, runs, output)

            self.assertEqual("partial_matrix", report["status"])
            with (output / "candidate-extraction.csv").open(encoding="utf-8-sig", newline="") as stream:
                candidate_rows = list(csv.DictReader(stream))
            self.assertEqual(2, len(candidate_rows))
            self.assertEqual("SIM-A", candidate_rows[0]["source_id"])
            with (output / "parameter-comparison.csv").open(encoding="utf-8-sig", newline="") as stream:
                comparison_rows = list(csv.DictReader(stream))
            self.assertEqual("True", comparison_rows[0]["facts_match"])
            with (output / "final-recommendations.csv").open(encoding="utf-8-sig", newline="") as stream:
                recommendation_rows = list(csv.DictReader(stream))
            self.assertEqual("SIM-A", recommendation_rows[0]["source_id"])
            with (output / "run-summary.csv").open(encoding="utf-8-sig", newline="") as stream:
                run_row = next(csv.DictReader(stream))
            self.assertEqual("80", run_row["total_tokens"])
            ET.parse(output / "model-comparison.svg")
            ET.parse(output / "score-comparison.svg")
            with (output / "score-template.csv").open(encoding="utf-8-sig", newline="") as stream:
                self.assertEqual(1, len(list(csv.DictReader(stream))))

    def test_aggregates_only_complete_in_range_human_scores(self):
        root = project_root()
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            runs = temp_path / "runs"
            output = temp_path / "out"
            runs.mkdir()
            record = self.make_run(root)
            (runs / "run.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            build_report(root, runs, output)
            scores = output / "score-template.csv"
            with scores.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=SCORE_FIELDS)
                writer.writeheader()
                writer.writerow({
                    "run_id": record["run_id"], "constraint_adherence_40": 40,
                    "multi_turn_consistency_25": 25, "instruction_following_15": 15,
                    "factuality_20": 20, "reviewer": "reviewer-1", "notes": "manual review",
                })

            report = build_report(root, runs, output, scores)

            self.assertEqual(1, report["scored_record_count"])
            with (output / "model-summary.csv").open(encoding="utf-8-sig", newline="") as stream:
                model_summary = list(csv.DictReader(stream))
            city = next(row for row in model_summary if row["model_key"] == "zhipu_glm_47_flash" and row["scenario_id"] == "city")
            self.assertEqual("100", city["mean_total_score"])
            self.assertIn("100.0", (output / "score-comparison.svg").read_text(encoding="utf-8"))
            with scores.open(encoding="utf-8-sig", newline="") as stream:
                retained = next(csv.DictReader(stream))
            self.assertEqual("40", retained["constraint_adherence_40"])

    def test_rejects_merging_multiple_compatible_batch_directories(self):
        root = project_root()
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            runs = temp_path / "runs"
            runs.mkdir()
            for batch_name in ("batch-a", "batch-b"):
                batch = runs / batch_name
                batch.mkdir()
                (batch / "run.json").write_text(json.dumps(self.make_run(root)), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Multiple compatible evaluation batches"):
                build_report(root, runs, temp_path / "out")

    def test_excludes_pilot_and_incompatible_records(self):
        root = project_root()
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            runs = temp_path / "runs"
            output = temp_path / "out"
            runs.mkdir()
            record = self.make_run(root)
            record["batch_kind"] = "pilot"
            (runs / "pilot.json").write_text(json.dumps(record), encoding="utf-8")

            report = build_report(root, runs, output)

            self.assertEqual("no_compatible_evaluation_runs", report["status"])
            self.assertEqual(1, len(report["excluded_records"]))
            svg = (output / "model-comparison.svg").read_text(encoding="utf-8")
            self.assertIn('width="760" height="180"', svg)
            self.assertNotIn('fill="#2563eb"', svg)


if __name__ == "__main__":
    unittest.main()
