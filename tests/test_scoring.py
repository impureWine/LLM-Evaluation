"""Offline regressions for the semi-automatic scoring rules (no API calls)."""

import csv
import json
import shutil
from pathlib import Path
import tempfile
import unittest

from llm_eval.scoring import (
    Catalog,
    aggregate,
    count_questions,
    main,
    match_vehicle,
    read_review,
    score_run,
)


ROOT = Path(__file__).resolve().parents[1]


def load_reference():
    payload = json.loads((ROOT / "data/reference-answers-v1.json").read_text(encoding="utf-8"))
    return {scenario["scenario_id"]: scenario for scenario in payload["scenarios"]}


def load_catalog():
    design = json.loads((ROOT / "configs/evaluation-v1.json").read_text(encoding="utf-8-sig"))
    return Catalog(design["vehicle_data"])


def car(model, trim, year, price, evidence, why_fit=None):
    return {
        "model": model,
        "trim": trim,
        "year": year,
        "price_wan": price,
        "meets_constraints": [],
        "why_fit": why_fit or "价格{}万元，纯电，5座，L2辅助驾驶".format(price),
        "risks": [],
        "evidence_ids": evidence,
    }


def car_a(**overrides):
    payload = car("教学车型 A", "通勤版", 2026, 14.8, ["SIM-A"])
    payload.update(overrides)
    return payload


def car_e(**overrides):
    payload = car("教学车型 E", "智驾版", 2026, 17.5, ["SIM-E"])
    payload.update(overrides)
    return payload


def car_b(**overrides):
    payload = car(
        "教学车型 B", "长途版", 2026, 18.6, ["SIM-B"],
        why_fit="价格18.6万元，插电混动，5座，L2辅助驾驶",
    )
    payload.update(overrides)
    return payload


def car_c(**overrides):
    payload = car(
        "教学车型 C", "家庭版", 2026, 22.6, ["SIM-C"],
        why_fit="价格22.6万元，插电混动，7座，L2辅助驾驶",
    )
    payload.update(overrides)
    return payload


def constraints(*extra):
    base = [
        {"name": "预算", "value": "不超过18万元", "source_turn": 1, "status": "active"},
        {"name": "能源形式", "value": "纯电", "source_turn": 1, "status": "active"},
        {"name": "座位数", "value": "至少5座", "source_turn": 1, "status": "active"},
    ]
    return base + list(extra)


ADAS = {"name": "辅助驾驶", "value": "L2级", "source_turn": 2, "status": "active"}


def payload(candidates, declared=None, final=None, next_question=None, status="candidate_only"):
    return {
        "turn_summary": "测试输出",
        "effective_constraints": declared if declared is not None else constraints(),
        "candidate_cars": candidates,
        "final_recommendation": final,
        "next_question": next_question,
        "confidence": "medium",
        "status": status,
        "assumptions": [],
    }


def comparison_rows(*cars):
    rows = []
    catalog = load_catalog()
    for payload_car in cars:
        source_id = payload_car["evidence_ids"][0]
        vehicle = catalog.by_source[source_id]
        rows.append({
            "source_id": source_id,
            "model": vehicle["model"],
            "trim": vehicle["trim"],
            "year": vehicle["year"],
            "price_wan": vehicle["price_wan"],
            "energy": vehicle["energy"],
            "seats": vehicle["seats"],
            "adas": vehicle["adas"],
        })
    return {"source": "frozen_vehicle_data", "rows": rows, "unmatched_candidates": []}


def city_payloads():
    first = payload([car_a(), car_e()], next_question="是否更看重续航？")
    second = payload(
        [car_a(), car_e()], declared=constraints(ADAS),
        next_question="是否接受纯电？",
    )
    third = payload([car_a(), car_e()], declared=constraints(ADAS), next_question=None)
    fourth = payload(
        [car_a(), car_e()], declared=constraints(ADAS),
        final={
            "model": "教学车型 A", "trim": "通勤版", "year": 2026,
            "reason": "预算内且满足纯电与L2", "tradeoffs": ["续航短于燃油车"],
        },
        status="final",
    )
    return [first, second, third, fourth]


