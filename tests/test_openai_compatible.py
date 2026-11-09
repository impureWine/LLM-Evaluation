import json
import os
import unittest
from unittest.mock import patch

from llm_eval.errors import AuthenticationConfigurationError, ModelAPIError
from llm_eval.models import ChatMessage, ModelSpec, Usage
from llm_eval.openai_compatible import HttpResponse, OpenAICompatibleClient


def make_spec(max_retries=2):
    return ModelSpec(
        key="test_model",
        display_name="Test Model",
        role="test",
        model_id="test-model-id",
        provider="openai_compatible",
        endpoint="https://example.invalid/chat/completions",
        api_key_env="TEST_MODEL_KEY",
        timeout_seconds=5,
        max_retries=max_retries,
        parameters={
            "temperature": 0.0,
            "top_p": 1.0,
            "max_tokens": 100,
            "response_format": {"type": "json_object"},
        },
    )


def success_body(content='{"ok": true}', model="served-model"):
    return json.dumps(
        {
            "id": "resp-123",
            "model": model,
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": content,
                        "reasoning_content": "provider-private reasoning",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 7,
                "total_tokens": 19,
            },
        }
    ).encode("utf-8")


class OpenAICompatibleClientTests(unittest.TestCase):
    def setUp(self):
        self.messages = [
            ChatMessage(role="system", content="Return JSON."),
            ChatMessage(role="user", content="Hello"),
        ]

    @patch.dict(os.environ, {"TEST_MODEL_KEY": "unit-test-secret"}, clear=False)
    def test_posts_context_and_returns_usage(self):
        captured = {}

        def transport(url, headers, body, timeout):
            captured.update(
                {
                    "url": url,
                    "headers": headers,
                    "body": json.loads(body.decode("utf-8")),
                    "timeout": timeout,
                }
            )
            return HttpResponse(200, {}, success_body())

        result = OpenAICompatibleClient(
            transport=transport,
            sleep=lambda _: None,
        ).complete(make_spec(), self.messages)

        self.assertEqual("https://example.invalid/chat/completions", captured["url"])
        self.assertEqual("Bearer unit-test-secret", captured["headers"]["Authorization"])
        self.assertEqual("test-model-id", captured["body"]["model"])
        self.assertEqual(2, len(captured["body"]["messages"]))
        self.assertEqual(0.0, captured["body"]["temperature"])
        self.assertEqual("served-model", result.served_model)
        self.assertEqual(19, result.usage.total_tokens)
        self.assertTrue(result.usage.reported)
        self.assertTrue(result.reasoning_present)
        self.assertNotIn("provider-private reasoning", result.content)

    def test_missing_usage_is_not_reported_as_zero_tokens(self):
        self.assertFalse(Usage.from_mapping(None).reported)
        self.assertFalse(Usage.from_mapping({"prompt_tokens": 10}).reported)
        self.assertTrue(Usage.from_mapping({"total_tokens": 0}).reported)

    @patch.dict(os.environ, {"TEST_MODEL_KEY": "unit-test-secret"}, clear=False)
    def test_retries_server_error_then_succeeds(self):
        calls = {"count": 0}

        def transport(url, headers, body, timeout):
            calls["count"] += 1
            if calls["count"] == 1:
                return HttpResponse(503, {}, b'{"error":"busy"}')
            return HttpResponse(200, {}, success_body())

        result = OpenAICompatibleClient(
            transport=transport,
            sleep=lambda _: None,
        ).complete(make_spec(max_retries=2), self.messages)

        self.assertEqual(2, calls["count"])
        self.assertEqual(2, result.attempts)
        self.assertEqual(2, len(result.attempt_latencies_ms))

    @patch.dict(os.environ, {"TEST_MODEL_KEY": "unit-test-secret"}, clear=False)
    def test_does_not_retry_client_error(self):
        calls = {"count": 0}

        def transport(url, headers, body, timeout):
            calls["count"] += 1
            return HttpResponse(400, {}, b'{"error":"bad request"}')

        with self.assertRaises(ModelAPIError) as raised:
            OpenAICompatibleClient(
                transport=transport,
                sleep=lambda _: None,
            ).complete(make_spec(max_retries=2), self.messages)

        self.assertEqual(1, calls["count"])
        self.assertEqual(400, raised.exception.status_code)

    def test_missing_key_is_reported_without_request(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(AuthenticationConfigurationError):
                OpenAICompatibleClient(
                    transport=lambda *_: self.fail("Transport must not be called"),
                ).complete(make_spec(), self.messages)


if __name__ == "__main__":
    unittest.main()

