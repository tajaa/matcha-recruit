"""Statement-of-Values auto-parse — Gemini reads an uploaded carrier SOV (PDF, or a
CSV / spreadsheet export whose columns don't match our template) and extracts the
per-building COPE + values, so a business can load its property schedule without
hand-keying every building.

Best-effort, never raises — returns a DRAFT list the business REVIEWS and edits
before it is bulk-inserted (it does NOT write buildings). Mirrors ``contract_parser`` /
``loss_run_parser``: cached IRAnalyzer, the file sent to Gemini (PDF as an inline part,
CSV/text as a text part), JSON parsed back into the building shape, construction types
normalized to our ISO keys. The deterministic, column-matched path is the CSV
bulk-upload endpoint; this is the "drop any SOV file and we figure out the columns" path.
"""

import asyncio
import json
import logging
from typing import Optional

from app.config import get_settings
from app.matcha.services.ir_analysis import IRAnalyzer
from app.matcha.services.property_sov import CONSTRUCTION_GRADE

logger = logging.getLogger(__name__)

_analyzer: Optional[IRAnalyzer] = None
SOV_PARSE_TIMEOUT = 120   # a multi-building SOV PDF can be large
MAX_BUILDINGS = 1000

# Free-text construction descriptions → our ISO keys (property_sov.CONSTRUCTION_GRADE).
_CONSTRUCTION_ALIASES = {
    "fire resistive": "fire_resistive", "fire-resistive": "fire_resistive", "fr": "fire_resistive",
    "iso 6": "fire_resistive", "class 6": "fire_resistive", "concrete": "fire_resistive",
    "modified fire resistive": "modified_fire_resistive", "modified fire-resistive": "modified_fire_resistive",
    "mfr": "modified_fire_resistive", "iso 5": "modified_fire_resistive", "class 5": "modified_fire_resistive",
    "masonry non combustible": "masonry_non_combustible", "masonry non-combustible": "masonry_non_combustible",
    "mnc": "masonry_non_combustible", "iso 4": "masonry_non_combustible", "class 4": "masonry_non_combustible",
    "non combustible": "non_combustible", "non-combustible": "non_combustible", "noncombustible": "non_combustible",
    "nc": "non_combustible", "iso 3": "non_combustible", "class 3": "non_combustible", "steel": "non_combustible",
    "joisted masonry": "joisted_masonry", "jm": "joisted_masonry", "iso 2": "joisted_masonry",
    "class 2": "joisted_masonry", "brick": "joisted_masonry", "masonry": "joisted_masonry",
    "frame": "frame", "wood frame": "frame", "wood": "frame", "iso 1": "frame", "class 1": "frame",
}

