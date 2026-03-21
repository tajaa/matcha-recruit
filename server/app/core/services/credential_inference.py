"""Infer required healthcare credentials from job title.

Uses a static mapping for common roles with a Gemini fallback for
unrecognized titles.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

VALID_DOCUMENT_TYPES = [
    "medical_license",
    "dea",
    "npi",
    "board_cert",
    "malpractice",
    "health_clearance",
]

DOCUMENT_TYPE_LABELS = {
    "medical_license": "Professional License",
    "dea": "DEA Registration",
    "npi": "NPI Verification",
    "board_cert": "Board Certification",
    "malpractice": "Malpractice Insurance",
    "health_clearance": "Health Clearance (BLS/TB/Immunizations)",
}


@dataclass
class CredentialRequirement:
    document_type: str
    label: str
    is_required: bool = True


# ── Static mapping ──────────────────────────────────────────────────────────
# Each entry: (pattern, [document_types])
# Patterns are matched case-insensitively against the full job title.
# Order matters — first match wins.

_ROLE_PATTERNS: list[tuple[re.Pattern, list[str]]] = [
    # Physicians
    (re.compile(r"\b(physician|doctor|md|m\.d\.|do|d\.o\.|attending|hospitalist|surgeon)\b", re.I),
     ["medical_license", "dea", "npi", "board_cert", "malpractice", "health_clearance"]),

    # Psychiatrist (physician + behavioral)
    (re.compile(r"\bpsychiatrist\b", re.I),
     ["medical_license", "dea", "npi", "board_cert", "malpractice", "health_clearance"]),

    # Dentist
    (re.compile(r"\b(dentist|dds|dmd|oral surgeon)\b", re.I),
     ["medical_license", "dea", "npi", "board_cert", "malpractice", "health_clearance"]),

    # Nurse Practitioner / APRN / CRNA
    (re.compile(r"\b(nurse practitioner|aprn|crna|cnm|np)\b", re.I),
     ["medical_license", "dea", "npi", "board_cert", "malpractice", "health_clearance"]),

    # Physician Assistant
    (re.compile(r"\b(physician assistant|pa-c|pa)\b", re.I),
     ["medical_license", "npi", "board_cert", "health_clearance"]),

    # Pharmacist
    (re.compile(r"\bpharmacist\b", re.I),
     ["medical_license", "dea", "npi", "health_clearance"]),

    # Registered Nurse
    (re.compile(r"\b(registered nurse|rn|charge nurse|nurse manager|staff nurse)\b", re.I),
     ["medical_license", "npi", "health_clearance"]),

    # Licensed Practical / Vocational Nurse
    (re.compile(r"\b(lpn|lvn|licensed practical nurse|licensed vocational nurse)\b", re.I),
     ["medical_license", "health_clearance"]),

    # Therapists (PT, OT, SLP, RT)
    (re.compile(r"\b(physical therapist|occupational therapist|speech.{0,10}pathologist|respiratory therapist|pt|ot|slp|ccc-slp)\b", re.I),
     ["medical_license", "npi", "health_clearance"]),

    # Psychologist
    (re.compile(r"\bpsychologist\b", re.I),
     ["medical_license", "npi", "malpractice", "health_clearance"]),

    # Licensed Clinical Social Worker / Counselor
    (re.compile(r"\b(lcsw|lmft|lpc|licensed.{0,15}(social worker|counselor|therapist))\b", re.I),
     ["medical_license", "npi", "health_clearance"]),

    # Behavioral Health Technician / Counselor (non-licensed)
    (re.compile(r"\b(behavioral.{0,10}(tech|specialist)|counselor|case manager)\b", re.I),
     ["health_clearance"]),

    # CNA / Medical Assistant
    (re.compile(r"\b(cna|certified nursing assistant|medical assistant|patient care tech|pct)\b", re.I),
     ["medical_license", "health_clearance"]),

    # Pharmacy Technician
    (re.compile(r"\bpharmacy tech", re.I),
     ["medical_license", "health_clearance"]),

    # Radiology / Lab Tech
    (re.compile(r"\b(radiology|x-ray|imaging|lab|laboratory|phlebotom|sonograph|ultrasound)\b.*\b(tech|specialist|scientist)\b", re.I),
     ["medical_license", "health_clearance"]),

    # Paramedic / EMT
    (re.compile(r"\b(paramedic|emt|emergency medical tech)\b", re.I),
     ["medical_license", "health_clearance"]),

    # Dietitian / Nutritionist
    (re.compile(r"\b(dietitian|dietician|nutritionist|rd)\b", re.I),
     ["medical_license", "npi", "health_clearance"]),
]

# Titles that are explicitly non-clinical — skip credential inference entirely
_NON_CLINICAL_PATTERNS = re.compile(
    r"\b(admin|administrator|receptionist|front desk|billing|coder|"
    r"medical records|scheduler|hr|human resources|it |information tech|"
    r"marketing|sales|finance|accounting|executive|director of operations|"
    r"office manager|practice manager|compliance officer|ceo|cfo|coo|cto)\b",
    re.I,
)


def infer_from_static(job_title: str) -> Optional[list[CredentialRequirement]]:
    """Try to match job_title against known healthcare role patterns.

    Returns None if no match (caller should try Gemini fallback).
    Returns an empty list for explicitly non-clinical roles.
    """
    if not job_title or not job_title.strip():
        return None

    title = job_title.strip()

    # Check non-clinical first
    if _NON_CLINICAL_PATTERNS.search(title):
        return []

    for pattern, doc_types in _ROLE_PATTERNS:
        if pattern.search(title):
            return [
                CredentialRequirement(
                    document_type=dt,
                    label=DOCUMENT_TYPE_LABELS.get(dt, dt),
                )
                for dt in doc_types
            ]

    return None  # No match — try Gemini


async def infer_from_gemini(job_title: str) -> list[CredentialRequirement]:
    """Use Gemini to determine required credentials for an unrecognized job title."""
    try:
        from google import genai
        from google.genai import types

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY not set, cannot infer credentials for: %s", job_title)
            return []

        client = genai.Client(api_key=api_key)

        prompt = f"""You are a healthcare HR compliance expert. Given the job title below, determine which credential documents are typically required in the US healthcare industry.

