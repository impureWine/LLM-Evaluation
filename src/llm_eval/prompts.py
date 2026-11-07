"""Versioned, shared prompt bundles used identically by every model."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from llm_eval.config import project_root
from llm_eval.errors import ConfigurationError
from llm_eval.models import ChatMessage


PLACEHOLDER_PATTERN = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


def default_prompt_directory() -> Path:
    return project_root() / "prompts"


def _read_required(path: Path) -> str:
    if not path.exists():
        raise ConfigurationError("Prompt file does not exist: {}".format(path))
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ConfigurationError("Prompt file is empty: {}".format(path))
    return value


def render_template(template: str, values: Mapping[str, str]) -> str:
    placeholders = set(PLACEHOLDER_PATTERN.findall(template))
    missing = sorted(placeholders - set(values))
    if missing:
        raise ConfigurationError(
            "Missing prompt values: {}".format(", ".join(missing))
        )

    def replace(match: re.Match) -> str:
        name = match.group(1)
        return str(values[name])

    return PLACEHOLDER_PATTERN.sub(replace, template)


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


@dataclass(frozen=True)
class PromptBundle:
    system_template: str
    initial_user_template: str
    followup_user_template: str
    output_schema_text: str
    fingerprint: str
    version: str = "v1"

    @classmethod
    def from_directory(cls, directory: Optional[Path] = None) -> "PromptBundle":
        prompt_dir = Path(directory) if directory else default_prompt_directory()
        files = {
            "system": prompt_dir / "system_v1.md",
            "initial": prompt_dir / "initial_user_v1.md",
            "followup": prompt_dir / "followup_user_v1.md",
            "schema": prompt_dir / "output_schema_v1.json",
        }
        contents = {name: _read_required(path) for name, path in files.items()}

        try:
            schema = json.loads(contents["schema"])
        except json.JSONDecodeError as exc:
            raise ConfigurationError(
                "Output schema is not valid JSON: {}".format(exc)
            ) from exc
        if not isinstance(schema, Mapping) or schema.get("type") != "object":
            raise ConfigurationError("Output schema must describe a JSON object")

        canonical = "\n\0\n".join(
            [
                contents["system"],
                contents["initial"],
                contents["followup"],
                contents["schema"],
            ]
        ).encode("utf-8")

        return cls(
            system_template=contents["system"],
            initial_user_template=contents["initial"],
            followup_user_template=contents["followup"],
            output_schema_text=contents["schema"],
            fingerprint=hashlib.sha256(canonical).hexdigest(),
        )

    def initial_messages(
        self,
        scenario: Any,
        vehicle_data: Any,
    ) -> List[ChatMessage]:
        system = render_template(
            self.system_template,
            {"OUTPUT_SCHEMA": self.output_schema_text},
        )
        initial_user = render_template(
            self.initial_user_template,
            {
                "SCENARIO_JSON": _json_text(scenario),
                "VEHICLE_DATA_JSON": _json_text(vehicle_data),
            },
        )
        return [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=initial_user),
        ]

    def followup_message(
        self,
        turn_number: int,
        user_message: str,
        change_rule: str = "",
    ) -> ChatMessage:
        if turn_number < 2:
            raise ConfigurationError("Follow-up turn number must be at least 2")
        if not user_message.strip():
            raise ConfigurationError("Follow-up user message cannot be empty")
        content = render_template(
            self.followup_user_template,
            {
                "TURN_NUMBER": str(turn_number),
                "USER_MESSAGE": user_message.strip(),
                "CHANGE_RULE": change_rule.strip() or "（无）",
            },
        )
        return ChatMessage(role="user", content=content)

    def public_fingerprint(self) -> Dict[str, str]:
        return {"prompt_version": self.version, "prompt_sha256": self.fingerprint}

