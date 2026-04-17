"""Project service — CRUD + section management for mw_projects."""

import json
import logging
import os
from typing import Optional
from uuid import UUID

from ...database import get_connection

logger = logging.getLogger(__name__)


async def create_project(
    company_id: UUID,
    user_id: UUID,
    title: str = "Untitled Project",
    project_type: str = "general",
    hiring_client_id: Optional[UUID] = None,
) -> dict:
    async with get_connection() as conn:
        if hiring_client_id is not None:
            owner_check = await conn.fetchval(
                "SELECT company_id FROM recruiting_clients WHERE id = $1",
                hiring_client_id,
            )
            if owner_check != company_id:
                raise ValueError("Hiring client does not belong to this workspace")
        row = await conn.fetchrow(
            """
            INSERT INTO mw_projects (company_id, created_by, title, project_type, hiring_client_id)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            company_id, user_id, title, project_type, hiring_client_id,
        )
        # Seed initial thread state for recruiting projects so the AI
        # infers skill="project" from the first message instead of "chat"
        initial_state = '{}'
        if project_type == 'recruiting':
            initial_state = json.dumps({"project_title": title, "project_sections": []})

        # Auto-create a first chat in the project
        chat = await conn.fetchrow(
            """
            INSERT INTO mw_threads (company_id, created_by, title, project_id, current_state)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            RETURNING id, title, status, created_at, updated_at
            """,
            company_id, user_id, "Chat 1", row["id"], initial_state,
        )
        # Seed the creator as project owner
        await conn.execute(
            """
            INSERT INTO mw_project_collaborators (project_id, user_id, invited_by, role)
            VALUES ($1, $2, $2, 'owner')
            ON CONFLICT (project_id, user_id) DO NOTHING
            """,
            row["id"], user_id,
        )
    project = _parse_project(row)
    project["chats"] = [dict(chat)]
    project["chat_count"] = 1
    return project


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


async def get_project(project_id: UUID, company_id: UUID, user_id: UUID | None = None) -> Optional[dict]:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT p.*, rc.name AS hiring_client_name
            FROM mw_projects p
            LEFT JOIN recruiting_clients rc ON rc.id = p.hiring_client_id
            WHERE p.id = $1 AND p.company_id = $2
            """,
            project_id, company_id,
        )
        if not row:
            return None
        project = _parse_project(row)
        project["hiring_client_name"] = row["hiring_client_name"]

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

        # Resolve collaborator role for the requesting user
        if user_id:
            collab = await conn.fetchrow(
                "SELECT role FROM mw_project_collaborators WHERE project_id = $1 AND user_id = $2 AND status = 'active'",
                project_id, user_id,
            )
            project["collaborator_role"] = collab["role"] if collab else None
        elif project.get("created_by") is not None:
            # Default: project creator is the owner
            project["collaborator_role"] = "owner"
    return project


