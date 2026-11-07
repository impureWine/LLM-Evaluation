"""Configuration and response data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from llm_eval.errors import ConfigurationError


CHAT_ROLES = {"system", "user", "assistant"}


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str

    def __post_init__(self):
        if self.role not in CHAT_ROLES:
            raise ConfigurationError("Unsupported chat role: {!r}".format(self.role))
        if not isinstance(self.content, str) or not self.content.strip():
            raise ConfigurationError("Chat message content must be a non-empty string")

    def as_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_mapping(cls, value: Optional[Mapping[str, Any]]) -> "Usage":
        if not value:
            return cls()
        return cls(
            prompt_tokens=_safe_int(value.get("prompt_tokens")),
            completion_tokens=_safe_int(value.get("completion_tokens")),
            total_tokens=_safe_int(value.get("total_tokens")),
        )

    def as_dict(self) -> Dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True)
class ModelSpec:
    key: str
    display_name: str
    role: str
    model_id: str
    provider: str
    endpoint: str
    api_key_env: str
    timeout_seconds: float
    max_retries: int
    enabled: bool = True
    parameters: Mapping[str, Any] = field(default_factory=dict)
    notes: str = ""

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        shared_parameters: Optional[Mapping[str, Any]] = None,
    ) -> "ModelSpec":
        required = (
            "key",
            "display_name",
            "role",
            "model_id",
            "provider",
            "endpoint",
            "api_key_env",
        )
        missing = [name for name in required if not value.get(name)]
        if missing:
            raise ConfigurationError(
                "Model entry is missing required fields: {}".format(", ".join(missing))
            )

        parameters = dict(shared_parameters or {})
        parameters.update(value.get("parameters") or {})
        if value.get("model_id") != parameters.get("model"):
            parameters.pop("model", None)

        return cls(
            key=str(value["key"]),
            display_name=str(value["display_name"]),
            role=str(value["role"]),
            model_id=str(value["model_id"]),
            provider=str(value["provider"]),
            endpoint=str(value["endpoint"]),
            api_key_env=str(value["api_key_env"]),
            timeout_seconds=float(value.get("timeout_seconds", 90)),
            max_retries=int(value.get("max_retries", 2)),
            enabled=bool(value.get("enabled", True)),
            parameters=parameters,
            notes=str(value.get("notes", "")),
        )


@dataclass(frozen=True)
class ModelRegistry:
    platform: str
    recorded_on: str
    shared_parameters: Mapping[str, Any]
    models: Mapping[str, ModelSpec]

    def get(self, key: str) -> ModelSpec:
        try:
            return self.models[key]
        except KeyError as exc:
            raise ConfigurationError(
                "Unknown model key {!r}; available: {}".format(
                    key, ", ".join(sorted(self.models))
                )
            ) from exc

    def ordered(self) -> List[ModelSpec]:
        return list(self.models.values())

    def enabled(self) -> List[ModelSpec]:
        return [spec for spec in self.models.values() if spec.enabled]


@dataclass(frozen=True)
class ChatResult:
    model_key: str
    requested_model: str
    served_model: str
    content: str
    finish_reason: str
    usage: Usage
    latency_ms: int
    attempts: int
    response_id: str = ""
    reasoning_present: bool = False
    attempt_latencies_ms: Tuple[int, ...] = ()

    def as_record(self) -> Dict[str, Any]:
        return {
            "model_key": self.model_key,
            "requested_model": self.requested_model,
            "served_model": self.served_model,
            "content": self.content,
            "finish_reason": self.finish_reason,
            "usage": self.usage.as_dict(),
            "latency_ms": self.latency_ms,
            "attempts": self.attempts,
            "response_id": self.response_id,
            "reasoning_present": self.reasoning_present,
            "attempt_latencies_ms": list(self.attempt_latencies_ms),
        }


def normalize_messages(messages: Iterable[ChatMessage]) -> List[Dict[str, str]]:
    normalized = []
    for message in messages:
        if isinstance(message, ChatMessage):
            normalized.append(message.as_dict())
        elif isinstance(message, Mapping):
            normalized.append(ChatMessage(
                role=str(message.get("role", "")),
                content=str(message.get("content", "")),
            ).as_dict())
        else:
            raise ConfigurationError("Messages must be ChatMessage values or mappings")
    if not normalized:
        raise ConfigurationError("At least one chat message is required")
    if normalized[0]["role"] != "system":
        raise ConfigurationError("The first message must use the system role")
    return normalized

