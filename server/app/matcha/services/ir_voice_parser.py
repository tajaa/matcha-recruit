"""Voice incident-intake parse — Gemini transcribes a spoken incident report and
extracts the create-form fields in one multimodal call (plus one retry on a
timeout or bad JSON response), so a reporter can "talk it in" instead of typing.

Mirrors ``wc_mod_parser`` / ``loss_run_parser``: a cached IRAnalyzer, the audio sent
to Gemini as an inline part, JSON parsed back into the IR create-form shape.
Best-effort, never raises — returns a prefill the user REVIEWS and edits before
submitting (it does NOT create the incident). Audio is uploaded as WAV (the browser
assembles it from the PCM worklet; Gemini's audio understanding accepts WAV but not
the webm/opus that MediaRecorder defaults to).
"""

import asyncio
import json
import logging
from typing import Optional

from google.genai import types

from app.config import get_settings
from app.matcha.services.ir_analysis import IRAnalyzer, VALID_INCIDENT_TYPES, VALID_SEVERITIES

logger = logging.getLogger(__name__)

_analyzer: Optional[IRAnalyzer] = None
VOICE_PARSE_TIMEOUT = 90       # audio can run longer than a PDF parse
MAX_WITNESSES = 20

_TYPE_DEFS = (
    "safety = injury / illness / unsafe condition; "
    "behavioral = harassment / misconduct / policy violation between people; "
    "property = damage to assets / equipment; "
    "near_miss = no harm occurred but could have; "
    "other = none of the above"
)
_SEVERITY_DEFS = (
    "critical = fatality / hospitalization / imminent danger; "
    "high = significant injury or serious misconduct; "
    "medium = moderate / treatable; "
    "low = minor / first-aid"
)


def _get_analyzer() -> IRAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = IRAnalyzer(api_key=get_settings().gemini_api_key)
    return _analyzer


def _build_prompt(location_options: list[dict]) -> str:
    """location_options: [{"id": "<uuid>", "label": "Main Plant — Dallas, TX"}]."""
    loc_lines = "\n".join(f"- {o['id']}: {o['label']}" for o in location_options) or "(none on file)"
    return f"""You are helping log a workplace incident report. The attached audio is a person verbally describing an incident. Transcribe it, then extract the structured fields.

Return ONLY valid JSON with exactly these keys (use null / [] for anything not clearly stated — never invent names, locations, or facts not spoken):
{{"transcript": "<full verbatim transcription of the audio>",
 "description": "<a clear written description of WHAT HAPPENED, in third person, from the narration>",
 "reported_by_name": "<the speaker's / reporter's name if stated, else null>",
 "occurred_at_text": "<when it happened, in the words spoken, e.g. 'yesterday around 3pm' or 'May 1 at 9am', else null>",
 "witnesses": [{{"name": "<a person named as a witness or other-involved, NOT the reporter>"}}],
 "location_id": "<the id of the BEST-matching location from the list below, or null if none clearly matches>",
 "incident_type": "<one of: safety, behavioral, property, near_miss, other — or null>",
 "severity": "<one of: critical, high, medium, low — or null>"}}

Incident types: {_TYPE_DEFS}.
Severity: {_SEVERITY_DEFS}.

Locations (return location_id as the matching id, never a made-up id):
{loc_lines}

Do not include markdown fences. Use null for unknowns; do not guess a location or a severity that wasn't implied."""


def _coerce_voice_fields(
    raw: dict,
    valid_location_ids: set,
    valid_types: set,
    valid_severities: set,
) -> dict:
    """Validate/clamp the model output into the safe prefill shape. PURE (unit-tested).

    Drops a location_id not in the company's set (defense vs a hallucinated/cross-tenant
    id), invalid enums, empty/whitespace strings, and caps witnesses. Always returns the
    full canonical dict; never raises."""
    def _str(k):
        v = raw.get(k)
        return v.strip() if isinstance(v, str) and v.strip() else None

    loc = raw.get("location_id")
    loc = str(loc) if loc is not None and str(loc) in valid_location_ids else None

    itype = raw.get("incident_type")
    itype = itype if isinstance(itype, str) and itype in valid_types else None
    sev = raw.get("severity")
    sev = sev if isinstance(sev, str) and sev in valid_severities else None

    witnesses = []
    for w in (raw.get("witnesses") or [])[:MAX_WITNESSES]:
        name = None
        if isinstance(w, str):
            name = w.strip()
        elif isinstance(w, dict):
            n = w.get("name")
            name = n.strip() if isinstance(n, str) else None
        if name:
            witnesses.append({"name": name})

    return {
        "transcript": _str("transcript"),
        "description": _str("description"),
        "reported_by_name": _str("reported_by_name"),
        "occurred_at_text": _str("occurred_at_text"),
        "witnesses": witnesses,
        "location_id": loc,
        "incident_type": itype,
        "severity": sev,
    }


# Incident narrations legitimately describe violence, harassment, injury, and
# similar — Gemini's default safety thresholds can block the response outright on
# exactly the audio we most need transcribed, which looks to the reporter like
# "couldn't understand the audio". This is a bounded, purpose-built extraction
# (not open-ended generation), so blocking is disabled for the categories a
# workplace-incident account would plausibly trip.
_VOICE_PARSE_SAFETY_SETTINGS = [
    types.SafetySetting(category=category, threshold=types.HarmBlockThreshold.BLOCK_NONE)
    for category in (
        types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
    )
]


async def parse_voice_incident(audio_bytes: bytes, mime_type: str, *, location_options: list[dict]) -> dict:
    """Gemini transcribes + extracts the create-form fields from spoken audio, with
    one retry (fresh timeout) on a transient timeout or unparsable JSON response.
    Never raises. ``available`` is False (with empty fields) on any failure so the
    UI can fall back to manual entry."""
    analyzer = _get_analyzer()
    valid_loc_ids = {str(o["id"]) for o in location_options}
    part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
    prompt = _build_prompt(location_options)
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        safety_settings=_VOICE_PARSE_SAFETY_SETTINGS,
    )

    payload: dict = {}
    for attempt in range(1, 3):  # one retry on timeout / bad JSON
        try:
            response = await asyncio.wait_for(
                analyzer.client.aio.models.generate_content(
                    model=analyzer.model, contents=[prompt, part], config=config,
                ),
                timeout=VOICE_PARSE_TIMEOUT,
            )
            raw = (getattr(response, "text", None) or "").strip()
            payload = analyzer._parse_json_response(raw) or {}
            break
        except (asyncio.TimeoutError, json.JSONDecodeError) as exc:
            if attempt == 2:
                logger.warning("IR voice parse failed (attempt %d/2): %s", attempt, exc)
        except Exception as exc:  # never-raises contract — anything else, no retry
            logger.warning("IR voice parse failed (attempt %d/2): %s", attempt, exc)
            break
    fields = _coerce_voice_fields(payload, valid_loc_ids, VALID_INCIDENT_TYPES, VALID_SEVERITIES)
    fields["available"] = bool(fields.get("description") or fields.get("transcript"))
    fields["model"] = analyzer.model
    return fields