async def list_projects(
    company_id: Optional[UUID],
    status: Optional[str] = None,
    user_id: Optional[UUID] = None,
    hiring_client_id: Optional[UUID] = None,
) -> list[dict]:
    """List projects. If user_id is provided, list via collaborator table (admin path)."""
    async with get_connection() as conn:
        if user_id:
            # Admin collaborator-based listing — all projects the user has access to
            if status:
                rows = await conn.fetch(
                    """
                    SELECT p.*, pc.role AS collaborator_role,
                           (SELECT COUNT(*) FROM mw_threads WHERE project_id = p.id) as chat_count
                    FROM mw_projects p
                    JOIN mw_project_collaborators pc ON pc.project_id = p.id
                    WHERE pc.user_id = $1 AND pc.status = 'active' AND p.status = $2
                    ORDER BY p.updated_at DESC
                    """,
                    user_id, status,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT p.*, pc.role AS collaborator_role,
                           (SELECT COUNT(*) FROM mw_threads WHERE project_id = p.id) as chat_count
                    FROM mw_projects p
                    JOIN mw_project_collaborators pc ON pc.project_id = p.id
                    WHERE pc.user_id = $1 AND pc.status = 'active'
                    ORDER BY p.updated_at DESC
                    """,
                    user_id,
                )
        else:
            filters = ["p.company_id = $1"]
            args: list = [company_id]
            if status:
                args.append(status)
                filters.append(f"p.status = ${len(args)}")
            if hiring_client_id is not None:
                args.append(hiring_client_id)
                filters.append(f"p.hiring_client_id = ${len(args)}")
            rows = await conn.fetch(
                f"""
                SELECT p.*,
                       rc.name AS hiring_client_name,
                       (SELECT COUNT(*) FROM mw_threads WHERE project_id = p.id) as chat_count
                FROM mw_projects p
                LEFT JOIN recruiting_clients rc ON rc.id = p.hiring_client_id
                WHERE {' AND '.join(filters)}
                ORDER BY p.updated_at DESC
                """,
                *args,
            )
    results = []
    for r in rows:
        p = _parse_project(r)
        if "collaborator_role" in r.keys():
            p["collaborator_role"] = r["collaborator_role"]
        if "hiring_client_name" in r.keys():
            p["hiring_client_name"] = r["hiring_client_name"]
        results.append(p)
    return results


async def update_project(project_id: UUID, updates: dict) -> dict:
    async with get_connection() as conn:
        allowed = {"title", "is_pinned", "status", "hiring_client_id"}
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
    return _parse_project(row)


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
    return _parse_project(row)


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
    if section.get("diagram_data"):
        new_section["diagram_data"] = section["diagram_data"]
    sections.append(new_section)
    result = await _update_sections(project_id, sections)
    return {"section": new_section, **result}


async def update_section(project_id: UUID, section_id: str, updates: dict) -> dict:
    sections = await get_sections(project_id)
    for i, s in enumerate(sections):
        if s.get("id") == section_id:
            merged = {**s}
            if "title" in updates:
                merged["title"] = updates["title"]
            if "content" in updates:
                merged["content"] = updates["content"]
            if "diagram_data" in updates:
                merged["diagram_data"] = updates["diagram_data"]
            sections[i] = merged
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

        # Seed initial thread state for recruiting projects so the AI
        # infers skill="project" from the first message instead of "chat"
        project_row = await conn.fetchrow(
            "SELECT project_type, title FROM mw_projects WHERE id = $1", project_id
        )
        initial_state = '{}'
        if project_row and project_row["project_type"] == 'recruiting':
            initial_state = json.dumps({
                "project_title": project_row["title"],
                "project_sections": [],
            })

        row = await conn.fetchrow(
            """
            INSERT INTO mw_threads (company_id, created_by, title, project_id, current_state)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            RETURNING id, title, status, version, created_at, updated_at, is_pinned,
                      node_mode, compliance_mode, payer_mode, project_id
            """,
            company_id, user_id, title, project_id, initial_state,
        )
        # Update project timestamp
        await conn.execute(
            "UPDATE mw_projects SET updated_at = NOW() WHERE id = $1", project_id
        )
    return dict(row)


# ── Recruiting-specific operations ──


async def update_project_data(project_id: UUID, updates: dict) -> dict:
    """Merge updates into project_data JSONB with row lock."""
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE", project_id
            )
            data = row["project_data"] if isinstance(row["project_data"], dict) else json.loads(row["project_data"] or "{}")
            data.update(updates)
            result = await conn.fetchrow(
                "UPDATE mw_projects SET project_data = $1::jsonb, updated_at = NOW() WHERE id = $2 RETURNING *",
                json.dumps(data), project_id,
            )
    return _parse_project(result)


async def add_candidates_to_project(project_id: UUID, new_candidates: list[dict]) -> dict:
    """Append candidates to project_data.candidates with row lock."""
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE", project_id
            )
            data = row["project_data"] if isinstance(row["project_data"], dict) else json.loads(row["project_data"] or "{}")
            existing = data.get("candidates") or []
            data["candidates"] = existing + new_candidates
            result = await conn.fetchrow(
                "UPDATE mw_projects SET project_data = $1::jsonb, updated_at = NOW() WHERE id = $2 RETURNING *",
                json.dumps(data), project_id,
            )
    return _parse_project(result)


async def toggle_shortlist(project_id: UUID, candidate_id: str) -> dict:
    """Add or remove a candidate from the shortlist with row lock."""
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE", project_id
            )
            data = row["project_data"] if isinstance(row["project_data"], dict) else json.loads(row["project_data"] or "{}")
            shortlist = set(data.get("shortlist_ids") or [])
            if candidate_id in shortlist:
                shortlist.discard(candidate_id)
            else:
                shortlist.add(candidate_id)
            data["shortlist_ids"] = list(shortlist)
            result = await conn.fetchrow(
                "UPDATE mw_projects SET project_data = $1::jsonb, updated_at = NOW() WHERE id = $2 RETURNING *",
                json.dumps(data), project_id,
            )
    return _parse_project(result)


async def toggle_dismiss(project_id: UUID, candidate_id: str) -> dict:
    """Add or remove a candidate from the dismissed list with row lock."""
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE", project_id
            )
            data = row["project_data"] if isinstance(row["project_data"], dict) else json.loads(row["project_data"] or "{}")
            dismissed = set(data.get("dismissed_ids") or [])
            if candidate_id in dismissed:
                dismissed.discard(candidate_id)
            else:
                dismissed.add(candidate_id)
            data["dismissed_ids"] = list(dismissed)
            result = await conn.fetchrow(
                "UPDATE mw_projects SET project_data = $1::jsonb, updated_at = NOW() WHERE id = $2 RETURNING *",
                json.dumps(data), project_id,
            )
    return _parse_project(result)


# ── Collaborator operations ──


async def get_project_as_collaborator(project_id: UUID, user_id: UUID) -> Optional[tuple[dict, str]]:
    """Get a project if the user is an active collaborator. Returns (project, role) or None."""
    async with get_connection() as conn:
        collab = await conn.fetchrow(
            """
            SELECT role FROM mw_project_collaborators
            WHERE project_id = $1 AND user_id = $2 AND status = 'active'
            """,
            project_id, user_id,
        )
        if not collab:
            return None
        row = await conn.fetchrow("SELECT * FROM mw_projects WHERE id = $1", project_id)
        if not row:
            return None
        project = _parse_project(row)
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
        project["collaborator_role"] = collab["role"]
    return project, collab["role"]


async def list_collaborators(project_id: UUID) -> list[dict]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT pc.user_id, pc.role, pc.created_at,
                   COALESCE(a.name, u.email) AS name,
                   u.email, u.avatar_url
            FROM mw_project_collaborators pc
            JOIN users u ON u.id = pc.user_id
            LEFT JOIN admins a ON a.user_id = pc.user_id
            WHERE pc.project_id = $1 AND pc.status = 'active'
            ORDER BY pc.created_at ASC
            """,
            project_id,
        )
    return [dict(r) for r in rows]


