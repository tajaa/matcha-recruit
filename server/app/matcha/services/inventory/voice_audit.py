"""Voice stock-count dictation — a manager walks the store dictating counts
("twelve boxes of gloves, six bags of espresso beans...") and one Gemini
multimodal call transcribes + extracts a count-per-item list. Best-effort,
never raises — returns a draft the Audit sheet REVIEWS and merges before
saving (this module writes nothing; the caller's commit_audit_lines is the
only writer). Audio arrives as WAV (browser assembles it from the PCM
worklet — Gemini's audio understanding accepts WAV, not the webm/opus
MediaRecorder defaults to).

Mirrors ir_voice_parser.py's audio-part/JSON-mode/retry wrapper, combined
with extraction.py's known-item-names grounding trick (the direct analogue
of IR voice's location_options closed set) so the model reuses an exact
catalog name instead of inventing near-duplicates.
"""

import asyncio
import json
import logging
from typing import Optional

from google.genai import types

from app.core.services.model_catalog import GEMINI_FLASH
from app.matcha.services._shared.gemini import genai_env_client
from app.matcha.services.inventory import movements as movements_service
from app.matcha.services.inventory.matching import best_match, normalize_name

logger = logging.getLogger(__name__)

VOICE_PARSE_TIMEOUT = 90
MAX_VOICE_LINES = 100
_MAX_NAME_CHARS = 200


def _build_prompt(item_names: list[str]) -> str:
    names = ", ".join(item_names) if item_names else "(none yet)"
    return f"""You are transcribing a store manager dictating physical stock counts while walking the store.

Known inventory items (reuse an EXACT name below when the speech clearly refers to it; otherwise use the spoken name as heard, title-case):
{names}

Return ONLY valid JSON matching this shape:
{{"transcript": "<full verbatim transcription of the audio>",
 "lines": [{{"item_name": "...", "quantity": <number>, "unit": "<spoken unit like boxes/bags, or null>"}}]}}

Rules:
- One line per distinct item counted. "twelve boxes of gloves" -> {{"item_name": "Gloves", "quantity": 12, "unit": "boxes"}}.
- quantity is the TOTAL count stated for that item; convert number words to digits.
- Skip anything that is not a count of a stock item (asides, questions). Never invent an item or a number that was not spoken.
- If the same item is counted twice, keep only the LAST count (a correction).

Do not include markdown fences."""


def _parse_model_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


def _coerce_voice_counts(raw: dict) -> dict:
    """Validate/clamp the model output. PURE (unit-tested). Never raises;
    always returns the full canonical shape."""
    if not isinstance(raw, dict):
        raw = {}
    transcript = raw.get("transcript")
    transcript = transcript.strip() if isinstance(transcript, str) and transcript.strip() else None

    lines = []
    for entry in (raw.get("lines") or [])[:MAX_VOICE_LINES]:
        if not isinstance(entry, dict):
            continue
        name = entry.get("item_name")
        name = name.strip() if isinstance(name, str) else ""
        if not name:
            continue
        name = name[:_MAX_NAME_CHARS]

        quantity = entry.get("quantity")
        if not isinstance(quantity, (int, float)) or isinstance(quantity, bool) or quantity < 0:
            continue

        unit = entry.get("unit")
        unit = unit.strip() if isinstance(unit, str) and unit.strip() else None

        lines.append({"item_name": name, "quantity": float(quantity), "unit": unit})

    return {"transcript": transcript, "lines": lines}


async def parse_voice_counts(audio_bytes: bytes, mime_type: str, *, item_names: list[str]) -> dict:
    """Gemini transcribes + extracts count lines from spoken audio, with one
    retry (fresh timeout) on a transient timeout or unparsable JSON
    response. Never raises. ``available`` reflects whether the model call
    itself succeeded (a clean transcript with zero counted items is still
    "available" — the UI tells that apart from a hard failure via
    ``lines``); it is False only when Gemini never returned a usable
    response, so the UI falls back to manual entry."""
    client = genai_env_client()
    part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
    prompt = _build_prompt(item_names)
    config = types.GenerateContentConfig(
        temperature=0.2,
        response_mime_type="application/json",
    )

    payload: dict = {}
    succeeded = False
    for attempt in range(1, 3):  # one retry on timeout / bad JSON
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=GEMINI_FLASH, contents=[prompt, part], config=config,
                ),
                timeout=VOICE_PARSE_TIMEOUT,
            )
            raw = (getattr(response, "text", None) or "").strip()
            payload = _parse_model_json(raw)
            succeeded = True
            break
        except (asyncio.TimeoutError, json.JSONDecodeError) as exc:
            if attempt == 2:
                logger.warning("inventory voice parse failed (attempt %d/2): %s", attempt, exc)
        except Exception as exc:  # never-raises contract — anything else, no retry
            logger.warning("inventory voice parse failed (attempt %d/2): %s", attempt, exc)
            break

    result = _coerce_voice_counts(payload)
    result["available"] = succeeded
    result["model"] = GEMINI_FLASH
    return result


async def resolve_count_lines(
    conn, *, company_id, location_id: Optional[str], lines: list[dict],
    existing: Optional[list[dict]] = None,
) -> list[dict]:
    """Read-only. Attaches an item match to each parsed line via the same
    fuzzy engine the receipts flow uses (matching.best_match) — no order
    claiming here, unlike receipts.resolve_lines, since an audit line isn't
    tied to an order. Pass `existing` (list_item_names' own return shape)
    when the caller already fetched the catalog for the same
    company/location — skips a redundant full-table SELECT."""
    if existing is None:
        existing = await movements_service.list_item_names(conn, company_id, location_id)
    out = []
    for line in lines:
        match = best_match(line["item_name"], existing)
        out.append({
            **line,
            "item_id": str(match["id"]) if match else None,
            "matched_name": match["name"] if match else None,
            "exact": bool(match) and match["normalized_name"] == normalize_name(line["item_name"]),
        })
    return out
