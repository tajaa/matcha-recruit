"""Central Google GenAI client factory.

Returns a ``google.genai`` Client wired to either the consumer AI Studio
endpoint (API key) or **Vertex AI** (BAA-eligible). The consumer endpoint is
NOT covered by a Google BAA, so PHI-bearing prompts (incident narratives that
can name patients) are an impermissible disclosure there. Flip
``USE_VERTEX_AI=true`` once a GCP project + signed Google Cloud BAA are in place
and PHI-bearing analysis moves to the covered endpoint.

Default (``USE_VERTEX_AI`` unset/false) preserves today's consumer behavior, so
this factory is a no-op drop-in until the BAA lands.
"""
from typing import Optional

from google import genai

from app.config import get_settings
from app.core.services.ai_usage import wrap_client


def get_genai_client(api_key: Optional[str] = None, **kwargs) -> genai.Client:
    """Build a ``genai.Client`` for the configured backend.

    * Vertex (``USE_VERTEX_AI=true``): IAM/ADC auth + ``project``/``location`` —
      the BAA-covered endpoint. ``api_key`` is ignored.
    * Consumer (default): API-key auth against ``generativelanguage.googleapis.com``.

    The returned client is wrapped (see ``ai_usage.wrap_client``) so every
    generate_content/embed_content call — sync, async, or streaming — is
    logged to ``ai_usage_log`` with zero changes at any call site. The
    ``-> genai.Client`` annotation stays nominal: nothing in the codebase
    isinstance-checks this return value, only type-annotates it.
    """
    settings = get_settings()
    if getattr(settings, "use_vertex_ai", False):
        return wrap_client(genai.Client(
            vertexai=True,
            project=settings.vertex_ai_project,
            location=settings.vertex_ai_location,
            **kwargs,
        ))
    return wrap_client(genai.Client(api_key=api_key or settings.gemini_api_key, **kwargs))