async def add_collaborator(project_id: UUID, user_id: UUID, invited_by: UUID) -> list[dict]:
    """Add a user as a collaborator. Returns updated collaborator list."""
    async with get_connection() as conn:
        target = await conn.fetchrow(
            "SELECT id FROM users WHERE id = $1 AND is_active = true",
            user_id,
        )
        if not target:
            raise ValueError("User not found")
        await conn.execute(
            """
            INSERT INTO mw_project_collaborators (project_id, user_id, invited_by, role)
            VALUES ($1, $2, $3, 'collaborator')
            ON CONFLICT (project_id, user_id) DO UPDATE SET status = 'active'
            """,
            project_id, user_id, invited_by,
        )
    return await list_collaborators(project_id)


async def remove_collaborator(project_id: UUID, user_id: UUID, removed_by: UUID) -> list[dict]:
    """Remove a collaborator. Only the owner can remove. Cannot remove the owner."""
    async with get_connection() as conn:
        # Check that remover is the owner
        remover = await conn.fetchrow(
            "SELECT role FROM mw_project_collaborators WHERE project_id = $1 AND user_id = $2 AND status = 'active'",
            project_id, removed_by,
        )
        if not remover or remover["role"] != "owner":
            raise PermissionError("Only the project owner can remove collaborators")
        # Cannot remove the owner
        target = await conn.fetchrow(
            "SELECT role FROM mw_project_collaborators WHERE project_id = $1 AND user_id = $2 AND status = 'active'",
            project_id, user_id,
        )
        if not target:
            raise ValueError("User is not a collaborator on this project")
        if target["role"] == "owner":
            raise PermissionError("Cannot remove the project owner")
        await conn.execute(
            "UPDATE mw_project_collaborators SET status = 'removed' WHERE project_id = $1 AND user_id = $2",
            project_id, user_id,
        )
    return await list_collaborators(project_id)


async def search_admin_users(query: str, exclude_user_id: UUID) -> list[dict]:
    """Search admin users by name or email for the invite picker."""
    async with get_connection() as conn:
        pattern = f"%{query}%"
        rows = await conn.fetch(
            """
            SELECT u.id AS user_id, u.email, u.avatar_url,
                   COALESCE(a.name, u.email) AS name
            FROM users u
            JOIN admins a ON a.user_id = u.id
            WHERE u.id != $1
              AND u.is_active = true
              AND (a.name ILIKE $2 OR u.email ILIKE $2)
            ORDER BY u.email
            LIMIT 10
            """,
            exclude_user_id, pattern,
        )
    return [dict(r) for r in rows]
