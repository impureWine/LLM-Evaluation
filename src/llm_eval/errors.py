"""Typed errors used by the model-access layer."""


class LLMEvaluationError(Exception):
    """Base class for expected evaluation errors."""


class ConfigurationError(LLMEvaluationError):
    """The model registry or local configuration is invalid."""


class AuthenticationConfigurationError(ConfigurationError):
    """The required API-key environment variable is missing."""


class TransportError(LLMEvaluationError):
    """A network request failed before a usable HTTP response was returned."""


class ModelAPIError(LLMEvaluationError):
    """The model service returned a non-successful response."""

    def __init__(self, message, status_code=None, response_excerpt=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_excerpt = response_excerpt


class InvalidModelResponse(LLMEvaluationError):
    """The provider returned JSON that does not match the chat contract."""

