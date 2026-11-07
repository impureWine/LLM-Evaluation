"""Shared model-access layer for the car-buying LLM evaluation."""

from llm_eval.config import load_model_registry
from llm_eval.models import ChatMessage, ChatResult, ModelRegistry, ModelSpec
from llm_eval.openai_compatible import OpenAICompatibleClient
from llm_eval.prompts import PromptBundle
from llm_eval.structured import SchemaValidatedDecisionClient

__all__ = [
    "ChatMessage",
    "ChatResult",
    "ModelRegistry",
    "ModelSpec",
    "OpenAICompatibleClient",
    "PromptBundle",
    "SchemaValidatedDecisionClient",
    "load_model_registry",
]

