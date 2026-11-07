"""Load project-local environment values without exposing credentials."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional

from llm_eval.errors import ConfigurationError


LEGACY_ENV_ALIASES = {
    "LLM_EVAL_ZHIPU_API_KEY": "LLM_EVAL_DEEPSEEK_API_KEY",
}


def default_env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def load_local_env(path: Optional[Path] = None) -> None:
    """Load KEY=VALUE pairs while preserving existing process-level values."""
    env_path = Path(path) if path else default_env_path()
    if not env_path.exists():
        return

    for line_number, raw_line in _iter_lines(env_path.read_text(encoding="utf-8-sig")):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            raise ConfigurationError(
                "Invalid .env line {}: expected KEY=VALUE".format(line_number)
            )
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ConfigurationError(
                "Invalid .env line {}: empty variable name".format(line_number)
            )
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if value and key not in os.environ:
            os.environ[key] = value

    # Preserve the key already entered under the previous provider-specific name.
    for current_name, legacy_name in LEGACY_ENV_ALIASES.items():
        if not os.environ.get(current_name) and os.environ.get(legacy_name):
            os.environ[current_name] = os.environ[legacy_name]


def _iter_lines(text: str) -> Iterable[tuple]:
    return enumerate(text.splitlines(), start=1)

