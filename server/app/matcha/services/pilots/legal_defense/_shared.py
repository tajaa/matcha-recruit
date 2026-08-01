"""Shared constants + tiny display/parse helpers used across the package."""

from ..._shared.citations import _parse_json  # noqa: F401 — re-export, see Stage 6
from ..._shared.pdf import _fmt_dt
from ..._shared.gemini import _genai  # noqa: F401 — re-export, package imports it from here
from ..._shared.text import _hum  # noqa: F401 — re-export, package imports it from here
from app.core.services.model_catalog import GEMINI_FLASH


MODEL = GEMINI_FLASH
_GEMINI_TIMEOUT = 90
_PER_SOURCE_CAP = 100
_HISTORY_TURNS = 12
# Matches the prompt's "AT MOST 3 requests" rule; enforced server-side because
# the model's compliance with its own instruction is not a guarantee.
_MAX_INTAKE_REQUESTS = 3

DISCLAIMER = (
    "Prepared from system records to assist counsel. Reflects records on file as "
    "of generation. This is an evidence-assembly aid, not legal advice and not a "
    "legal conclusion; attorney review is required."
)

def _dt(v) -> str:
    return _fmt_dt(v)


def _iso(v) -> str | None:
    """Machine-sortable companion to the display-formatted ``when`` — the
    chronology (UI tab + PDF section) sorts on this, never on display strings."""
    if v is None:
        return None
    try:
        return v.isoformat()
    except AttributeError:
        return str(v) or None


# `_hum` (imported above) humanizes a raw db enum/snake_case value for display —
# 'in_review' -> 'In Review'. It feeds both the AI corpus text and the PDF, so the
# model's own summaries read cleanly too, not just the deterministic rendering.
# It title-cases, which turns statutory acronyms into "Fmla" / "Eeoc" — fine
# for a status enum, wrong in an attorney-facing record where the acronym IS the
# statute's name. Only these closed vocabularies need the override.
_ACRONYM_LABELS = {
    "fmla": "FMLA", "state_pfml": "state PFML", "unpaid_loa": "unpaid LOA",
    "eeoc": "EEOC", "nlrb": "NLRB", "osha": "OSHA", "state_agency": "state agency",
}


def _hum_acronym(v) -> str:
    return _ACRONYM_LABELS.get(v, _hum(v))


def _money(v) -> str:
    """Currency for an attorney-facing record: cents are shown when they exist.
    A settlement of 45000.50 rendered as "$45,000" is a wrong figure, not a
    tidier one."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"${f:,.0f}" if f == int(f) else f"${f:,.2f}"
def _dt_date(v) -> str:
    """Date-only render for law/bill records. The two retrieval paths hand
    back different types for the same field (RAG pre-isoformats to str, the
    SQL fallback returns date objects) — normalize so one exhibit never shows
    the same date in two formats."""
    if v is None:
        return "—"
    if isinstance(v, str):
        return v[:10] or "—"
    try:
        return v.strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return str(v)
def _emp_name(d, fallback: str = "—") -> str:
    """Employee display name from anything carrying first_name/last_name — a
    detail dict (which may not have the keys at all) or an asyncpg Record."""
    name = f"{d.get('first_name') or ''} {d.get('last_name') or ''}".strip()
    return name or fallback
