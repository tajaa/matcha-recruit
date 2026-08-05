"""One-shot Gemini extraction for an inventory-classified channel message.
Mirrors services/ems/event_intake.py:classify_event's call shape exactly:
never raises, takes no conn, returns the uncategorized/non-actionable
fallback shape on any failure so the caller can delegate to EMS intake."""

import json
import logging
import re

from google.genai import types

from app.core.services.model_catalog import GEMINI_FLASH_LITE
from app.matcha.services._shared.gemini import genai_env_client as _get_client

logger = logging.getLogger(__name__)

FLASH_LITE_MODEL = GEMINI_FLASH_LITE


_PROMPT_TEMPLATE = """You extract structured inventory data from a short channel message.

Known existing items (reuse an exact name below when the message clearly refers to one of them; otherwise propose a short, title-case new item name):
{item_names}

Message: "{content}"

Return ONLY JSON matching this shape:
{{
  "actionable": true or false,
  "kind": "movement" | "stockout" | "receipt" | "order_request" | "return",
  "lines": [
    {{"item_name": "...", "quantity": number or null, "unit": "..." or null, "direction": "out" or "in"}}
  ],
  "recipient_note": "..." or null
}}

Rules:
- "actionable": false when the message does not name any identifiable stock item, or is not really about inventory (a misclassification) — the caller falls back to plain event logging in that case.
- "kind": "movement" for an ordinary deduction/use ("we gifted some cookies"), "stockout" for a "ran out of" / "out of" report, "receipt" for goods coming IN with an invoice/delivery/order behind it ("we received the produce delivery", "we got 3 more reams, add them to stock"), "return" for goods coming back INTO stock from a customer/patient/guest return (no document expected — "a patient returned an unopened box of gloves, put it back in stock"), "order_request" for an explicit "we need to reorder X".
- "quantity" is null when the message doesn't state a number ("some cookies") — never guess a number.
- "recipient_note" captures a short human-readable aside like "gifted to Elizabeth (manager)" — null if there isn't one.
- Every "direction" is "out" for movement/stockout, "in" for receipt/return. order_request lines have direction "out" (they represent what's being replenished).
"""


def _build_prompt(content: str, item_names: list[str]) -> str:
    names = ", ".join(item_names) if item_names else "(none yet)"
    return _PROMPT_TEMPLATE.format(item_names=names, content=content)


_FALLBACK_RESULT = {
    "actionable": False,
    "kind": "movement",
    "lines": [],
    "recipient_note": None,
}

_NUMERIC_RE = re.compile(r"(\d+(?:\.\d+)?)")


def fallback_extraction(content: str) -> dict:
    """Deterministic, zero-Gemini fallback. No item name can be isolated
    without a model, so this always reports non-actionable — the caller
    then falls back to EMS intake, same as a classify_event outage never
    loses documentation, only routes it elsewhere."""
    return dict(_FALLBACK_RESULT)


def _parse_model_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


async def extract_inventory(content: str, item_names: list[str]) -> dict:
    """Never raises. Returns the fallback shape (actionable=False) on any
    Gemini failure or malformed response — caller falls back to
    _bg_ems_intake wholesale in that case, same as EMS's own outage rule."""
    try:
        prompt = _build_prompt(content, item_names)
        resp = await _get_client().aio.models.generate_content(
            model=FLASH_LITE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2, response_mime_type="application/json", max_output_tokens=500,
            ),
        )
        parsed = _parse_model_json(resp.text)
        return {**_FALLBACK_RESULT, **parsed}
    except Exception:
        logger.warning("inventory: extraction failed, falling back", exc_info=True)
        return fallback_extraction(content)
