"""Lazy OpenAI client factory. Credentials remain server-side only."""
from openai import OpenAI

from odei_api.config import get_settings


class ModelConfigurationError(RuntimeError):
    """Raised when model configuration is missing."""


def get_openai_client() -> tuple[OpenAI, str]:
    settings = get_settings()
    if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value():
        raise ModelConfigurationError("OPENAI_API_KEY is not configured")
    if settings.openai_model is None or not settings.openai_model.strip():
        raise ModelConfigurationError("ODEI_MODEL is not configured")
    return (
        OpenAI(api_key=settings.openai_api_key.get_secret_value()),
        settings.openai_model.strip(),
    )
