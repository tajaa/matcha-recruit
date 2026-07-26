"""Helpers for ER export formatting."""

from __future__ import annotations

import json
from typing import Any


def extract_analysis_export_text(raw_value: Any) -> str:
    """Extract the most readable text representation for PDF exports."""
    if isinstance(raw_value, str):
        stripped = raw_value.strip()
        if not stripped:
            return "No results."
        try:
            parsed = json.loads(stripped)
        except Exception:
            return stripped
        raw_value = parsed

    if isinstance(raw_value, dict):
        for key in ("content", "summary", "timeline_summary", "case_summary"):
            value = raw_value.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        try:
            return json.dumps(raw_value, indent=2)[:500]
        except Exception:
            return str(raw_value)[:500]

    if raw_value is None:
        return "No results."

    text = str(raw_value).strip()
    return text or "No results."
