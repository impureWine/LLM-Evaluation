import json
import unittest

from llm_eval.models import ChatMessage, ChatResult, ModelSpec, Usage
from llm_eval.prompts import PromptBundle
from llm_eval.structured import SchemaValidatedDecisionClient


def make_result(content, finish_reason="stop"):
    return ChatResult(
        model_key="test",
        requested_model="test-model",
        served_model="test-model",
        content=content,
        finish_reason=finish_reason,
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        latency_ms=100,
        attempts=1,
        attempt_latencies_ms=(100,),
    )


def valid_payload():
    return {
        "turn_summary": "找到一个满足预算的候选车型。",
        "effective_constraints": [
            {
                "name": "预算",
                "value": "20 万元以内",
                "source_turn": 1,
                "status": "active",
            }
        ],
        "candidate_cars": [
            {
                "model": "示例车",
                "trim": "基础版",
                "year": 2026,
                "price_wan": 18,
                "meets_constraints": ["预算"],
                "why_fit": "价格在预算内。",
                "risks": ["配置相对基础。"],
                "evidence_ids": ["car-1"],
            }
        ],
        "final_recommendation": {
            "model": "示例车",
            "trim": "基础版",
            "year": 2026,
            "reason": "满足本轮全部硬约束。",
            "tradeoffs": ["配置相对基础。"],
        },
        "next_question": None,
        "confidence": "medium",
        "status": "final",
        "assumptions": [],
    }


class FakeClient:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.requests = []

    def complete(self, spec, messages):
        self.requests.append(list(messages))
        return self.outputs.pop(0)


class StructuredDecisionTests(unittest.TestCase):
    def setUp(self):
        self.spec = ModelSpec(
            key="test",
            display_name="Test",
            role="test",
            model_id="test-model",
            provider="openai_compatible",
            endpoint="https://example.invalid",
            api_key_env="TEST_KEY",
            timeout_seconds=5,
            max_retries=0,
        )
        self.messages = [
            ChatMessage(role="system", content="Return JSON."),
            ChatMessage(role="user", content="Start."),
        ]

    def test_accepts_valid_output_without_correction(self):
        fake = FakeClient([make_result(json.dumps(valid_payload(), ensure_ascii=False))])
        client = SchemaValidatedDecisionClient(fake, PromptBundle.from_directory())
        result = client.complete(self.spec, self.messages)
        self.assertTrue(result.valid)
        self.assertEqual(0, result.correction_attempts)
        self.assertEqual(1, len(fake.requests))

    def test_one_correction_is_added_after_invalid_output(self):
        fake = FakeClient(
            [
                make_result("这不是 JSON"),
                make_result(json.dumps(valid_payload(), ensure_ascii=False)),
            ]
        )
        client = SchemaValidatedDecisionClient(fake, PromptBundle.from_directory())
        result = client.complete(self.spec, self.messages)
        self.assertTrue(result.valid)
        self.assertEqual(1, result.correction_attempts)
        self.assertEqual(2, len(fake.requests))
        self.assertEqual("assistant", fake.requests[1][-2].role)
        self.assertIn("无法通过数据结构校验", fake.requests[1][-1].content)
        self.assertEqual(30, result.total_usage.total_tokens)
        self.assertEqual(200, result.total_latency_ms)

    def test_returns_invalid_after_correction_budget(self):
        fake = FakeClient([make_result("bad"), make_result("still bad")])
        client = SchemaValidatedDecisionClient(
            fake,
            PromptBundle.from_directory(),
            max_corrections=1,
        )
        result = client.complete(self.spec, self.messages)
        self.assertFalse(result.valid)
        self.assertEqual(1, result.correction_attempts)
        self.assertEqual(2, len(result.all_results))


if __name__ == "__main__":
    unittest.main()

