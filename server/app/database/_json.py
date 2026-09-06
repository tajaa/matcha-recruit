"""JSONB decode helper for asyncpg rows.

No ``set_type_codec('jsonb', …)`` is registered on the pool, so asyncpg hands
every JSONB column back as a ``str``.  Anything that reads one — directly, or
through ``jsonb_agg``/``json_build_object`` — has to decode it first, or the
value reaches the client as a JSON *string* and every field read on it silently
yields undefined.

Registering the codec in ``init_pool`` would fix all of this at the source, but
it flips the return type of every JSONB read across all five backend apps at
once, including the call sites that already ``json.loads()`` the string
themselves.  That is its own change with its own audit; this helper is the
shared decode until then.
"""

import json
from typing import Any, Optional


def decode_jsonb(value: Any, default: Optional[Any] = None) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return default
    return value if value is not None else default
