import json
import unittest

from llm_eval.schema import parse_decision_output, validate_decision_output


def valid_output():
    return {
        "turn_summary": "根据 20 万元预算筛选出两个候选车型。",
        "effective_constraints": [
            {
                "name": "预算",
                "value": "不超过 20 万元",
                "source_turn": 1,
                "status": "active",
            }
        ],
        "candidate_cars": [
            {
                "model": "测试车型",
                "trim": "舒适版",
                "year": 2026,
                "price_wan": 18.5,
                "meets_constraints": ["预算"],
                "why_fit": "售价和城市通勤需求均满足。",
                "risks": ["需要核实当地终端优惠。"],
                "evidence_ids": ["car-1"],
            }
        ],
        "final_recommendation": {
            "model": "测试车型",
            "trim": "舒适版",
            "year": 2026,
            "reason": "在预算内满足通勤需求。",
            "tradeoffs": ["智能驾驶配置为选装。"],
        },
        "next_question": None,
        "confidence": "medium",
        "status": "final",
        "assumptions": [],
    }


class SchemaValidationTests(unittest.TestCase):
    def test_accepts_valid_decision(self):
        self.assertEqual([], validate_decision_output(valid_output()))

    def test_parses_json_and_reports_missing_field(self):
        value = valid_output()
        del value["confidence"]
        payload, issues = parse_decision_output(json.dumps(value, ensure_ascii=False))
        self.assertIsNotNone(payload)
        self.assertTrue(any("$.confidence" in str(issue) for issue in issues))

    def test_rejects_markdown_fenced_json(self):
        content = "```json\n{}\n```"
        payload, issues = parse_decision_output(content)
        self.assertIsNone(payload)
        self.assertTrue(issues)

    def test_rejects_final_and_question_together(self):
        value = valid_output()
        value["next_question"] = "还需要问什么？"
        issues = validate_decision_output(value)
        self.assertTrue(any("next_question" in str(issue) for issue in issues))

    def test_rejects_unverifiable_candidate(self):
        value = valid_output()
        value["candidate_cars"][0]["evidence_ids"] = []
        issues = validate_decision_output(value)
        self.assertTrue(any("evidence_ids" in str(issue) for issue in issues))


if __name__ == "__main__":
    unittest.main()

