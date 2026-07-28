"""Shared citation gate + Gemini JSON parsing — every grounded pilot (Legal
Defense, HR Pilot, Handbook Pilot, Analysis Pilot, Broker Pilot, discipline AI,
Huume) drops any model-cited id that isn't in its own retrieved corpus through
this gate. Leaf module: imports nothing from services/.
"""
import json


def _parse_json(text: str) -> dict:
    """Parse a Gemini JSON reply, tolerating ```json fences / surrounding prose."""
    if not text:
        return {}
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if t.count("```") >= 2 else t.strip("`")
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    t = t.strip()
    # Fall back to the outermost {...} if there's leading/trailing prose.
    if not t.startswith("{"):
        i, j = t.find("{"), t.rfind("}")
        if i != -1 and j != -1 and j > i:
            t = t[i : j + 1]
    try:
        out = json.loads(t)
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}


def validate_citations(evidence_map, index: dict):
    """Anti-hallucination gate: keep only cited IDs that exist in the corpus.

    Pure function (unit-tested). Returns ``(clean_map, dropped_ids)``."""
    clean, dropped = [], []
    for item in evidence_map or []:
        if not isinstance(item, dict):
            continue
        raw = item.get("cited_ids")
        ids = [c for c in raw if isinstance(c, str)] if isinstance(raw, list) else []
        keep = [c for c in ids if c in index]
        dropped.extend(c for c in ids if c not in index)
        clean.append({"point": str(item.get("point", "")), "cited_ids": keep})
    return clean, dropped