_PROMPT = """You are an insurance Statement of Values (SOV) analyst. The attached file is a commercial-property SOV / building schedule (a carrier or broker spreadsheet, or a PDF). Extract one record PER BUILDING / LOCATION.

Return ONLY valid JSON with exactly this shape (use null for anything not present — never invent values):
{"buildings": [
  {"name": "<building or location name/label, or null>",
   "address": "<street address, or null>",
   "city": "<city, or null>",
   "state": "<2-letter US state, or null>",
   "zipcode": "<postal code, or null>",
   "county": "<county, or null>",
   "occupancy": "<occupancy / use, e.g. 'office', 'warehouse', 'retail', or null>",
   "construction_type": "<one of: fire_resistive, modified_fire_resistive, masonry_non_combustible, non_combustible, joisted_masonry, frame — map ISO class 6..1 or descriptions like 'concrete'/'steel'/'brick'/'wood frame'; null if unknown>",
   "year_built": <integer year, or null>,
   "sq_ft": <integer square footage, or null>,
   "stories": <integer, or null>,
   "roof_year": <integer year the roof was last replaced, or null>,
   "sprinklered": <true if sprinklered, false if explicitly not, null if unknown>,
   "protection_class": "<ISO Public Protection Class 1-10 as a string, or null>",
   "building_value": <building/structure replacement or stated value in whole dollars, or null>,
   "contents_value": <contents/BPP value in whole dollars, or null>,
   "bi_value": <business-interruption / business-income value in whole dollars, or null>,
   "replacement_cost": <total replacement cost in whole dollars, or null>,
   "insured_value": <stated/insured value in whole dollars, or null>,
   "valuation_basis": "<RCV or ACV, or null>",
   "coinsurance_pct": <coinsurance percentage e.g. 90, or null>,
   "ordinance_law": "<none/A/B/C/ABC if stated, or null>",
   "bi_months": <business-interruption period of restoration in months, or null>,
   "blanket": <true if a blanket limit (vs scheduled), else null>,
   "aop_deductible": <all-other-perils deductible in whole dollars, or null>,
   "wind_deductible_pct": <wind/hail deductible percent, or null>,
   "named_storm_deductible_pct": <named-storm/hurricane deductible percent, or null>,
   "quake_deductible_pct": <earthquake deductible percent, or null>,
   "roof_type": "<roof covering e.g. TPO/EPDM/BUR/metal/shingle/tile, or null>",
   "wiring_year": <year wiring last updated, or null>,
   "central_station_alarm": <true if a central-station/monitored fire alarm, else null>,
   "cooking_nfpa96": <true if commercial cooking / Type-I hood present, else null>,
   "hot_work": <true if hot work performed on site, else null>,
   "hazmat": <true if hazardous materials/flammables stored, else null>,
   "note": "<short note, or null>"}
]}

Convert "$1,000,000" / "$1M" / "1,000,000" to 1000000. If a column is a combined building+contents TIV only, put it in building_value. Do not include header or subtotal rows. Do not include markdown fences."""


def _get_analyzer() -> IRAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = IRAnalyzer(api_key=get_settings().gemini_api_key)
    return _analyzer


def normalize_construction(raw) -> Optional[str]:
    """Free-text / ISO-class construction → our CONSTRUCTION_GRADE key, or None.
    Pure; shared with the CSV bulk-upload row coercion."""
    if not isinstance(raw, str):
        return None
    s = raw.strip().lower()
    if not s:
        return None
    if s in CONSTRUCTION_GRADE:
        return s
    key = s.replace("_", " ")
    if key in _CONSTRUCTION_ALIASES:
        return _CONSTRUCTION_ALIASES[key]
    # last resort: substring match against alias phrases (longest first)
    for alias in sorted(_CONSTRUCTION_ALIASES, key=len, reverse=True):
        if alias in key:
            return _CONSTRUCTION_ALIASES[alias]
    return None


def _str(v, limit: int) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s[:limit] if s else None


def _int(v, lo: int, hi: int) -> Optional[int]:
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None
    return n if lo <= n <= hi else None


