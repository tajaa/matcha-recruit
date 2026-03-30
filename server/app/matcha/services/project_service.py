"""Project service — CRUD + section management for mw_projects."""

import json
import logging
import os
from typing import Optional
from uuid import UUID

from ...database import get_connection

logger = logging.getLogger(__name__)


async def create_project(company_id: UUID, user_id: UUID, title: str = "Untitled Project") -> dict:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO mw_projects (company_id, created_by, title)
            VALUES ($1, $2, $3)
            RETURNING id, company_id, created_by, title, sections, status, is_pinned, version, created_at, updated_at
            """,
            company_id, user_id, title,
        )
        # Auto-create a first chat in the project
        chat = await conn.fetchrow(
            """
            INSERT INTO mw_threads (company_id, created_by, title, project_id)
            VALUES ($1, $2, $3, $4)
            RETURNING id, title, status, created_at, updated_at
            """,
            company_id, user_id, "Chat 1", row["id"],
        )
    project = dict(row)
    project["sections"] = json.loads(project["sections"]) if isinstance(project["sections"], str) else project["sections"]
    project["chats"] = [dict(chat)]
    project["chat_count"] = 1
    return project


async def get_project(project_id: UUID, company_id: UUID) -> Optional[dict]:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM mw_projects WHERE id = $1 AND company_id = $2",
            project_id, company_id,
        )
        if not row:
            return None
        project = dict(row)
        project["sections"] = json.loads(project["sections"]) if isinstance(project["sections"], str) else project["sections"]

        chats = await conn.fetch(
            """
            SELECT id, title, status, version, created_at, updated_at, is_pinned
            FROM mw_threads
            WHERE project_id = $1
            ORDER BY created_at ASC
            """,
            project_id,
        )
        project["chats"] = [dict(c) for c in chats]
        project["chat_count"] = len(chats)
    return project


async def list_projects(company_id: UUID, status: Optional[str] = None) -> list[dict]:
    async with get_connection() as conn:
        if status:
            rows = await conn.fetch(
                """
                SELECT p.*, (SELECT COUNT(*) FROM mw_threads WHERE project_id = p.id) as chat_count
                FROM mw_projects p
                WHERE p.company_id = $1 AND p.status = $2
                ORDER BY p.updated_at DESC
                """,
                company_id, status,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT p.*, (SELECT COUNT(*) FROM mw_threads WHERE project_id = p.id) as chat_count
                FROM mw_projects p
                WHERE p.company_id = $1
                ORDER BY p.updated_at DESC
                """,
                company_id,
            )
    results = []
    for r in rows:
        d = dict(r)
        d["sections"] = json.loads(d["sections"]) if isinstance(d["sections"], str) else d["sections"]
        results.append(d)
    return results


async def update_project(project_id: UUID, updates: dict) -> dict:
    async with get_connection() as conn:
        allowed = {"title", "is_pinned", "status"}
        sets = []
        vals = []
        idx = 1
        for k, v in updates.items():
            if k in allowed:
                sets.append(f"{k} = ${idx}")
                vals.append(v)
                idx += 1
        if not sets:
            row = await conn.fetchrow("SELECT * FROM mw_projects WHERE id = $1", project_id)
            return dict(row) if row else {}
        vals.append(project_id)
        row = await conn.fetchrow(
            f"UPDATE mw_projects SET {', '.join(sets)}, updated_at = NOW() WHERE id = ${idx} RETURNING *",
            *vals,
        )
    result = dict(row)
    result["sections"] = json.loads(result["sections"]) if isinstance(result["sections"], str) else result["sections"]
    return result


async def archive_project(project_id: UUID):
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE mw_projects SET status = 'archived', updated_at = NOW() WHERE id = $1",
            project_id,
        )


# ── Section operations ──

async def _update_sections(project_id: UUID, sections: list) -> dict:
    """Atomically update sections and bump version."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE mw_projects
            SET sections = $1::jsonb, version = version + 1, updated_at = NOW()
            WHERE id = $2
            RETURNING *
            """,
            json.dumps(sections), project_id,
        )
    result = dict(row)
    result["sections"] = json.loads(result["sections"]) if isinstance(result["sections"], str) else result["sections"]
    return result


async def get_sections(project_id: UUID) -> list:
    async with get_connection() as conn:
        raw = await conn.fetchval("SELECT sections FROM mw_projects WHERE id = $1", project_id)
    if raw is None:
        return []
    return json.loads(raw) if isinstance(raw, str) else raw


async def add_section(project_id: UUID, section: dict) -> dict:
    sections = await get_sections(project_id)
    new_section = {
        "id": os.urandom(8).hex(),
        "title": section.get("title"),
        "content": section.get("content", ""),
        "source_message_id": section.get("source_message_id"),
    }
    sections.append(new_section)
    result = await _update_sections(project_id, sections)
    return {"section": new_section, **result}


async def update_section(project_id: UUID, section_id: str, updates: dict) -> dict:
    sections = await get_sections(project_id)
    for i, s in enumerate(sections):
        if s.get("id") == section_id:
            if "title" in updates:
                sections[i] = {**s, "title": updates["title"]}
            if "content" in updates:
                sections[i] = {**sections[i], "content": updates["content"]}
            break
    return await _update_sections(project_id, sections)


async def delete_section(project_id: UUID, section_id: str) -> dict:
    sections = await get_sections(project_id)
    sections = [s for s in sections if s.get("id") != section_id]
    return await _update_sections(project_id, sections)


async def reorder_sections(project_id: UUID, section_ids: list[str]) -> dict:
    sections = await get_sections(project_id)
    section_map = {s["id"]: s for s in sections}
    reordered = [section_map[sid] for sid in section_ids if sid in section_map]
    seen = set(section_ids)
    for s in sections:
        if s["id"] not in seen:
            reordered.append(s)
    return await _update_sections(project_id, reordered)


async def create_project_chat(project_id: UUID, company_id: UUID, user_id: UUID, title: str | None = None) -> dict:
    async with get_connection() as conn:
        # Count existing chats to generate title
        if not title:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM mw_threads WHERE project_id = $1", project_id
            )
            title = f"Chat {count + 1}"

        row = await conn.fetchrow(
            """
            INSERT INTO mw_threads (company_id, created_by, title, project_id)
            VALUES ($1, $2, $3, $4)
            RETURNING id, title, status, version, created_at, updated_at, is_pinned, project_id
            """,
            company_id, user_id, title, project_id,
        )
        # Update project timestamp
        await conn.execute(
            "UPDATE mw_projects SET updated_at = NOW() WHERE id = $1", project_id
        )
    return dict(row)
