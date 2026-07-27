"""Shared Gemini client cache + model-unavailability check. Leaf module:
imports nothing from services/.
"""
from app.core.services.genai_client import get_genai_client

_client = None


def _genai():
    global _client
    if _client is None:
        _client = get_genai_client()
    return _client


def is_model_unavailable_error(error: Exception) -> bool:
    """Return True when the model is unavailable for the current account/project."""
    message = str(error).lower()
    if "model" not in message:
        return False
    return (
        "not found" in message
        or "does not have access" in message
        or "unsupported model" in message
        or "404" in message
    )
