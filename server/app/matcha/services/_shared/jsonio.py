"""Shared JSON helpers for DB values. Leaf module: imports nothing from services/ or routes/.

Named ``jsonio`` rather than ``json`` so the stdlib import inside it is unambiguous.
"""
import json
import logging

logger = logging.getLogger(__name__)


def safe_json_loads(value, default=None):
    """Safely parse JSON from a database value."""
    if value is None:
        return default if default is not None else {}
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Failed to parse JSON: {e}")
        return default if default is not None else {}


def loads_or_none(v):
    """Coerce a JSONB column to its Python value, or None.

    Distinct from ``safe_json_loads`` on purpose: this returns ``None`` for a
    NULL column and for unparseable text, where the other returns ``{}``. The
    claims/litigation packets need "absent" to stay distinguishable from "empty
    object" — an empty dict renders as a present-but-blank section in the PDF.
    """
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return None
