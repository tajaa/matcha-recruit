"""Writers: an account whose site is a magazine (cappemag04).

A writer picks a handle at sign-up and their magazine lives at
`<handle>.gummfit.com`: a `source_type='magazine'` site whose front page is
the magazine (`front_at_root`), with no shop. The handle is exactly what they
chose — taken is a 409 to choose again, never a quiet "-2".
"""
from __future__ import annotations

import re
from typing import Optional

from ..common import RESERVED_SUBDOMAINS
from ...models.magazine import HANDLE_PATTERN

_HANDLE = re.compile(HANDLE_PATTERN)
BAD_HANDLE = "Use 3–30 lowercase letters, numbers or single hyphens, starting and ending with a letter or number."
RESERVED = "That address is reserved. Pick another."
TAKEN = "That address is taken. Pick another."


def normalize_handle(handle: str) -> str:
    return (handle or "").strip().lower()


def handle_problem(handle: str) -> Optional[str]:
    """Why a handle can't be a magazine's address, or None."""
    if not _HANDLE.fullmatch(handle) or "--" in handle:
        return BAD_HANDLE
    if handle in RESERVED_SUBDOMAINS:
        return RESERVED
    return None


async def handle_taken(conn, handle: str) -> bool:
    return bool(await conn.fetchval(
        "SELECT 1 FROM cappe_sites WHERE slug = $1 OR subdomain = $1", handle,
    ))
