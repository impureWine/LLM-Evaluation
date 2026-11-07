"""Load and validate the versioned model registry."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Optional

from llm_eval.errors import ConfigurationError
from llm_eval.models import ModelRegistry, ModelSpec


SECRET_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_registry_path() -> Path:
    return project_root() / "configs" / "models.json"


def load_model_registry(path: Optional[Path] = None) -> ModelRegistry:
    registry_path = Path(path) if path else default_registry_path()
    if not registry_path.exists():
        raise ConfigurationError("Model registry does not exist: {}".format(registry_path))

    text = registry_path.read_text(encoding="utf-8")
    if SECRET_PATTERN.search(text):
        raise ConfigurationError(
            "A credential-like value appears in {}. Use environment variables instead.".format(
                registry_path
            )
        )

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            "Invalid JSON in {}: {}".format(registry_path, exc)
        ) from exc

    if data.get("schema_version") != 1:
        raise ConfigurationError("Unsupported model registry schema version")

    shared_parameters = data.get("shared_parameters") or {}
    entries = data.get("models") or []
    if not isinstance(entries, list) or len(entries) < 2:
        raise ConfigurationError("The registry must contain at least two model entries")

    models = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ConfigurationError("Each model entry must be a JSON object")
        spec = ModelSpec.from_mapping(entry, shared_parameters)
        if spec.key in models:
            raise ConfigurationError("Duplicate model key: {}".format(spec.key))
        models[spec.key] = spec

    model_ids = [spec.model_id for spec in models.values()]
    if len(set(model_ids)) < 2:
        raise ConfigurationError("At least two distinct model identifiers are required")

    return ModelRegistry(
        platform=str(data.get("platform", "")),
        recorded_on=str(data.get("recorded_on", "")),
        shared_parameters=dict(shared_parameters),
        models=models,
    )


def registry_as_public_dict(registry: ModelRegistry) -> Mapping[str, Any]:
    """Return registry data suitable for documentation and logs (no credentials)."""
    return {
        "platform": registry.platform,
        "recorded_on": registry.recorded_on,
        "shared_parameters": registry.shared_parameters,
        "models": [
            {
                "key": spec.key,
                "display_name": spec.display_name,
                "role": spec.role,
                "model_id": spec.model_id,
                "provider": spec.provider,
                "endpoint": spec.endpoint,
                "api_key_env": spec.api_key_env,
                "timeout_seconds": spec.timeout_seconds,
                "max_retries": spec.max_retries,
                "enabled": spec.enabled,
                "parameters": spec.parameters,
                "notes": spec.notes,
            }
            for spec in registry.ordered()
        ],
    }

