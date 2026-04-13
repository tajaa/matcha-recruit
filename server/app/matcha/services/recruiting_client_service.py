"""Recruiting client service — CRUD for hiring clients recruiters work for."""

from typing import Optional
from uuid import UUID

from ...database import get_connection


async def create_client(
    company_id: UUID,
    user_id: UUID,
    name: str,
    website: Optional[str] = None,
    logo_url: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO recruiting_clients (company_id, created_by, name, website, logo_url, notes)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, company_id, name, website, logo_url, notes,
                      created_by, created_at, updated_at, archived_at
            """,
            company_id, user_id, name, website, logo_url, notes,
        )
    return dict(row)


async def list_clients(company_id: UUID, include_archived: bool = False) -> list[dict]:
    async with get_connection() as conn:
        if include_archived:
            rows = await conn.fetch(
                """
                SELECT rc.id, rc.company_id, rc.name, rc.website, rc.logo_url, rc.notes,
                       rc.created_by, rc.created_at, rc.updated_at, rc.archived_at,
                       (SELECT COUNT(*) FROM mw_projects p
                        WHERE p.hiring_client_id = rc.id AND p.status = 'active') AS project_count
                FROM recruiting_clients rc
                WHERE rc.company_id = $1
                ORDER BY rc.archived_at NULLS FIRST, rc.name ASC
                """,
                company_id,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT rc.id, rc.company_id, rc.name, rc.website, rc.logo_url, rc.notes,
                       rc.created_by, rc.created_at, rc.updated_at, rc.archived_at,
                       (SELECT COUNT(*) FROM mw_projects p
                        WHERE p.hiring_client_id = rc.id AND p.status = 'active') AS project_count
                FROM recruiting_clients rc
                WHERE rc.company_id = $1 AND rc.archived_at IS NULL
                ORDER BY rc.name ASC
                """,
                company_id,
            )
    return [dict(r) for r in rows]


async def get_client(client_id: UUID, company_id: UUID) -> Optional[dict]:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, company_id, name, website, logo_url, notes,
                   created_by, created_at, updated_at, archived_at
            FROM recruiting_clients
            WHERE id = $1 AND company_id = $2
            """,
            client_id, company_id,
        )
    return dict(row) if row else None


async def update_client(client_id: UUID, company_id: UUID, updates: dict) -> Optional[dict]:
    allowed = {"name", "website", "logo_url", "notes"}
    sets = []
    vals: list = []
    idx = 1
    for k, v in updates.items():
        if k in allowed:
            sets.append(f"{k} = ${idx}")
            vals.append(v)
            idx += 1
    if not sets:
        return await get_client(client_id, company_id)
    vals.append(client_id)
    vals.append(company_id)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE recruiting_clients
            SET {', '.join(sets)}, updated_at = NOW()
            WHERE id = ${idx} AND company_id = ${idx + 1}
            RETURNING id, company_id, name, website, logo_url, notes,
                      created_by, created_at, updated_at, archived_at
            """,
            *vals,
        )
    return dict(row) if row else None


async def archive_client(client_id: UUID, company_id: UUID) -> bool:
    async with get_connection() as conn:
        result = await conn.execute(
            """
            UPDATE recruiting_clients
            SET archived_at = NOW(), updated_at = NOW()
            WHERE id = $1 AND company_id = $2 AND archived_at IS NULL
            """,
            client_id, company_id,
        )
    return result.endswith("1")


async def unarchive_client(client_id: UUID, company_id: UUID) -> bool:
    async with get_connection() as conn:
        result = await conn.execute(
            """
            UPDATE recruiting_clients
            SET archived_at = NULL, updated_at = NOW()
            WHERE id = $1 AND company_id = $2 AND archived_at IS NOT NULL
            """,
            client_id, company_id,
        )
    return result.endswith("1")
