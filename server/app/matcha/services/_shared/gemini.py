"""Shared Gemini client cache + model-unavailability check. Leaf module:
imports nothing from services/.
"""
import os

from app.config import get_settings
from app.core.services.genai_client import get_genai_client

_client = None


def _genai():
    global _client
    if _client is None:
        _client = get_genai_client()
    return _client


_env_client = None


def genai_env_client():
    """Module-cached client for the one-shot Gemini services (EMS intake/ask,
    schedule chat, task summary, thread title, ticket drafts, commit scan).

    Unlike `_genai()`, prefers the GEMINI_API_KEY env var over
    settings.gemini_api_key (which loads from LIVE_API) — the exact pattern
    every one-shot service carried as its own private `_get_client()` copy
    before 2026-07-31. Prod .env.backend sets BOTH vars and they are not
    guaranteed to be the same key, so the lookup order is load-bearing.
    """
    global _env_client
    if _env_client is None:
        settings = get_settings()
        _env_client = get_genai_client(api_key=os.getenv("GEMINI_API_KEY") or settings.gemini_api_key)
    return _env_client


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