def build_record(payloads, scenario_id="city", comparison=None, valid=True, run_id=None,
                 model_key="zhipu_glm_47_flash"):
    turns = []
    for index, turn_payload in enumerate(payloads, start=1):
        entry = {
            "turn": index,
            "model_key": model_key,
            "valid": valid,
            "validation_issues": [],
            "correction_attempts": 0,
            "prompt_fingerprint": "test",
            "total_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "total_latency_ms": 1000,
            "final_response": {},
            "attempts": [],
            "parsed_output": turn_payload,
        }
        if index == 3 and comparison is not None:
            entry["parameter_comparison"] = comparison
        turns.append(entry)
    return {
        "run_id": run_id or "{}-{}-1".format(model_key, scenario_id),
        "scenario_id": scenario_id,
        "repetition": 1,
        "batch_kind": "evaluation_candidate",
        "turns": turns,
        "elapsed_ms": 4000,
        "completed": True,
    }


def item_of(result, dimension, turn):
    for item in result["items"]:
        if item["dimension"] == dimension and item["turn"] == turn:
            return item
    raise AssertionError("missing item {}#{}".format(dimension, turn))


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.references = load_reference()
        self.catalog = load_catalog()

    def perfect_city(self):
        return build_record(city_payloads(), comparison=comparison_rows(car_a(), car_e()))

    def test_perfect_run_scores_full_marks(self):
        result = score_run(self.perfect_city(), self.references, self.catalog)
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["pending_points"], 0)
        self.assertTrue(result["success"])
        self.assertEqual(result["subtotals"], {
            "constraint_fit": 40, "consistency": 25, "instruction": 15, "truthfulness": 20,
        })

    def test_out_of_budget_candidate_loses_constraint_point_only(self):
        payloads = city_payloads()
        payloads[0] = payload([car_a(), car_c()], next_question="是否更看重续航？")
        result = score_run(build_record(payloads, comparison=comparison_rows(car_a(), car_e())),
                           self.references, self.catalog)
        self.assertEqual(item_of(result, "constraint_fit", 1)["points"], 0)
        self.assertEqual(item_of(result, "truthfulness", 1)["points"], 5)
        self.assertEqual(result["score"], 90)

    def test_wrong_price_breaks_truthfulness_not_fit(self):
        payloads = city_payloads()
        payloads[1] = payload(
            [car_a(price_wan=99.0), car_e()], declared=constraints(ADAS),
            next_question="是否接受纯电？",
        )
        result = score_run(build_record(payloads, comparison=comparison_rows(car_a(), car_e())),
                           self.references, self.catalog)
        self.assertEqual(item_of(result, "constraint_fit", 2)["points"], 10)
        truth = item_of(result, "truthfulness", 2)
        self.assertEqual(truth["points"], 0)
        self.assertIn("price_mismatch", truth["reason"])

    def test_relaxed_energy_breaks_consistency(self):
        payloads = city_payloads()
        relaxed = constraints(
            ADAS,
            {"name": "能源形式", "value": "纯电或插电混动", "source_turn": 1, "status": "active"},
        )
        relaxed = [c for c in relaxed if not (c["name"] == "能源形式" and c["value"] == "纯电")]
        payloads[1] = payload([car_a()], declared=relaxed, next_question="是否接受纯电？")
        result = score_run(build_record(payloads, comparison=comparison_rows(car_a(), car_e())),
                           self.references, self.catalog)
        consistency = item_of(result, "consistency", 2)
        self.assertEqual(consistency["points"], 0)
        self.assertIn("retained_constraint_missing:energy", consistency["reason"])
        self.assertEqual(result["score"], 90)

    def test_two_questions_break_instruction(self):
        payloads = city_payloads()
        payloads[0] = payload([car_a(), car_e()], next_question="您更看重续航？还是更看重智驾？")
        result = score_run(build_record(payloads, comparison=comparison_rows(car_a(), car_e())),
                           self.references, self.catalog)
        self.assertEqual(count_questions(payloads[0]["next_question"]), 2)
        instruction = item_of(result, "instruction", 1)
        self.assertEqual(instruction["points"], 0)
        self.assertIn("more_than_one_question", instruction["reason"])
        self.assertEqual(result["score"], 97)

    def test_question_count_failure_is_reopenable_for_review(self):
        payloads = city_payloads()
        payloads[0] = payload([car_a(), car_e()], next_question="您更看重续航？还是更看重智驾？")
        record = build_record(payloads, comparison=comparison_rows(car_a(), car_e()))
        result = score_run(record, self.references, self.catalog)
        self.assertEqual(result["pending_points"], 0)
        override = [row for row in result["review_rows"] if row["kind"] == "override"]
        self.assertEqual(len(override), 1)
        self.assertEqual(override[0]["turn"], 1)
        self.assertEqual(override[0]["dimension"], "instruction")
        self.assertEqual(override[0]["default"], "fail")
        reviewed = score_run(record, self.references, self.catalog,
                             {(record["run_id"], 1, "instruction"): "pass"})
        self.assertEqual(reviewed["score"], 100)
        self.assertTrue(item_of(reviewed, "instruction", 1)["reviewed"])

    def test_partial_question_failure_cannot_be_reopened(self):
        payloads = city_payloads()
        payloads[0] = payload([], next_question="您更看重续航？还是更看重智驾？")
        result = score_run(build_record(payloads, comparison=comparison_rows(car_a(), car_e())),
                           self.references, self.catalog)
        instruction = item_of(result, "instruction", 1)
        self.assertIn("candidate_list_missing", instruction["reason"])
        self.assertFalse(instruction["reviewable"])
        self.assertEqual([row for row in result["review_rows"] if row["kind"] == "override"], [])

    def test_missing_parameter_table_needs_review(self):
        record = build_record(city_payloads())
        result = score_run(record, self.references, self.catalog)
        instruction = item_of(result, "instruction", 3)
        self.assertEqual(instruction["points"], 5)
        truth = item_of(result, "truthfulness", 3)
        self.assertFalse(truth["auto"])
        self.assertEqual(truth["points"], 0)
        self.assertEqual(result["pending_points"], 5)
        self.assertEqual(result["score"], 95)
        self.assertIsNone(result["success"])
        self.assertEqual(len(result["review_rows"]), 1)

    def test_review_pass_can_settle_pending_point(self):
        record = build_record(city_payloads())
        review = {(record["run_id"], 3, "truthfulness"): "pass"}
        result = score_run(record, self.references, self.catalog, review)
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["pending_points"], 0)
        self.assertTrue(result["success"])

    def test_comparison_price_mismatch_breaks_truthfulness(self):
        rows = comparison_rows(car_a(), car_e())
        rows["rows"][0]["price_wan"] = 99.9
        result = score_run(build_record(city_payloads(), comparison=rows), self.references, self.catalog)
        truth = item_of(result, "truthfulness", 3)
        self.assertEqual(truth["points"], 0)
        self.assertIn("comparison_price_mismatch", truth["reason"])

    def test_missing_fourth_turn_is_scored_as_failure(self):
        payloads = city_payloads()[:3]
        result = score_run(build_record(payloads, comparison=comparison_rows(car_a(), car_e())),
                           self.references, self.catalog)
        self.assertEqual(item_of(result, "constraint_fit", 4)["points"], 0)
        self.assertEqual(result["score"], 61)
        self.assertFalse(result["success"])

    def test_unknown_vehicle_breaks_fit_and_truthfulness(self):
        payloads = city_payloads()
        payloads[0] = payload([
            car("虚构车型 X", "标准版", 2026, 15.0, ["SIM-Z"]),
            car_e(),
        ], next_question="是否更看重续航？")
        result = score_run(build_record(payloads, comparison=comparison_rows(car_a(), car_e())),
                           self.references, self.catalog)
        self.assertEqual(item_of(result, "constraint_fit", 1)["points"], 0)
        self.assertEqual(item_of(result, "truthfulness", 1)["points"], 0)

    def test_unanchored_identity_is_rejected_even_when_facts_match(self):
        payloads = city_payloads()
        payloads[0] = payload([
            {"model": "教学车型A", "trim": "通勤版", "year": 2026, "price_wan": 14.8,
             "meets_constraints": [], "why_fit": "合规", "risks": [], "evidence_ids": []},
            car_e(),
        ], next_question="是否更看重续航？")
        result = score_run(build_record(payloads, comparison=comparison_rows(car_a(), car_e())),
                           self.references, self.catalog)
        self.assertEqual(item_of(result, "constraint_fit", 1)["points"], 10)
        truth = item_of(result, "truthfulness", 1)
        self.assertEqual(truth["points"], 0)
        self.assertIn("candidate_not_linked_by_evidence_id", truth["reason"])

    def test_change_scenario_flags_stale_budget(self):
        first = payload(
            [car_b(), car_c()],
            declared=[
                {"name": "预算", "value": "不超过24万元", "source_turn": 1, "status": "active"},
                {"name": "座位数", "value": "至少5座", "source_turn": 1, "status": "active"},
                {"name": "能源形式", "value": "插电混动", "source_turn": 1, "status": "active"},
            ],
            next_question="是否接受长途油耗？",
        )
        second = payload(
            [car_b()],
            declared=[
                {"name": "预算", "value": "不超过24万元", "source_turn": 1, "status": "active"},
                {"name": "预算", "value": "不超过19万元", "source_turn": 2, "status": "active"},
                {"name": "座位数", "value": "至少5座", "source_turn": 1, "status": "active"},
                {"name": "能源形式", "value": "插电混动", "source_turn": 1, "status": "active"},
            ],
            next_question="是否接受长途油耗？",
        )
        clean = payload(
            [car_b()],
            declared=[
                {"name": "预算", "value": "不超过19万元", "source_turn": 2, "status": "active"},
                {"name": "座位数", "value": "至少5座", "source_turn": 1, "status": "active"},
                {"name": "能源形式", "value": "插电混动", "source_turn": 1, "status": "active"},
            ],
            next_question=None,
        )
        final = payload(
            [car_b()],
            declared=clean["effective_constraints"],
            final={
                "model": "教学车型 B", "trim": "长途版", "year": 2026,
                "reason": "19万内唯一插混", "tradeoffs": ["纯电续航较短"],
            },
            status="final",
        )
        record = build_record(
            [first, second, clean, final], scenario_id="change",
            comparison=comparison_rows(car_b()),
        )
        result = score_run(record, self.references, self.catalog)
        consistency = item_of(result, "consistency", 2)
        self.assertEqual(consistency["points"], 0)
        self.assertIn("superseded_value_still_active:price_wan", consistency["reason"])
        self.assertEqual(result["subtotals"]["consistency"], 15)
        self.assertEqual(result["score"], 90)
        self.assertTrue(any(
            hint["hint"] == "superseded_value_not_declared:price_wan" for hint in result["hints"]
        ))

    def test_aggregate_groups_by_model_and_scenario(self):
        records = [self.perfect_city(), self.perfect_city()]
        results = [score_run(record, self.references, self.catalog) for record in records]
        rows = aggregate(results)
        keys = {(row["model_key"], row["scenario_id"]) for row in rows}
        self.assertIn(("zhipu_glm_47_flash", "city"), keys)
        self.assertIn(("zhipu_glm_47_flash", "全部场景"), keys)
        city = next(row for row in rows if row["scenario_id"] == "city")
        self.assertEqual(city["runs"], 2)
        self.assertEqual(city["mean_score"], 100)
        self.assertEqual(city["success"], 2)
        self.assertEqual(city["distinct_recommendations"], 1)
        self.assertEqual(city["recommendation_mix"], "SIM-A×2")

    def test_switching_between_eligible_vehicles_is_not_penalised(self):
        first = score_run(self.perfect_city(), self.references, self.catalog)
        payloads = city_payloads()
        payloads[3] = payload(
            [car_a(), car_e()], declared=constraints(ADAS),
            final={
                "model": "教学车型 E", "trim": "智驾版", "year": 2026,
                "reason": "同为合格候选，取其智驾配置", "tradeoffs": ["价格高2.7万元"],
            },
            status="final",
        )
        second = score_run(build_record(payloads, comparison=comparison_rows(car_a(), car_e())),
                           self.references, self.catalog)
        self.assertEqual(first["score"], 100)
        self.assertEqual(second["score"], 100)
        rows = aggregate([first, second])
        city = next(row for row in rows if row["scenario_id"] == "city")
        self.assertEqual(city["distinct_recommendations"], 2)
        self.assertEqual(city["recommendation_mix"], "SIM-A×1;SIM-E×1")
        self.assertEqual(city["mean_score"], 100)

    def test_match_vehicle_reports_conflicting_evidence(self):
        source_id, mode, problems = match_vehicle(car_a(evidence_ids=["SIM-E"]), self.catalog)
        self.assertEqual(source_id, "SIM-A")
        self.assertEqual(mode, "identity_fields")
        self.assertIn("evidence_id_conflict:SIM-E", problems)

    def test_cli_writes_score_tables(self):
        # Scratch batches live under the git-ignored runs/ directory so the test also
        # works under sandboxes that restrict writable temporary areas.
        temp = ROOT / "runs" / "_cli-test"
        if temp.exists():
            shutil.rmtree(temp, ignore_errors=True)
        temp.mkdir(parents=True)
        try:
            runs = temp / "runs"
            runs.mkdir()
            record = self.perfect_city()
            (runs / (record["run_id"] + ".json")).write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            exit_code = main(["--runs", str(runs)])
            self.assertEqual(exit_code, 0)
            out = runs / "scores"
            with (out / "scores.csv").open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["score"], "100")
            self.assertEqual(rows[0]["success"], "true")
            self.assertTrue((out / "summary.md").exists())
            self.assertTrue((out / "scores.json").exists())
            self.assertEqual(read_review(out / "review-queue.csv"), {})
        finally:
            shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
