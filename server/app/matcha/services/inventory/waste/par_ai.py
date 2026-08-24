"""Bounded, read-only AI proposals for deterministic par exceptions."""
import asyncio
import json
import logging
from decimal import Decimal

from google.genai import types
from app.core.services.model_catalog import GEMINI_FLASH
from app.matcha.services._shared.gemini import genai_env_client

logger = logging.getLogger(__name__)
MAX_ITEMS = 20

def _parse(text: str) -> dict:
    try:
        value = json.loads((text or '').strip().removeprefix('```json').removesuffix('```'))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}

def _coerce(raw: dict, eligible_ids: set[str]) -> list[dict]:
    output = []
    for row in (raw.get('exceptions') or [])[:MAX_ITEMS]:
        if not isinstance(row, dict) or str(row.get('item_id')) not in eligible_ids: continue
        try: multiplier = Decimal(str(row.get('multiplier')))
        except Exception: continue
        if not Decimal('0.5') <= multiplier <= Decimal('1.5'): continue
        reason = str(row.get('reason') or '').strip()
        if reason: output.append({'item_id': str(row['item_id']), 'multiplier': multiplier, 'reason': reason[:200]})
    return output

async def propose_par_exceptions(*, suppressed_items: list[dict]) -> dict:
    """Never writes. Only suppressed rows with a real loss signal are eligible."""
    eligible = [row for row in suppressed_items if (row.get('stockouts') or row.get('waste_units'))][:MAX_ITEMS]
    if not eligible: return {'available': True, 'model': GEMINI_FLASH, 'exceptions': []}
    prompt = ('Review only these deterministic signals. Propose a bounded multiplier for a future manager-confirmed par change; do no arithmetic and never invent values. '
              'Return JSON {"exceptions":[{"item_id":"...","multiplier":0.5..1.5,"reason":"..."}]}.\n' + json.dumps(eligible, default=str))
    try:
        response = await asyncio.wait_for(genai_env_client().aio.models.generate_content(
            model=GEMINI_FLASH, contents=[prompt], config=types.GenerateContentConfig(temperature=0.2, response_mime_type='application/json')), timeout=60)
        return {'available': True, 'model': GEMINI_FLASH, 'exceptions': _coerce(_parse(getattr(response, 'text', '') or ''), {str(row['item_id']) for row in eligible})}
    except Exception:
        logger.warning('inventory par exception draft unavailable', exc_info=True)
        return {'available': False, 'model': GEMINI_FLASH, 'exceptions': []}
