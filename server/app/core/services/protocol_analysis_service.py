"""Protocol Gap Analysis Service.

Compares a protocol/study document against regulatory requirements
using Gemini AI to identify covered, partially covered, and missing
requirements.
"""

import asyncio
import json
import logging
from typing import Any, Optional
from uuid import UUID

from google import genai

from ...config import get_settings

logger = logging.getLogger(__name__)

GEMINI_CALL_TIMEOUT = 60  # seconds — protocol analysis may be longer than typical calls

PROTOCOL_ANALYSIS_PROMPT = """You are a regulatory compliance analyst. You have been given a protocol document and a set of regulatory requirements. Your job is to determine how well the protocol addresses each requirement.

PROTOCOL DOCUMENT:
{protocol_text}

{company_context}

REGULATORY REQUIREMENTS:
{requirements_text}

For each requirement, determine one of three statuses:
- "covered": The protocol explicitly addresses this requirement. Quote the relevant section or language.
- "partial": The protocol touches on this requirement but is incomplete or vague. Explain what is present and what is missing.
- "gap": The protocol does not address this requirement at all. Provide brief guidance on what should be added.

Return ONLY a JSON object with this exact structure (no markdown, no extra text):
{{
  "covered": [
    {{
      "requirement_key": "the_requirement_key",
      "title": "Requirement Title",
      "status": "covered",
      "evidence": "Quote or reference from the protocol that addresses this requirement"
    }}
  ],
  "partial": [
    {{
      "requirement_key": "the_requirement_key",
      "title": "Requirement Title",
      "status": "partial",
      "evidence": "What the protocol does address",
      "missing": "What is still missing or insufficient"
    }}
  ],
  "gaps": [
    {{
      "requirement_key": "the_requirement_key",
      "title": "Requirement Title",
      "status": "gap",
      "guidance": "Brief description of what the protocol should include to satisfy this requirement"
    }}
  ],
  "summary": "Protocol covers X of Y applicable requirements. N critical gaps identified. Brief overall assessment."
}}

Be thorough but concise. Every requirement must appear in exactly one of the three arrays."""


def _build_requirements_text(requirements: list[dict]) -> str:
    """Format requirements into a numbered text block for the prompt."""
    lines = []
    for i, req in enumerate(requirements, 1):
        parts = [f"{i}. [{req.get('requirement_key', req.get('category', 'unknown'))}]"]
        parts.append(f"Title: {req.get('title', 'Untitled')}")
        if req.get("description"):
            parts.append(f"   Description: {req['description']}")
        if req.get("current_value"):
            parts.append(f"   Current Value: {req['current_value']}")
        if req.get("jurisdiction_level") or req.get("jurisdiction_name"):
            jl = req.get("jurisdiction_level", "")
            jn = req.get("jurisdiction_name", "")
            parts.append(f"   Jurisdiction: {jl} — {jn}")
        if req.get("category"):
            parts.append(f"   Category: {req['category']}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


def _parse_json_response(text: str) -> dict[str, Any]:
    """Parse JSON from Gemini response, stripping markdown fences if present."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())


def _validate_analysis_result(result: dict) -> Optional[str]:
    """Validate the structure of the analysis result. Returns error message or None."""
    for key in ("covered", "gaps", "partial"):
        if not isinstance(result.get(key), list):
            return f"Missing or invalid '{key}': must be a list"

    if not result.get("summary"):
        return "Missing required field: summary"

    # Validate individual entries have required fields
    for item in result.get("covered", []):
        if not item.get("requirement_key") or not item.get("title"):
            return "covered item missing requirement_key or title"
        if not item.get("evidence"):
            return "covered item missing evidence"

    for item in result.get("gaps", []):
        if not item.get("requirement_key") or not item.get("title"):
            return "gaps item missing requirement_key or title"
        if not item.get("guidance"):
            return "gaps item missing guidance"

    for item in result.get("partial", []):
        if not item.get("requirement_key") or not item.get("title"):
            return "partial item missing requirement_key or title"

    return None


async def analyze_protocol(
    protocol_text: str,
    requirements: list[dict],
    company_context: Optional[str] = None,
) -> dict[str, Any]:
    """
    Analyze a protocol document against regulatory requirements using Gemini.

    Args:
        protocol_text: The protocol/study document text to analyze.
        requirements: List of requirement dicts with keys like
            requirement_key, title, description, category, current_value,
            jurisdiction_level, jurisdiction_name.
        company_context: Optional string with company/industry context.

    Returns:
        Dict with covered[], gaps[], partial[], and summary string.

    Raises:
        ValueError: If inputs are invalid.
        RuntimeError: If Gemini call fails after retries.
    """
    if not protocol_text or not protocol_text.strip():
        raise ValueError("protocol_text is required")

    if not requirements:
        return {
            "covered": [],
            "gaps": [],
            "partial": [],
            "summary": "No applicable requirements found to analyze against.",
        }

    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("Gemini API key not configured")

    client = genai.Client(api_key=settings.gemini_api_key)

    requirements_text = _build_requirements_text(requirements)
    context_section = (
        f"COMPANY/INDUSTRY CONTEXT:\n{company_context}" if company_context else ""
    )

    prompt = PROTOCOL_ANALYSIS_PROMPT.format(
        protocol_text=protocol_text[:50000],  # Cap at ~50k chars to stay within limits
        requirements_text=requirements_text,
        company_context=context_section,
    )

    # Try gemini-2.5-flash first, fall back to gemini-2.0-flash
    models = ["gemini-2.5-flash", "gemini-2.0-flash"]
    last_error = None

    for model_name in models:
        for attempt in range(2):  # 1 initial + 1 retry per model
            try:
                retry_feedback = ""
                if attempt > 0 and last_error:
                    retry_feedback = (
                        f"\n\nPREVIOUS ATTEMPT FAILED: {last_error}. "
                        "Please return ONLY valid JSON with the exact structure requested."
                    )

                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model_name,
                        contents=prompt + retry_feedback,
                    ),
                    timeout=GEMINI_CALL_TIMEOUT,
                )

                result = _parse_json_response(response.text)

                validation_error = _validate_analysis_result(result)
                if validation_error:
                    last_error = f"Validation failed: {validation_error}"
                    logger.warning(
                        "Protocol analysis validation error (model=%s, attempt=%d): %s",
                        model_name, attempt + 1, validation_error,
                    )
                    continue

                # Ensure status fields are set
                for item in result.get("covered", []):
                    item.setdefault("status", "covered")
                for item in result.get("gaps", []):
                    item.setdefault("status", "gap")
                for item in result.get("partial", []):
                    item.setdefault("status", "partial")

                result["model_used"] = model_name
                result["requirements_analyzed"] = len(requirements)
                return result

            except asyncio.TimeoutError:
                last_error = f"Timed out after {GEMINI_CALL_TIMEOUT}s"
                logger.warning(
                    "Protocol analysis timeout (model=%s, attempt=%d)",
                    model_name, attempt + 1,
                )
            except json.JSONDecodeError as e:
                last_error = f"JSON parse error: {e}"
                logger.warning(
                    "Protocol analysis JSON error (model=%s, attempt=%d): %s",
                    model_name, attempt + 1, e,
                )
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.warning(
                    "Protocol analysis error (model=%s, attempt=%d): %s",
                    model_name, attempt + 1, e,
                )
                # If it's a model-level error (not timeout/parse), skip to next model
                break

    raise RuntimeError(
        f"Protocol analysis failed after trying all models. Last error: {last_error}"
    )
