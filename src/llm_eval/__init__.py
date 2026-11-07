"""Shared model-access layer for the car-buying LLM evaluation."""

from llm_eval.config import load_model_registry
from llm_eval.models import ChatMessage, ChatResult, ModelRegistry, ModelSpec
from llm_eval.openai_compatible import OpenAICompatibleClient

__all__ = [
    "ChatMessage",
    "ChatResult",
    "ModelRegistry",
    "ModelSpec",
    "OpenAICompatibleClient",
    "load_model_registry",
]

