"""Matter persistence helpers shared by the HTTP route
(`routes/pilots/legal_defense.py`) and the Huume chat skill
(`services/huume/legal_skill.py`).

HTTP-free on purpose: `load_matter` returns None instead of raising 404 (the
route wraps it), and `audit_matter` takes a plain optional `ip_address` rather
than a Request. The "prefer the newest assistant turn with a non-empty
evidence_map" rule in `latest_memo` is real logic both callers must share —
duplicating it is how an intake-only turn ends up rendered as an empty memo.
"""

from __future__ import annotations

import json
from typing import Any, Optional


async def load_matter(conn, matter_id, company_id) -> Optional[dict[str, Any]]:
    """Tenant-scoped matter fetch. None when it doesn't exist or belongs to
    another company — never leak which of the two it was."""
    row = await conn.fetchrow(
        "SELECT * FROM legal_matters WHERE id = $1 AND company_id = $2",
        matter_id, company_id,
    )
    return dict(row) if row else None


async def load_messages(conn, matter_id) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT role, content, metadata, created_at FROM legal_matter_messages "
        "WHERE matter_id = $1 ORDER BY created_at",
        matter_id,
    )
    return [dict(r) for r in rows]


async def latest_memo(conn, matter_id) -> Optional[dict[str, Any]]:
    """The newest assistant turn that actually carries an analysis.

    Not simply the newest row: intake turns (the assistant asking the admin for
    missing material) persist with an empty ``evidence_map`` by design, and
    building the packet off one of those renders a memo whose observations
    section reads "No grounded observations were recorded." even though an
    earlier turn produced a full analysis. Prefer the newest turn with a
    non-empty map; fall back to the newest row so matters predating this — and
    matters whose only analysis genuinely found nothing — behave as before, and
    so the caller's "discuss the matter in chat first" refusal still triggers
    only on a matter with no assistant turn at all.
    """
    row = await conn.fetchrow(
        "SELECT content, metadata FROM legal_matter_messages "
        "WHERE matter_id = $1 AND role = 'assistant' "
        "  AND COALESCE(jsonb_array_length(metadata -> 'evidence_map'), 0) > 0 "
        "ORDER BY created_at DESC LIMIT 1",
        matter_id,
    )
    if not row:
        row = await conn.fetchrow(
            "SELECT content, metadata FROM legal_matter_messages "
            "WHERE matter_id = $1 AND role = 'assistant' ORDER BY created_at DESC LIMIT 1",
            matter_id,
        )
    if not row:
        return None
    meta = row["metadata"]
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:  # noqa: BLE001
            meta = {}
    meta = meta or {}
    return {
        "assistant_text": row["content"] or "",
        "evidence_map": meta.get("evidence_map") or [],
        "open_questions": meta.get("open_questions") or [],
    }


async def audit_matter(
    conn, matter_id, user_id, action: str,
    details: Optional[dict[str, Any]] = None, ip_address: Optional[str] = None,
) -> None:
    """Append to the legal-grade `legal_matter_audit_log` trail. The HTTP route
    passes the request IP; headless callers (Huume) pass None."""
    await conn.execute(
        """INSERT INTO legal_matter_audit_log (matter_id, user_id, action, details, ip_address)
           VALUES ($1, $2, $3, $4, $5)""",
        matter_id, user_id, action, json.dumps(details or {}), ip_address,
    )
