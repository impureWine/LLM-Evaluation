"""HTTP client for OpenAI-compatible chat-completions APIs."""

from __future__ import annotations

import json
import os
import socket
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from llm_eval.env import load_local_env
from llm_eval.errors import (
    AuthenticationConfigurationError,
    InvalidModelResponse,
    ModelAPIError,
    TransportError,
)
from llm_eval.models import ChatMessage, ChatResult, ModelSpec, Usage, normalize_messages


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


Transport = Callable[[str, Dict[str, str], bytes, float], HttpResponse]


class UrllibTransport:
    def __call__(
        self,
        url: str,
        headers: Dict[str, str],
        body: bytes,
        timeout: float,
    ) -> HttpResponse:
        request = Request(url=url, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=timeout) as response:
                return HttpResponse(
                    status=int(response.status),
                    headers=dict(response.headers.items()),
                    body=response.read(),
                )
        except HTTPError as exc:
            return HttpResponse(
                status=int(exc.code),
                headers=dict(exc.headers.items()) if exc.headers else {},
                body=exc.read(),
            )
        except (URLError, socket.timeout, TimeoutError) as exc:
            raise TransportError("Network request failed: {}".format(exc)) from exc


class OpenAICompatibleClient:
    """Call one configured model while keeping credentials out of logs."""

    def __init__(
        self,
        transport: Optional[Transport] = None,
        sleep: Optional[Callable[[float], None]] = None,
        monotonic: Optional[Callable[[], float]] = None,
    ):
        self._transport = transport or UrllibTransport()
        self._sleep = sleep or time.sleep
        self._monotonic = monotonic or time.monotonic

    def complete(
        self,
        spec: ModelSpec,
        messages: Iterable[ChatMessage],
    ) -> ChatResult:
        if spec.provider != "openai_compatible":
            raise ModelAPIError("Unsupported provider: {}".format(spec.provider))

        load_local_env()
        api_key = os.environ.get(spec.api_key_env, "").strip()
        if not api_key:
            raise AuthenticationConfigurationError(
                "Required environment variable is not set: {}".format(spec.api_key_env)
            )

        normalized = normalize_messages(messages)
        payload = {
            "model": spec.model_id,
            "messages": normalized,
            "stream": False,
        }
        payload.update(spec.parameters)
        request_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": "Bearer {}".format(api_key),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        started = self._monotonic()
        attempt_latencies = []
        attempts_allowed = max(0, spec.max_retries) + 1

        for attempt in range(1, attempts_allowed + 1):
            attempt_started = self._monotonic()
            try:
                response = self._transport(
                    spec.endpoint,
                    headers,
                    request_body,
                    spec.timeout_seconds,
                )
            except TransportError:
                attempt_latencies.append(self._elapsed_ms(attempt_started))
                if attempt < attempts_allowed:
                    self._sleep(self._backoff_seconds(attempt))
                    continue
                raise TransportError(
                    "Request failed after {} attempt(s)".format(attempt)
                )

            attempt_latencies.append(self._elapsed_ms(attempt_started))
            if 200 <= response.status < 300:
                result = self._parse_response(response.body, spec, attempt)
                total_latency = self._elapsed_ms(started)
                return ChatResult(
                    model_key=result.model_key,
                    requested_model=result.requested_model,
                    served_model=result.served_model,
                    content=result.content,
                    finish_reason=result.finish_reason,
                    usage=result.usage,
                    latency_ms=total_latency,
                    attempts=attempt,
                    response_id=result.response_id,
                    reasoning_present=result.reasoning_present,
                    attempt_latencies_ms=tuple(attempt_latencies),
                )

            if self._is_retryable_status(response.status) and attempt < attempts_allowed:
                self._sleep(self._retry_delay(response, attempt))
                continue

            excerpt = _body_excerpt(response.body)
            raise ModelAPIError(
                "{} returned HTTP {}".format(spec.display_name, response.status),
                status_code=response.status,
                response_excerpt=excerpt,
            )

        raise ModelAPIError("Request loop ended unexpectedly")

    def _parse_response(
        self,
        body: bytes,
        spec: ModelSpec,
        attempts: int,
    ) -> ChatResult:
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidModelResponse("Provider response is not valid UTF-8 JSON") from exc

        choices = data.get("choices") if isinstance(data, Mapping) else None
        if not isinstance(choices, list) or not choices:
            raise InvalidModelResponse("Provider response has no choices")
        choice = choices[0]
        message = choice.get("message") if isinstance(choice, Mapping) else None
        if not isinstance(message, Mapping):
            raise InvalidModelResponse("Provider response has no assistant message")

        content = message.get("content")
        if not isinstance(content, str):
            raise InvalidModelResponse("Assistant content is missing or is not a string")

        served_model = str(data.get("model") or "")
        if not served_model:
            raise InvalidModelResponse("Provider response does not identify the served model")

        return ChatResult(
            model_key=spec.key,
            requested_model=spec.model_id,
            served_model=served_model,
            content=content,
            finish_reason=str(choice.get("finish_reason") or ""),
            usage=Usage.from_mapping(data.get("usage")),
            latency_ms=0,
            attempts=attempts,
            response_id=str(data.get("id") or ""),
            reasoning_present=bool(message.get("reasoning_content")),
        )

    def _elapsed_ms(self, started: float) -> int:
        return int(round((self._monotonic() - started) * 1000))

    @staticmethod
    def _is_retryable_status(status: int) -> bool:
        return status in {408, 409, 429} or status >= 500

    def _retry_delay(self, response: HttpResponse, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After") or response.headers.get("retry-after")
        if retry_after:
            try:
                return max(0.0, min(float(retry_after), 10.0))
            except ValueError:
                pass
        return self._backoff_seconds(attempt)

    @staticmethod
    def _backoff_seconds(attempt: int) -> float:
        return min(0.5 * (2 ** (attempt - 1)), 4.0)


def _body_excerpt(body: bytes, limit: int = 500) -> str:
    try:
        text = body.decode("utf-8", errors="replace")
    except Exception:
        return "<unreadable response body>"
    text = " ".join(text.split())
    return text[:limit]

