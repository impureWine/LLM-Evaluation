"""Boundary regressions for the change scenario: the budget edge and the no-solution branch.

These tests are offline and call no model API.  They exist because case C2 asks what
happens when a requirement change leaves no eligible vehicle: the frozen data says
"18.6 万 still has one car, 18.5 万 has none", and the scoring rules must behave
predictably in that branch even though the formal matrix never visits it.
"""

import copy
import json
from pathlib import Path
import unittest

from llm_eval.dataset import constraint_history, fits
from llm_eval.scoring import Catalog, score_run


ROOT = Path(__file__).resolve().parents[1]


def load_inputs():
    design = json.loads((ROOT / "configs/evaluation-v1.json").read_text(encoding="utf-8-sig"))
    rules = json.loads((ROOT / "configs/scenario-rules-v1.json").read_text(encoding="utf-8-sig"))
    catalog = Catalog(design["vehicle_data"])
    rule = copy.deepcopy(next(item for item in rules["scenarios"] if item["id"] == "change"))
    return design, catalog, rule


def variant(design, rule, budget):
    """Reference turns for the change scenario with a modified second-turn budget."""
    rule["events"][0]["constraint"]["value"] = budget
    turns = []
    for turn in (1, 2, 3, 4):
        history = constraint_history(rule, turn)
        active = [item for item in history if item["status"] == "active"]
        eligible = [
            vehicle["source_id"] for vehicle in design["vehicle_data"]
            if all(fits(vehicle, item) for item in active)
        ]
        turns.append({"turn": turn, "constraints": history,
                      "eligible_source_ids": eligible, "excluded": []})
    return {"scenario_id": "change", "turns": turns}


def car(catalog, source_id):
    vehicle = catalog.by_source[source_id]
    return {
        "model": vehicle["model"], "trim": vehicle["trim"], "year": vehicle["year"],
        "price_wan": vehicle["price_wan"], "meets_constraints": [],
        "why_fit": "价格{}万元，插电混动，5座，L2辅助驾驶".format(vehicle["price_wan"]),
        "risks": [], "evidence_ids": [source_id],
    }


def comparison(catalog, source_id):
    vehicle = catalog.by_source[source_id]
    return [{key: vehicle[key] for key in
             ("source_id", "model", "trim", "year", "price_wan", "energy", "seats", "adas")}]


def ledger(budget, supersede_old=True):
    entries = [
        {"name": "座位数", "value": "至少5座", "source_turn": 1, "status": "active"},
        {"name": "能源形式", "value": "插电混动", "source_turn": 1, "status": "active"},
        {"name": "预算", "value": "不超过{}万元".format(budget), "source_turn": 2, "status": "active"},
    ]
    if supersede_old:
        entries.insert(0, {"name": "预算", "value": "不超过24万元",
                           "source_turn": 1, "status": "superseded"})
    return entries


def synthetic_record(catalog, declared_budget):
    """A deliberately best-effort answer at the 18.5 万 boundary.

    The payload is a hand-written fixture, not model output: the candidate list has
    to stay non-empty because the output schema requires at least one candidate.
    """
    payloads = [
        {"turn_summary": "初选", "effective_constraints": ledger(declared_budget),
         "candidate_cars": [car(catalog, "SIM-B"), car(catalog, "SIM-C")],
         "parameter_comparison": [],
         "final_recommendation": None, "next_question": "是否接受插混？",
         "confidence": "medium", "status": "candidate_only", "assumptions": []},
        {"turn_summary": "更新", "effective_constraints": ledger(declared_budget),
         "candidate_cars": [car(catalog, "SIM-B")], "parameter_comparison": [],
         "final_recommendation": None,
         "next_question": "是否接受18.6万元车型？", "confidence": "medium",
         "status": "candidate_only", "assumptions": []},
        {"turn_summary": "对比", "effective_constraints": ledger(declared_budget),
         "candidate_cars": [car(catalog, "SIM-B")],
         "parameter_comparison": comparison(catalog, "SIM-B"),
         "final_recommendation": None,
         "next_question": None, "confidence": "medium",
         "status": "candidate_only", "assumptions": []},
        {"turn_summary": "推荐", "effective_constraints": ledger(declared_budget),
         "candidate_cars": [car(catalog, "SIM-B")], "parameter_comparison": [],
         "final_recommendation": {"model": "教学车型 B", "trim": "长途版", "year": 2026,
                                  "reason": "当前唯一接近条件的车型",
                                  "tradeoffs": ["超出新预算0.1万元"]},
         "next_question": None, "confidence": "medium", "status": "final", "assumptions": []},
    ]
    turns = []
    for index, payload in enumerate(payloads, start=1):
        rows = payload["parameter_comparison"]
        entry = {"turn": index, "model_key": "zhipu_glm_47_flash", "valid": True,
                 "validation_issues": [], "correction_attempts": 0,
                 "total_usage": {"total_tokens": 100}, "total_latency_ms": 1000,
                 "comparison_audit": {"passed": True, "issues": [], "checked_rows": len(rows)},
                 "parsed_output": payload}
        turns.append(entry)
    return {"run_id": "synthetic-change-18.5", "scenario_id": "change", "repetition": 1,
            "batch_kind": "synthetic_fixture", "turns": turns, "elapsed_ms": 4000,
            "output_contract_completed": True}


def item_of(result, dimension, turn):
    for item in result["items"]:
        if item["dimension"] == dimension and item["turn"] == turn:
            return item
    raise AssertionError("missing item {}#{}".format(dimension, turn))


class ChangeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.design, self.catalog, self.rule = load_inputs()

    def test_budget_edge_switches_from_one_vehicle_to_none(self):
        def eligible(budget):
            return variant(self.design, copy.deepcopy(self.rule), budget)["turns"][1]["eligible_source_ids"]

        self.assertEqual(eligible(19), ["SIM-B"])
        self.assertEqual(eligible(18.6), ["SIM-B"])   # inclusive upper bound keeps B
        self.assertEqual(eligible(18.5), [])          # first no-solution budget

    def test_no_solution_branch_cannot_reach_full_marks(self):
        reference = variant(self.design, copy.deepcopy(self.rule), 18.5)
        result = score_run(synthetic_record(self.catalog, 18.5), {"change": reference}, self.catalog)
        self.assertLess(result["score"], 100)
        self.assertEqual(item_of(result, "constraint_fit", 2)["points"], 0)
        self.assertEqual(item_of(result, "constraint_fit", 4)["points"], 0)
        self.assertEqual(item_of(result, "constraint_fit", 1)["points"], 10)
        self.assertFalse(result["success"])

    def test_honest_ledger_beats_silent_drift(self):
        reference = variant(self.design, copy.deepcopy(self.rule), 18.5)
        honest = score_run(synthetic_record(self.catalog, 18.5), {"change": reference}, self.catalog)
        drift = score_run(synthetic_record(self.catalog, 19), {"change": reference}, self.catalog)
        self.assertGreater(honest["score"], drift["score"])
        self.assertEqual(item_of(honest, "consistency", 2)["points"], 10)
        self.assertEqual(item_of(drift, "consistency", 2)["points"], 0)
        self.assertIn("new_constraint_missing:price_wan",
                      item_of(drift, "consistency", 2)["reason"])


if __name__ == "__main__":
    unittest.main()
