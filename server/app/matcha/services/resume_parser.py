"""Shared resume parsing helper.

Extracts plain text from a resume file (PDF/DOC/DOCX/TXT) via
ERDocumentParser, then runs a lightweight Gemini flash-lite structured
extraction to produce a ResumeCandidate-shaped dict. Used by:

- The matcha-work recruiting flow that uploads resumes to a thread/project.
- The new /users/me/resume endpoint that stores a profile-level resume.

Keeping the parser logic in one place ensures both surfaces produce the
same schema and eases future changes (e.g. adding phonetic name hints).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

from google import genai
from google.genai import types

from ...config import get_settings
from .er_document_parser import ERDocumentParser

logger = logging.getLogger(__name__)

RESUME_UPLOAD_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt"}
RESUME_UPLOAD_MAX_BYTES = 10 * 1024 * 1024
RESUME_TEXT_CAP = 15_000
RESUME_EXTRACT_MODEL = "gemini-3.1-flash-lite-preview"
RESUME_EXTRACT_TIMEOUT = 60

RESUME_EXTRACT_PROMPT = """Extract candidate information from this resume. Return ONLY valid JSON with these fields:
{"name":"...","email":"...","phone":"...","location":"...","current_title":"...","experience_years":0,"skills":["..."],"education":"highest degree - school","certifications":["..."],"summary":"1-2 sentence professional summary","strengths":["top 3 strengths"],"flags":["any concerns or gaps"]}

Resume text:
---
%s
---"""


class ResumeParseError(Exception):
    """Raised when text extraction or structured parsing fails."""


async def extract_resume_text(raw: bytes, filename: str) -> str:
    """Run ERDocumentParser and return the extracted plain text."""
    parser = ERDocumentParser()
    text, _ = parser.extract_text_from_bytes(raw, filename)
    if not text or len(text.strip()) < 50:
        raise ResumeParseError(f"Extracted text too short for {filename}")
    return text


async def parse_resume_text(text: str) -> dict:
    """Run Gemini flash-lite structured extraction on an already-extracted
    resume text blob. Returns a ResumeCandidate-shaped dict.
    """
    settings = get_settings()
    api_key = os.getenv("GEMINI_API_KEY") or settings.gemini_api_key
    if not api_key:
        raise ResumeParseError("GEMINI_API_KEY not configured")
    client = genai.Client(api_key=api_key)
    capped = text[:RESUME_TEXT_CAP]
    try:
        resp = await asyncio.wait_for(
            asyncio.to_thread(
                lambda t=capped: client.models.generate_content(
                    model=RESUME_EXTRACT_MODEL,
                    contents=[
                        types.Content(
                            role="user",
                            parts=[types.Part.from_text(text=RESUME_EXTRACT_PROMPT % t)],
                        )
                    ],
                    config=types.GenerateContentConfig(temperature=0.1),
                )
            ),
            timeout=RESUME_EXTRACT_TIMEOUT,
        )
    except Exception as e:
        raise ResumeParseError(f"Gemini extraction call failed: {e}") from e

    raw_json = (resp.text or "").strip()
    if raw_json.startswith("```"):
        raw_json = raw_json.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise ResumeParseError(f"Gemini returned invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ResumeParseError("Gemini returned non-object payload")
    return data


async def parse_resume_file(
    raw: bytes, filename: str, content_type: Optional[str] = None
) -> tuple[dict, str]:
    """High-level helper: extract text + run structured extraction.

    Returns (parsed_data, raw_text). Raises ResumeParseError on any failure.
    The caller is responsible for enforcing extension/size limits (see the
    RESUME_UPLOAD_* constants above) and for uploading the raw file to
    storage if it wants to keep the original around.
    """
    text = await extract_resume_text(raw, filename)
    parsed = await parse_resume_text(text)
    return parsed, text
