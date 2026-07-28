"""Project lifecycle: create (with per-type seeding), parse, get, list, update,
archive/unarchive, permanent delete, the locked data read/write pair, the
recruiting candidate/shortlist/dismiss operations, pinning, and admin search.
"""
import json
import logging
import re
import secrets
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from app.database import get_connection

from ._data import _parse_project
from ._config import PROJECT_TEMPLATE_SECTIONS, _ALLOWED_BLOG_TONES, _ALLOWED_PROJECT_TYPES, _slugify
from .discipline import _seed_discipline_data

logger = logging.getLogger(__name__)


def _seed_blog_data(extra_data: Optional[dict]) -> dict:
    e = extra_data or {}
    tone = e.get("tone") if e.get("tone") in _ALLOWED_BLOG_TONES else "expert-casual"
    return {
        "slug": _slugify(e.get("title") or ""),
        "excerpt": None,
        "cover_image_url": None,
        "author": e.get("author") or {},
        "audience": e.get("audience"),
        "tone": tone,
        "tags": [str(t) for t in (e.get("tags") or [])],
        "status": "draft",
        "published_at": None,
        "stats": {"word_count": 0, "read_minutes": 0},
    }


async def create_project(
    company_id: UUID,
    user_id: UUID,
    title: str = "Untitled Project",
    project_type: str = "general",
    hiring_client_id: Optional[UUID] = None,
    icon: Optional[str] = None,
    extra_data: Optional[dict] = None,
) -> dict:
    if project_type not in _ALLOWED_PROJECT_TYPES:
        raise ValueError(f"Unknown project_type '{project_type}'")
    async with get_connection() as conn:
        if hiring_client_id is not None:
            owner_check = await conn.fetchval(
                "SELECT company_id FROM recruiting_clients WHERE id = $1",
                hiring_client_id,
            )
            if owner_check != company_id:
                raise ValueError("Hiring client does not belong to this workspace")

        if project_type == "blog":
            seed_extra = dict(extra_data or {})
            seed_extra.setdefault("title", title)
            initial_project_data = _seed_blog_data(seed_extra)
        elif project_type == "discipline":
            initial_project_data = _seed_discipline_data(extra_data)
        else:
            initial_project_data = {}

        # Auto-name "New Project N" when caller passed a default. Counts
        # existing projects for this company that share the "New Project"
        # prefix and bumps the next integer. Skips numbering for blog.
        if title in (None, "", "Untitled Project", "New Project") and project_type != "blog":
            existing = await conn.fetchval(
                """
                SELECT COUNT(*) FROM mw_projects
                WHERE company_id = $1
                  AND project_type != 'blog'
                  AND (title = 'New Project' OR title ~ '^New Project [0-9]+$')
                """,
                company_id,
            )
            title = "New Project" if not existing else f"New Project {existing + 1}"

        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO mw_projects (company_id, created_by, title, project_type, hiring_client_id, project_data, icon)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
                RETURNING *
                """,
                company_id, user_id, title, project_type, hiring_client_id,
                json.dumps(initial_project_data), icon,
            )

            # Optional starter template — seed the project's `sections` JSONB
            # with a pre-defined skeleton (proposal, project_brief, etc.). The
            # bracketed-placeholder content lets the existing AI fill flow
            # auto-populate values from the user's first chat message. Lives
            # inside the same transaction as the INSERT so a partial create
            # never produces a project with the wrong sections.
            template_id = (extra_data or {}).get("template")
            if template_id and template_id in PROJECT_TEMPLATE_SECTIONS:
                now_iso = datetime.now(timezone.utc).isoformat()
                # Match the 16-hex-char ID format used by add_section
                # (`os.urandom(8).hex()`) so any code that incidentally
                # assumes a fixed length works against template-seeded rows.
                seeded_sections = [
                    {
                        "id": secrets.token_hex(8),
                        "title": s["title"],
                        "content": s["content"],
                        "source_message_id": None,
                        "content_source": "template",
                        "content_updated_at": now_iso,
                        "history": [],
                    }
                    for s in PROJECT_TEMPLATE_SECTIONS[template_id]
                ]
                await conn.execute(
                    "UPDATE mw_projects SET sections = $1::jsonb WHERE id = $2",
                    json.dumps(seeded_sections), row["id"],
                )
                # Refresh the row so the returned project includes the seed.
                row = await conn.fetchrow(
                    "SELECT * FROM mw_projects WHERE id = $1", row["id"]
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
            # Seed the creator as project owner. Critical for the admin
            # listing path which filters projects by collaborator membership
            # only — without this insert the admin cannot see the project
            # they just created.
            await conn.execute(
                """
                INSERT INTO mw_project_collaborators (project_id, user_id, invited_by, role, status)
                VALUES ($1, $2, $2, 'owner', 'active')
                ON CONFLICT (project_id, user_id) DO UPDATE SET status = 'active'
                """,
                row["id"], user_id,
            )
    project = _parse_project(row)
    project["chats"] = [dict(chat)]
    project["chat_count"] = 1
    return project


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

        # Resolve collaborator role + per-user pin for the requesting user
        if user_id:
            collab = await conn.fetchrow(
                "SELECT role FROM mw_project_collaborators WHERE project_id = $1 AND user_id = $2 AND status = 'active'",
                project_id, user_id,
            )
            project["collaborator_role"] = collab["role"] if collab else None
            user_pinned = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM mw_project_pins WHERE user_id = $1 AND project_id = $2)",
                user_id, project_id,
            )
            project["is_pinned"] = bool(user_pinned)
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
    """List projects. If company_id and user_id are both provided, lists company projects + collaborated projects."""
    async with get_connection() as conn:
        filters = []
        args = []
        
        if company_id and user_id:
            args.extend([company_id, user_id])
            filters.append(f"(p.company_id = $1 OR EXISTS (SELECT 1 FROM mw_project_collaborators pc_auth WHERE pc_auth.project_id = p.id AND pc_auth.user_id = $2 AND pc_auth.status = 'active'))")
        elif user_id:
            args.append(user_id)
            filters.append(f"EXISTS (SELECT 1 FROM mw_project_collaborators pc_auth WHERE pc_auth.project_id = p.id AND pc_auth.user_id = $1 AND pc_auth.status = 'active')")
        elif company_id:
            args.append(company_id)
            filters.append(f"p.company_id = $1")
            
        if status:
            args.append(status)
            filters.append(f"p.status = ${len(args)}")
            
        if hiring_client_id is not None:
            args.append(hiring_client_id)
            filters.append(f"p.hiring_client_id = ${len(args)}")

        where_clause = "WHERE " + " AND ".join(filters) if filters else ""
        
        # To get the collaborator_role for the user without breaking the query with parameterized joins,
        # we can just select it via a subquery in the SELECT clause if user_id is provided.
        role_subquery = ""
        pin_subquery = ""
        if user_id:
            user_arg_idx = 1 if not company_id else 2
            role_subquery = f", (SELECT role FROM mw_project_collaborators WHERE project_id = p.id AND user_id = ${user_arg_idx} AND status = 'active' LIMIT 1) AS collaborator_role"
            # Per-user pin overrides the legacy global mw_projects.is_pinned.
            pin_subquery = f", EXISTS(SELECT 1 FROM mw_project_pins WHERE user_id = ${user_arg_idx} AND project_id = p.id) AS user_pinned"

        query = f"""
            SELECT p.*,
                   rc.name AS hiring_client_name,
                   (SELECT COUNT(*) FROM mw_threads WHERE project_id = p.id) as chat_count
                   {role_subquery}
                   {pin_subquery}
            FROM mw_projects p
            LEFT JOIN recruiting_clients rc ON rc.id = p.hiring_client_id
            {where_clause}
            ORDER BY p.updated_at DESC
        """
        rows = await conn.fetch(query, *args)

        # Second pass: load active collaborators for collab-typed projects
        # in one follow-up query so the main list query stays simple. Best
        # effort — if this lookup fails, projects still render without
        # the collaborator pile.
        collabs_by_project: dict[str, list[dict]] = {}
        try:
            collab_project_ids = [
                r["id"] for r in rows
                if (r["project_type"] if "project_type" in r.keys() else None) == "collab"
            ]
            if collab_project_ids:
                pc_rows = await conn.fetch(
                    """
                    SELECT pc.project_id, pc.user_id, pc.role,
                           COALESCE(
                               c.name,
                               NULLIF(BTRIM(CONCAT(e.first_name, ' ', e.last_name)), ''),
                               a.name,
                               u.email
                           ) AS name,
                           u.email, u.avatar_url
                    FROM mw_project_collaborators pc
                    JOIN users u ON u.id = pc.user_id
                    LEFT JOIN clients c ON c.user_id = pc.user_id
                    LEFT JOIN employees e ON e.user_id = pc.user_id
                    LEFT JOIN admins a ON a.user_id = pc.user_id
                    WHERE pc.project_id = ANY($1::uuid[]) AND pc.status = 'active'
                    ORDER BY pc.role DESC, u.email
                    """,
                    collab_project_ids,
                )
                for cr in pc_rows:
                    pid = str(cr["project_id"])
                    collabs_by_project.setdefault(pid, []).append({
                        "user_id": str(cr["user_id"]),
                        "name": cr["name"],
                        "email": cr["email"],
                        "avatar_url": cr["avatar_url"],
                        "role": cr["role"],
                    })
        except Exception as exc:
            logger.warning("list_projects collaborators lookup failed: %s", exc)

    results = []
    for r in rows:
        p = _parse_project(r)
        if "collaborator_role" in r.keys():
            p["collaborator_role"] = r["collaborator_role"]
        if "hiring_client_name" in r.keys():
            p["hiring_client_name"] = r["hiring_client_name"]
        # Per-user pin overrides the global is_pinned column when caller is known.
        if "user_pinned" in r.keys():
            p["is_pinned"] = bool(r["user_pinned"])
        pid = str(p.get("id"))
        if pid in collabs_by_project:
            p["collaborators"] = collabs_by_project[pid]
        results.append(p)
    return results


async def update_project(project_id: UUID, updates: dict) -> dict:
    async with get_connection() as conn:
        async with conn.transaction():
            prior = await conn.fetchrow(
                "SELECT title, project_type, project_data FROM mw_projects WHERE id = $1 FOR UPDATE",
                project_id,
            )
            # Note: is_pinned is intentionally NOT in this set — pin is now
            # per-user via mw_project_pins. The route intercepts is_pinned
            # before calling this service. The global column on mw_projects
            # is kept for backfill/legacy reads only.
            allowed = {"title", "status", "hiring_client_id", "icon"}
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
            # Blog: re-derive slug when title changes AND current slug matches prior auto-slug
            if prior and prior["project_type"] == "blog" and "title" in updates:
                new_title = updates["title"]
                prior_title = prior["title"] or ""
                data = prior["project_data"]
                if isinstance(data, str):
                    data = json.loads(data or "{}")
                data = data or {}
                current_slug = data.get("slug") or ""
                if not current_slug or current_slug == _slugify(prior_title):
                    data["slug"] = _slugify(new_title)
                    row = await conn.fetchrow(
                        "UPDATE mw_projects SET project_data = $1::jsonb WHERE id = $2 RETURNING *",
                        json.dumps(data), project_id,
                    )

            # Collab: keep the linked discussion channel's name in sync with the
            # project title so the channels sidebar stays legible after a rename.
            if prior and prior["project_type"] == "collab" and "title" in updates:
                cdata = prior["project_data"]
                if isinstance(cdata, str):
                    try:
                        cdata = json.loads(cdata or "{}")
                    except (json.JSONDecodeError, ValueError):
                        cdata = {}
                cdata = cdata or {}
                chan_id = cdata.get("discussion_channel_id")
                new_title = (updates.get("title") or "").strip()
                if chan_id and new_title:
                    await conn.execute(
                        "UPDATE channels SET name = $1 WHERE id = $2 AND name IS DISTINCT FROM $1",
                        new_title,
                        UUID(chan_id) if isinstance(chan_id, str) else chan_id,
                    )
    return _parse_project(row)


async def archive_project(project_id: UUID):
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE mw_projects SET status = 'archived', updated_at = NOW() WHERE id = $1",
            project_id,
        )


async def unarchive_project(project_id: UUID):
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE mw_projects SET status = 'active', updated_at = NOW() WHERE id = $1 AND status = 'archived'",
            project_id,
        )


async def delete_project_permanent(project_id: UUID):
    async with get_connection() as conn:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM mw_threads WHERE project_id = $1",
                project_id,
            )
            await conn.execute(
                "DELETE FROM mw_projects WHERE id = $1",
                project_id,
            )


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


async def set_project_pin(user_id: UUID, project_id: UUID, pinned: bool) -> bool:
    """Toggle a per-user star/pin on a project. Returns the new state.

    The pin is stored in `mw_project_pins(user_id, project_id)`. Anyone
    can pin a project they can already see (caller-side authorisation
    happens in the route).
    """
    async with get_connection() as conn:
        if pinned:
            await conn.execute(
                """
                INSERT INTO mw_project_pins (user_id, project_id)
                VALUES ($1, $2)
                ON CONFLICT (user_id, project_id) DO NOTHING
                """,
                user_id, project_id,
            )
        else:
            await conn.execute(
                "DELETE FROM mw_project_pins WHERE user_id = $1 AND project_id = $2",
                user_id, project_id,
            )
    return pinned


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
