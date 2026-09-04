"""Back-compat re-export — the shared decode now lives in `app.database`.

Four inventory modules import `decode_jsonb` from here; the helper itself moved
next to the pool that causes the problem it works around.
"""

from app.database import decode_jsonb  # noqa: F401

__all__ = ["decode_jsonb"]
