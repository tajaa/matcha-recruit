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
