"""Element notes/links service.

Free-form notes + links pinned to a project element (its context repo). Backed
by `mw_element_notes`; CASCADE-deleted with the element. `kind` is 'note'
(free text in `body`) or 'link' (`url` + optional `body` label).
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from ...database import get_connection

_ALLOWED_NOTE_KINDS = {"note", "link"}


def _serialize(d: dict) -> dict:
    for k in ("id", "project_id", "created_by"):
        if d.get(k) is not None:
            d[k] = str(d[k])
    if d.get("created_at") is not None:
        d["created_at"] = d["created_at"].isoformat()
    return d


async def list_element_notes(project_id: UUID, element_id: str) -> list[dict[str, Any]]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT n.id, n.element_id, n.project_id, n.created_by, n.kind, n.body, n.url,
                   n.created_at,
                   COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name) AS author_name
            FROM mw_element_notes n
            LEFT JOIN clients c ON c.user_id = n.created_by
            LEFT JOIN employees e ON e.user_id = n.created_by
            LEFT JOIN admins a ON a.user_id = n.created_by
            WHERE n.project_id = $1 AND n.element_id = $2
            ORDER BY n.created_at DESC
            """,
            project_id, element_id,
        )
    return [_serialize(dict(r)) for r in rows]


async def add_element_note(
    project_id: UUID,
    element_id: str,
    created_by: UUID,
    kind: str,
    body: Optional[str],
    url: Optional[str],
) -> dict[str, Any]:
    kind = (kind or "note").strip().lower()
    if kind not in _ALLOWED_NOTE_KINDS:
        raise ValueError(f"Invalid note kind: {kind}")
    body = (body or "").strip() or None
    url = (url or "").strip() or None
    if kind == "link" and not url:
        raise ValueError("A link note requires a url")
    if kind == "note" and not body:
        raise ValueError("A note requires body text")
    async with get_connection() as conn:
        # Guard against pinning a note onto another project's element.
        owns = await conn.fetchval(
            "SELECT 1 FROM mw_project_elements WHERE id = $1 AND project_id = $2",
            element_id, project_id,
        )
        if not owns:
            return {}
        row = await conn.fetchrow(
            """
            INSERT INTO mw_element_notes (element_id, project_id, created_by, kind, body, url)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, element_id, project_id, created_by, kind, body, url, created_at
            """,
            element_id, project_id, created_by, kind, body, url,
        )
    return _serialize(dict(row))


async def delete_element_note(project_id: UUID, element_id: str, note_id: UUID) -> bool:
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM mw_element_notes WHERE id = $1 AND project_id = $2 AND element_id = $3",
            note_id, project_id, element_id,
        )
    return result.endswith("1")