def _num(v) -> Optional[float]:
    """Dollar value → non-negative float. Tolerates '$', commas, 'M'/'K' suffixes."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if v >= 0 else None
    s = str(v).strip().lower().replace("$", "").replace(",", "")
    if not s:
        return None
    mult = 1.0
    if s.endswith("m"):
        mult, s = 1_000_000.0, s[:-1]
    elif s.endswith("k"):
        mult, s = 1_000.0, s[:-1]
    try:
        n = float(s) * mult
    except ValueError:
        return None
    return n if n >= 0 else None


def _bool(v) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("true", "yes", "y", "1", "sprinklered", "fully", "fully sprinklered"):
        return True
    if s in ("false", "no", "n", "0", "none", "unsprinklered"):
        return False
    return None


def coerce_building(raw: dict) -> Optional[dict]:
    """One raw building dict → the BuildingUpsert field shape (clamped). PURE.
    Returns None for an empty/garbage row (no name/address and no values)."""
    if not isinstance(raw, dict):
        return None
    spr = _bool(raw.get("sprinklered"))
    state = _str(raw.get("state"), 2)
    valuation = _str(raw.get("valuation_basis"), 4)
    valuation = valuation.upper() if valuation and valuation.upper() in ("RCV", "ACV") else None
    ordl = _str(raw.get("ordinance_law"), 8)
    b = {
        "name": _str(raw.get("name"), 255),
        "address": _str(raw.get("address"), 500),
        "city": _str(raw.get("city"), 120),
        "state": state.upper() if state else None,
        "zipcode": _str(raw.get("zipcode"), 10),
        "county": _str(raw.get("county"), 120),
        "occupancy": _str(raw.get("occupancy"), 120),
        "construction_type": normalize_construction(raw.get("construction_type")),
        "year_built": _int(raw.get("year_built"), 1700, 2100),
        "sq_ft": _int(raw.get("sq_ft"), 0, 100_000_000),
        "stories": _int(raw.get("stories"), 0, 500),
        "roof_year": _int(raw.get("roof_year"), 1700, 2100),
        "sprinklered": bool(spr),
        "protection_class": _str(raw.get("protection_class"), 4),
        "building_value": _num(raw.get("building_value")),
        "contents_value": _num(raw.get("contents_value")),
        "bi_value": _num(raw.get("bi_value")),
        "replacement_cost": _num(raw.get("replacement_cost")),
        "insured_value": _num(raw.get("insured_value")),
        "note": _str(raw.get("note"), 2000),
        # deeper capture (propd01)
        "valuation_basis": valuation,
        "coinsurance_pct": _num(raw.get("coinsurance_pct")),
        "ordinance_law": ordl,
        "bi_months": _int(raw.get("bi_months"), 0, 120),
        "blanket": bool(_bool(raw.get("blanket"))),
        "aop_deductible": _num(raw.get("aop_deductible")),
        "wind_deductible_pct": _num(raw.get("wind_deductible_pct")),
        "named_storm_deductible_pct": _num(raw.get("named_storm_deductible_pct")),
        "quake_deductible_pct": _num(raw.get("quake_deductible_pct")),
        "roof_type": _str(raw.get("roof_type"), 40),
        "wiring_year": _int(raw.get("wiring_year"), 1700, 2100),
        "central_station_alarm": bool(_bool(raw.get("central_station_alarm"))),
        "cooking_nfpa96": bool(_bool(raw.get("cooking_nfpa96"))),
        "hot_work": bool(_bool(raw.get("hot_work"))),
        "hazmat": bool(_bool(raw.get("hazmat"))),
    }
    has_identity = any(b[k] for k in ("name", "address", "city"))
    has_value = any(b[k] is not None for k in ("building_value", "contents_value", "bi_value", "replacement_cost", "insured_value"))
    return b if (has_identity or has_value) else None


def _coerce_buildings(payload: dict) -> list[dict]:
    out: list[dict] = []
    for raw in (payload.get("buildings") or [])[:MAX_BUILDINGS]:
        b = coerce_building(raw)
        if b:
            out.append(b)
    return out


async def parse_sov(file_bytes: bytes, mime_type: str) -> dict:
    """Best-effort SOV parse → {"buildings": [...draft...], "available": bool, "model": str}.
    Never raises. PDF goes to Gemini as an inline part; CSV/text is decoded and sent as
    a text part. ``available`` is False (empty buildings) on any failure."""
    analyzer = _get_analyzer()
    payload: dict = {}
    try:
        from google.genai import types
        mt = (mime_type or "").lower()
        if "pdf" in mt:
            part = types.Part.from_bytes(data=file_bytes, mime_type="application/pdf")
        else:
            text = file_bytes.decode("utf-8", errors="replace")
            part = types.Part.from_text(text=f"SOV data follows:\n\n{text}")
        response = await asyncio.wait_for(
            analyzer.client.aio.models.generate_content(model=analyzer.model, contents=[_PROMPT, part]),
            timeout=SOV_PARSE_TIMEOUT,
        )
        raw = (getattr(response, "text", None) or "").strip()
        payload = analyzer._parse_json_response(raw) or {}
    except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as exc:  # never-raises contract
        logger.warning("SOV parse failed: %s", exc)
        payload = {}
    buildings = _coerce_buildings(payload)
    return {"buildings": buildings, "available": bool(buildings), "model": analyzer.model}
