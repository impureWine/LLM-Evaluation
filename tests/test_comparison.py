import unittest

from llm_eval.comparison import audit_parameter_comparison


VEHICLES = [
    {
        "source_id": "SIM-A",
        "model": "教学车型 A",
        "trim": "通勤版",
        "year": 2026,
        "price_wan": 14.8,
        "energy": "纯电",
        "seats": 5,
        "adas": "L2",
    }
]


class ComparisonAuditTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "candidate_cars": [
                {"model": "教学车型 A", "trim": "通勤版", "year": 2026, "evidence_ids": ["SIM-A"]}
            ],
            "parameter_comparison": [dict(VEHICLES[0])],
        }

    def test_accepts_exact_candidate_parameter_rows(self):
        self.assertEqual([], audit_parameter_comparison(self.payload, VEHICLES))

    def test_detects_missing_candidate_rows(self):
        self.payload["parameter_comparison"] = []
        issues = audit_parameter_comparison(self.payload, VEHICLES)
        self.assertTrue(any("missing comparison rows" in issue for issue in issues))

    def test_detects_mismatched_vehicle_facts(self):
        self.payload["parameter_comparison"][0]["price_wan"] = 15
        issues = audit_parameter_comparison(self.payload, VEHICLES)
        self.assertTrue(any("price_wan" in issue for issue in issues))

    def test_detects_candidate_with_mismatched_source_id(self):
        self.payload["candidate_cars"][0]["evidence_ids"] = ["SIM-B"]
        issues = audit_parameter_comparison(self.payload, VEHICLES)
        self.assertTrue(any("source_id" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
