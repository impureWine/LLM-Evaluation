"""Factory helpers for configured model clients."""

from __future__ import annotations

from typing import Iterable, List

from llm_eval.config import load_model_registry
from llm_eval.models import ModelSpec
from llm_eval.openai_compatible import OpenAICompatibleClient


def selected_models(keys: Iterable[str]) -> List[ModelSpec]:
    registry = load_model_registry()
    return [registry.get(key) for key in keys]


def build_client() -> OpenAICompatibleClient:
    return OpenAICompatibleClient()

