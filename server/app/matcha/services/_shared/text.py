"""Shared text formatting helpers. Leaf module: imports nothing from services/."""
import re


def _hum(s) -> str:
    if not s:
        return ""
    return str(s).replace("_", " ").replace("-", " ").strip().title()


def _slug(s) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-") or "x"


def history_text(history: list[dict], turns: int) -> str:
    """Render the last `turns` user/assistant messages as plain chat history.

    Byte-identical across 5 pilots before this extraction (broker_pilot,
    handbook_pilot, legal_defense, ask_hr, and core/services/compliance_pilot.py
    — the last one left alone: core/ must not import matcha/services/, so it
    keeps its own copy). Each caller closes over its own `_HISTORY_TURNS`
    (10-12 depending on pilot), so `turns` is a parameter rather than a shared
    constant.
    """
    msgs = [m for m in (history or []) if m.get("role") in ("user", "assistant")][-turns:]
    return "\n".join(f"[{m['role']}] {m.get('content', '')}" for m in msgs) or "(no prior messages)"
