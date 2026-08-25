"""Shared JSONB decode helper — asyncpg returns JSONB as str (no
set_type_codec('jsonb', …) registered app-wide), so any jsonb_agg(...)
column must be decoded before use."""

import json
from typing import Any, Optional


def decode_jsonb(value: Any, default: Optional[Any] = None) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return default
    return value if value is not None else default
