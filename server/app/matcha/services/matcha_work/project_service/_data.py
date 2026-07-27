"""Raw project-row data access: the SELECT ... FOR UPDATE / write pair every
mutating path shares, and the unparsed row fetch.

Its own module rather than living in crud.py because `discipline.py` needs the
locked read/write pair while `crud.create_project` needs discipline's seeder —
a straight cycle. This is the leaf both sides depend on.
"""
import json
import logging
from typing import Optional
from uuid import UUID
from app.database import get_connection

logger = logging.getLogger(__name__)


def _parse_project(row) -> dict:
    """Convert a DB row to a project dict with parsed JSONB."""
    d = dict(row)
    for key in ("sections", "project_data"):
        if key in d and isinstance(d[key], str):
            d[key] = json.loads(d[key])
        elif key not in d:
            d[key] = [] if key == "sections" else {}
    d.setdefault("project_type", "general")
    return d


async def _load_and_lock_data(conn, project_id: UUID) -> dict:
    row = await conn.fetchrow(
        "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE", project_id
    )
    if row is None:
        raise ValueError("Project not found")
    raw = row["project_data"]
    if isinstance(raw, dict):
        return raw
    return json.loads(raw or "{}")


async def _persist_data(conn, project_id: UUID, data: dict) -> dict:
    result = await conn.fetchrow(
        "UPDATE mw_projects SET project_data = $1::jsonb, updated_at = NOW() WHERE id = $2 RETURNING *",
        json.dumps(data), project_id,
    )
    return _parse_project(result)


async def get_project_raw(project_id: UUID) -> Optional[dict]:
    """Fetch a single project row by id with no auth scoping.

    Caller is responsible for authorization (typically via
    `_verify_project_access` in the route layer). Returns None when
    the row doesn't exist.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM mw_projects WHERE id = $1", project_id,
        )
    if not row:
        return None
    return _parse_project(row)
