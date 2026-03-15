"""Gemini Vision extraction for healthcare credential documents.

Sends document images/PDFs to Gemini and extracts structured credential
data (license numbers, expiration dates, etc.) with confidence scores.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from google import genai
from google.genai import types

from ...config import get_settings

logger = logging.getLogger(__name__)

EXTRACTION_MODEL = "gemini-2.0-flash"

# Mapping from document_type to the fields we want to extract
EXTRACTION_FIELDS: dict[str, list[dict[str, str]]] = {
    "medical_license": [
        {"field": "license_type", "description": "Type of medical license (e.g. MD, DO, RN, NP, PA, LPN, APRN)"},
        {"field": "license_number", "description": "The license number"},
        {"field": "license_state", "description": "Two-letter state abbreviation where the license was issued"},
        {"field": "license_expiration", "description": "Expiration date in YYYY-MM-DD format"},
        {"field": "holder_name", "description": "Full name of the license holder"},
    ],
    "dea": [
        {"field": "dea_number", "description": "DEA registration number"},
        {"field": "dea_expiration", "description": "Expiration date in YYYY-MM-DD format"},
        {"field": "holder_name", "description": "Full name of the registrant"},
        {"field": "schedules", "description": "Comma-separated controlled substance schedules authorized"},
    ],
    "npi": [
        {"field": "npi_number", "description": "10-digit National Provider Identifier number"},
        {"field": "holder_name", "description": "Full name of the provider"},
        {"field": "taxonomy", "description": "Provider taxonomy/specialty code"},
    ],
    "board_cert": [
        {"field": "board_certification", "description": "Name of the board certification"},
        {"field": "board_certification_expiration", "description": "Expiration date in YYYY-MM-DD format"},
        {"field": "specialty", "description": "Medical specialty"},
        {"field": "certifying_body", "description": "Name of the certifying organization"},
        {"field": "holder_name", "description": "Full name of the certificate holder"},
    ],
    "malpractice": [
        {"field": "malpractice_carrier", "description": "Insurance carrier/company name"},
        {"field": "malpractice_policy_number", "description": "Policy number"},
        {"field": "malpractice_expiration", "description": "Policy expiration date in YYYY-MM-DD format"},
        {"field": "coverage_amount", "description": "Coverage amount (e.g. $1M/$3M)"},
        {"field": "holder_name", "description": "Full name of the insured"},
    ],
    "health_clearance": [
        {"field": "clearance_type", "description": "Type of clearance (CPR, BLS, ACLS, TB_test, Hep_B, flu_shot, or other)"},
        {"field": "expiration", "description": "Expiration date in YYYY-MM-DD format, if applicable"},
        {"field": "issuing_org", "description": "Organization that issued the clearance"},
        {"field": "holder_name", "description": "Full name of the person"},
    ],
    "other": [
        {"field": "document_title", "description": "Title or type of the document"},
        {"field": "holder_name", "description": "Name of the person the document belongs to"},
        {"field": "expiration", "description": "Expiration date in YYYY-MM-DD format, if applicable"},
        {"field": "key_details", "description": "Any other important details found in the document"},
    ],
}


def _get_client() -> genai.Client:
    settings = get_settings()
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key)
    elif settings.use_vertex:
        return genai.Client(
            vertexai=True,
            project=settings.vertex_project,
            location=settings.vertex_location,
        )
    else:
        return genai.Client(api_key=settings.gemini_api_key)


def _build_prompt(document_type: str) -> str:
    fields = EXTRACTION_FIELDS.get(document_type, EXTRACTION_FIELDS["other"])
    field_descriptions = "\n".join(
        f'  - "{f["field"]}": {f["description"]}'
        for f in fields
    )

    return f"""You are a healthcare credential document extraction system.
Analyze this document and extract the following fields. Return ONLY valid JSON.

Fields to extract:
{field_descriptions}

For each field, return:
- "value": the extracted value (string or null if not found)
- "confidence": a number 0.0-1.0 indicating how confident you are

Return format:
{{
  "fields": {{
    "<field_name>": {{ "value": "<extracted_value>", "confidence": 0.95 }},
    ...
  }},
  "document_description": "Brief description of what this document is"
}}

If a date is found but in a different format, convert it to YYYY-MM-DD.
If a field is not present in the document, set value to null and confidence to 0.0.
Return ONLY the JSON object, no markdown or extra text."""


async def extract_credential_info(
    file_bytes: bytes,
    mime_type: str,
    document_type: str,
) -> dict[str, Any]:
    """Extract credential information from a document using Gemini Vision.

    Returns a dict with 'fields' (extracted data with confidence scores)
    and 'document_description'.
    """
    client = _get_client()
    prompt = _build_prompt(document_type)

    # Build the content parts: document + prompt
    file_part = types.Part.from_bytes(data=file_bytes, mime_type=mime_type)
    text_part = types.Part.from_text(text=prompt)

    try:
        response = client.models.generate_content(
            model=EXTRACTION_MODEL,
            contents=[types.Content(parts=[file_part, text_part])],
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=2048,
            ),
        )

        # Parse the JSON response
        text = response.text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[: text.rfind("```")]
        text = text.strip()

        result = json.loads(text)
        return result

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini extraction response: {e}")
        return {
            "fields": {},
            "error": "Failed to parse extraction result",
            "raw_response": response.text[:500] if response else None,
        }
    except Exception as e:
        logger.error(f"Gemini extraction failed: {e}")
        return {
            "fields": {},
            "error": str(e),
        }