Job title: "{job_title}"

Choose ONLY from these document types:
- medical_license: State professional license (nursing, medical, therapy, etc.)
- dea: DEA controlled substance registration
- npi: National Provider Identifier
- board_cert: Board certification in a specialty
- malpractice: Professional liability / malpractice insurance
- health_clearance: Health clearances (BLS/CPR, TB test, immunizations, flu shot)

If this is a NON-CLINICAL role (admin, billing, IT, etc.), return an empty array.

Return ONLY a JSON array of strings, e.g.: ["medical_license", "npi", "health_clearance"]
No markdown, no explanation — just the JSON array."""

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[types.Content(parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=256),
        )

        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:text.rfind("```")]
        text = text.strip()

        doc_types = json.loads(text)
        if not isinstance(doc_types, list):
            return []

        return [
            CredentialRequirement(
                document_type=dt,
                label=DOCUMENT_TYPE_LABELS.get(dt, dt),
            )
            for dt in doc_types
            if dt in VALID_DOCUMENT_TYPES
        ]

    except Exception as e:
        logger.error("Gemini credential inference failed for '%s': %s", job_title, e)
        return []


async def infer_credential_requirements(job_title: Optional[str]) -> list[CredentialRequirement]:
    """Infer required credentials for a job title using static mapping + Gemini fallback.

    Returns a list of CredentialRequirement objects. Empty list means no credentials needed.
    """
    if not job_title:
        return []

    # Try static mapping first
    result = infer_from_static(job_title)
    if result is not None:
        logger.info("Static credential match for '%s': %s", job_title, [r.document_type for r in result])
        return result

    # Fallback to Gemini
    logger.info("No static match for '%s', trying Gemini inference", job_title)
    result = await infer_from_gemini(job_title)
    logger.info("Gemini credential inference for '%s': %s", job_title, [r.document_type for r in result])
    return result
