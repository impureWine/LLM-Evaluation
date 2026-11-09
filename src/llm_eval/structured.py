"""Schema validation and one controlled corrective retry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Mapping, Optional, Tuple

from llm_eval.models import ChatMessage, ChatResult, ModelSpec, Usage
from llm_eval.openai_compatible import OpenAICompatibleClient
from llm_eval.prompts import PromptBundle
from llm_eval.schema import ValidationIssue, parse_decision_output


CORRECTION_TEMPLATE = (
    "上一轮输出无法通过数据结构校验，问题如下：\n"
    "{issues}\n\n"
    "请重新回答当前购车决策问题。只输出一个合法 JSON 对象，严格满足系统消息中的 Schema，"
    "不要使用 Markdown 代码块，也不要省略与车型库来源编号相关的字段。"
)


@dataclass(frozen=True)
class StructuredResult:
    final: ChatResult
    payload: Optional[Mapping[str, Any]]
    valid: bool
    issues: Tuple[ValidationIssue, ...]
    correction_attempts: int
    all_results: Tuple[ChatResult, ...]
    prompt_fingerprint: str

    @property
    def total_usage(self) -> Usage:
        return Usage(
            prompt_tokens=sum(result.usage.prompt_tokens for result in self.all_results),
            completion_tokens=sum(
                result.usage.completion_tokens for result in self.all_results
            ),
            total_tokens=sum(result.usage.total_tokens for result in self.all_results),
            reported=bool(self.all_results) and all(result.usage.reported for result in self.all_results),
        )

    @property
    def total_latency_ms(self) -> int:
        return sum(result.latency_ms for result in self.all_results)

    def as_record(self) -> Mapping[str, Any]:
        return {
            "model_key": self.final.model_key,
            "requested_model": self.final.requested_model,
            "served_model": self.final.served_model,
            "valid": self.valid,
            "validation_issues": [str(issue) for issue in self.issues],
            "correction_attempts": self.correction_attempts,
            "prompt_fingerprint": self.prompt_fingerprint,
            "total_usage": self.total_usage.as_dict(),
            "total_latency_ms": self.total_latency_ms,
            "final_response": self.final.as_record(),
            "attempts": [result.as_record() for result in self.all_results],
            "parsed_output": self.payload,
        }


class SchemaValidatedDecisionClient:
    def __init__(
        self,
        base_client: OpenAICompatibleClient,
        prompt_bundle: PromptBundle,
        max_corrections: int = 1,
    ):
        if max_corrections < 0:
            raise ValueError("max_corrections cannot be negative")
        self._base_client = base_client
        self._prompt_bundle = prompt_bundle
        self._max_corrections = max_corrections

    def complete(
        self,
        spec: ModelSpec,
        messages: Iterable[ChatMessage],
    ) -> StructuredResult:
        conversation: List[ChatMessage] = list(messages)
        results: List[ChatResult] = []
        corrections = 0

        while True:
            result = self._base_client.complete(spec, conversation)
            results.append(result)
            payload, issues = parse_decision_output(result.content)
            if result.finish_reason != "stop":
                issues = list(issues)
                issues.append(
                    ValidationIssue(
                        "$.finish_reason",
                        "expected stop but received {!r}".format(result.finish_reason),
                    )
                )

            if not issues:
                return StructuredResult(
                    final=result,
                    payload=payload,
                    valid=True,
                    issues=(),
                    correction_attempts=corrections,
                    all_results=tuple(results),
                    prompt_fingerprint=self._prompt_bundle.fingerprint,
                )

            if corrections >= self._max_corrections:
                return StructuredResult(
                    final=result,
                    payload=payload,
                    valid=False,
                    issues=tuple(issues),
                    correction_attempts=corrections,
                    all_results=tuple(results),
                    prompt_fingerprint=self._prompt_bundle.fingerprint,
                )

            correction = ChatMessage(
                role="user",
                content=CORRECTION_TEMPLATE.format(
                    issues="\n".join("- {}".format(issue) for issue in issues)
                ),
            )
            if result.content.strip():
                conversation.append(
                    ChatMessage(role="assistant", content=result.content.strip())
                )
            conversation.append(correction)
            corrections += 1

