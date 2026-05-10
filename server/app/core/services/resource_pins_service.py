"""Resource pins — free-tier (and any-tier) per-user favorites across the
resources hub. Mirrors the `mw_project_pins` shape: composite PK,
ON CONFLICT DO NOTHING for idempotent inserts, plain DELETE for unpins.
"""

import re
from typing import Literal
from uuid import UUID

from ...database import get_connection


ResourceKind = Literal[
    "template", "job_description", "glossary", "state_guide", "calculator",
]

VALID_KINDS: set[str] = {
    "template", "job_description", "glossary", "state_guide", "calculator",
}

# Slugs across all 5 catalogs are lowercase ASCII + hyphens. Bound at 128
# to match the DB column.
RESOURCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,127}$")


def _validate(kind: str, resource_id: str) -> None:
    if kind not in VALID_KINDS:
        raise ValueError(f"Invalid resource_kind: {kind}")
    if not RESOURCE_ID_PATTERN.match(resource_id):
        raise ValueError(f"Invalid resource_id: {resource_id}")


async def list_pins(user_id: UUID) -> list[dict]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT resource_kind, resource_id, created_at
            FROM resource_pins
            WHERE user_id = $1
            ORDER BY created_at DESC
            """,
            user_id,
        )
        return [
            {
                "kind": r["resource_kind"],
                "id": r["resource_id"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]


async def add_pin(user_id: UUID, kind: str, resource_id: str) -> None:
    _validate(kind, resource_id)
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO resource_pins (user_id, resource_kind, resource_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, resource_kind, resource_id) DO NOTHING
            """,
            user_id, kind, resource_id,
        )


async def remove_pin(user_id: UUID, kind: str, resource_id: str) -> None:
    _validate(kind, resource_id)
    async with get_connection() as conn:
        await conn.execute(
            """
            DELETE FROM resource_pins
            WHERE user_id = $1 AND resource_kind = $2 AND resource_id = $3
            """,
            user_id, kind, resource_id,
        )
