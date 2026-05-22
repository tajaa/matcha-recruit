"""Journal service — CRUD + access control for `mw_journals`.

Mirrors `project_service` shapes. A journal is visible to its `created_by`
user OR any active row in `mw_journal_collaborators`. All write operations
require active membership; entry edits require either authoring the entry
or being the journal creator.
"""

import logging
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from ...database import get_connection

logger = logging.getLogger(__name__)


def _parse_journal(row) -> dict:
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "description": row["description"],
        "color": row["color"],
        "icon": row["icon"],
        "status": row["status"],
        "created_by": str(row["created_by"]),
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        "entry_count": row["entry_count"] if "entry_count" in row.keys() else None,
        "collaborator_count": (
            row["collaborator_count"] if "collaborator_count" in row.keys() else None
        ),
        "collaborator_role": (
            row["collaborator_role"] if "collaborator_role" in row.keys() else None
        ),
    }


def _parse_entry(row) -> dict:
    return {
        "id": str(row["id"]),
        "journal_id": str(row["journal_id"]),
        "author_id": str(row["author_id"]),
        "title": row["title"],
        "content": row["content"],
        "entry_date": row["entry_date"].isoformat() if row["entry_date"] else None,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


# ── Visibility ──────────────────────────────────────────────────────────


async def _has_access(conn, journal_id: UUID, user_id: UUID) -> bool:
    """True if user is creator OR active collaborator on the journal."""
    return await conn.fetchval(
        """
        SELECT EXISTS(
            SELECT 1 FROM mw_journals j
            WHERE j.id = $1
              AND (
                  j.created_by = $2
                  OR EXISTS(
                      SELECT 1 FROM mw_journal_collaborators
                      WHERE journal_id = $1 AND user_id = $2 AND status = 'active'
                  )
              )
        )
        """,
        journal_id, user_id,
    )


async def _is_creator(conn, journal_id: UUID, user_id: UUID) -> bool:
    return await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM mw_journals WHERE id = $1 AND created_by = $2)",
        journal_id, user_id,
    )


# ── Journals ────────────────────────────────────────────────────────────


async def list_journals(user_id: UUID, company_id: Optional[UUID], status: str = "active") -> list[dict]:
    """Journals visible to the user in the given status bucket (default
    active). Includes entry + collaborator counts for the sidebar summary."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT j.id, j.title, j.description, j.color, j.icon, j.status,
                   j.created_by, j.created_at, j.updated_at,
                   (SELECT COUNT(*) FROM mw_journal_entries WHERE journal_id = j.id) AS entry_count,
                   (SELECT COUNT(*) FROM mw_journal_collaborators
                       WHERE journal_id = j.id AND status = 'active') AS collaborator_count,
                   (SELECT role FROM mw_journal_collaborators
                       WHERE journal_id = j.id AND user_id = $1 AND status = 'active') AS collaborator_role
            FROM mw_journals j
            WHERE j.status = $2
              AND (
                  j.created_by = $1
                  OR EXISTS(
                      SELECT 1 FROM mw_journal_collaborators
                      WHERE journal_id = j.id AND user_id = $1 AND status = 'active'
                  )
              )
            ORDER BY j.updated_at DESC
            """,
            user_id, status,
        )
        return [_parse_journal(r) for r in rows]


async def unarchive_journal(journal_id: UUID, user_id: UUID) -> None:
    """Restore an archived journal (owner only)."""
    async with get_connection() as conn:
        owner = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM mw_journals WHERE id = $1 AND created_by = $2)",
            journal_id, user_id,
        )
        if not owner:
            raise PermissionError("Only the owner can restore this journal")
        await conn.execute(
            "UPDATE mw_journals SET status = 'active', updated_at = NOW() WHERE id = $1",
            journal_id,
        )


async def get_journal(journal_id: UUID, viewer_id: UUID) -> Optional[dict]:
    async with get_connection() as conn:
        if not await _has_access(conn, journal_id, viewer_id):
            return None
        row = await conn.fetchrow(
            """
            SELECT j.id, j.title, j.description, j.color, j.icon, j.status,
                   j.created_by, j.created_at, j.updated_at,
                   (SELECT COUNT(*) FROM mw_journal_entries WHERE journal_id = j.id) AS entry_count,
                   (SELECT COUNT(*) FROM mw_journal_collaborators
                       WHERE journal_id = j.id AND status = 'active') AS collaborator_count,
                   (SELECT role FROM mw_journal_collaborators
                       WHERE journal_id = j.id AND user_id = $2 AND status = 'active') AS collaborator_role
            FROM mw_journals j
            WHERE j.id = $1
            """,
            journal_id, viewer_id,
        )
        return _parse_journal(row) if row else None


async def create_journal(
    creator_id: UUID,
    company_id: UUID,
    *,
    title: str,
    description: Optional[str] = None,
    color: Optional[str] = None,
    icon: Optional[str] = None,
) -> dict:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO mw_journals (company_id, created_by, title, description, color, icon)
            VALUES ($1, $2, COALESCE(NULLIF($3, ''), 'Untitled Journal'), $4, $5, $6)
            RETURNING id, title, description, color, icon, status,
                      created_by, created_at, updated_at
            """,
            company_id, creator_id, title, description, color, icon,
        )
        return _parse_journal(row)


async def update_journal(journal_id: UUID, viewer_id: UUID, patch: dict) -> dict:
    """Owner-only metadata edit (title/description/color/icon)."""
    async with get_connection() as conn:
        if not await _is_creator(conn, journal_id, viewer_id):
            raise PermissionError("Only the journal creator can update metadata")
        sets, params = [], []
        idx = 1
        for k in ("title", "description", "color", "icon"):
            if k in patch and patch[k] is not None:
                sets.append(f"{k} = ${idx}")
                params.append(patch[k])
                idx += 1
        if not sets:
            row = await conn.fetchrow(
                "SELECT id, title, description, color, icon, status, "
                "created_by, created_at, updated_at FROM mw_journals WHERE id = $1",
                journal_id,
            )
            return _parse_journal(row) if row else {}
        sets.append("updated_at = NOW()")
        params.append(journal_id)
        row = await conn.fetchrow(
            f"""
            UPDATE mw_journals
            SET {", ".join(sets)}
            WHERE id = ${idx}
            RETURNING id, title, description, color, icon, status,
                      created_by, created_at, updated_at
            """,
            *params,
        )
        return _parse_journal(row)


async def archive_journal(journal_id: UUID, viewer_id: UUID) -> None:
    async with get_connection() as conn:
        if not await _is_creator(conn, journal_id, viewer_id):
            raise PermissionError("Only the journal creator can archive")
        await conn.execute(
            "UPDATE mw_journals SET status = 'archived', updated_at = NOW() WHERE id = $1",
            journal_id,
        )


async def delete_journal_permanent(journal_id: UUID, viewer_id: UUID) -> None:
    """Hard-delete a journal. Entries + collaborators cascade via FK."""
    async with get_connection() as conn:
        if not await _is_creator(conn, journal_id, viewer_id):
            raise PermissionError("Only the journal creator can delete")
        await conn.execute("DELETE FROM mw_journals WHERE id = $1", journal_id)


# ── Entries ─────────────────────────────────────────────────────────────


async def list_entries(
    journal_id: UUID, viewer_id: UUID, *, limit: int = 50, before: Optional[datetime] = None
) -> list[dict]:
    async with get_connection() as conn:
        if not await _has_access(conn, journal_id, viewer_id):
            return []
        if before is not None:
            rows = await conn.fetch(
                """
                SELECT id, journal_id, author_id, title, content, entry_date,
                       created_at, updated_at
                FROM mw_journal_entries
                WHERE journal_id = $1 AND created_at < $2
                ORDER BY entry_date DESC, created_at DESC
                LIMIT $3
                """,
                journal_id, before, limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, journal_id, author_id, title, content, entry_date,
                       created_at, updated_at
                FROM mw_journal_entries
                WHERE journal_id = $1
                ORDER BY entry_date DESC, created_at DESC
                LIMIT $2
                """,
                journal_id, limit,
            )
        return [_parse_entry(r) for r in rows]


async def create_entry(
    journal_id: UUID,
    author_id: UUID,
    *,
    title: Optional[str] = None,
    content: str = "",
    entry_date: Optional[date] = None,
) -> dict:
    async with get_connection() as conn:
        if not await _has_access(conn, journal_id, author_id):
            raise PermissionError("Not a member of this journal")
        # Bump journal updated_at so list ordering reflects activity.
        await conn.execute(
            "UPDATE mw_journals SET updated_at = NOW() WHERE id = $1", journal_id,
        )
        row = await conn.fetchrow(
            """
            INSERT INTO mw_journal_entries (journal_id, author_id, title, content, entry_date)
            VALUES ($1, $2, $3, $4, COALESCE($5, CURRENT_DATE))
            RETURNING id, journal_id, author_id, title, content, entry_date,
                      created_at, updated_at
            """,
            journal_id, author_id, title, content, entry_date,
        )
        return _parse_entry(row)


async def update_entry(entry_id: UUID, viewer_id: UUID, patch: dict) -> dict:
    """Author of the entry OR journal creator may edit."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT e.id, e.journal_id, e.author_id, j.created_by AS journal_creator
            FROM mw_journal_entries e JOIN mw_journals j ON j.id = e.journal_id
            WHERE e.id = $1
            """,
            entry_id,
        )
        if row is None:
            raise PermissionError("Entry not found")
        if row["author_id"] != viewer_id and row["journal_creator"] != viewer_id:
            raise PermissionError("Only the entry author or journal creator can edit")
        sets, params = [], []
        idx = 1
        for k in ("title", "content", "entry_date"):
            if k in patch:
                sets.append(f"{k} = ${idx}")
                params.append(patch[k])
                idx += 1
        if not sets:
            row2 = await conn.fetchrow(
                "SELECT id, journal_id, author_id, title, content, entry_date, "
                "created_at, updated_at FROM mw_journal_entries WHERE id = $1",
                entry_id,
            )
            return _parse_entry(row2)
        sets.append("updated_at = NOW()")
        params.append(entry_id)
        row2 = await conn.fetchrow(
            f"""
            UPDATE mw_journal_entries
            SET {", ".join(sets)}
            WHERE id = ${idx}
            RETURNING id, journal_id, author_id, title, content, entry_date,
                      created_at, updated_at
            """,
            *params,
        )
        return _parse_entry(row2)


async def delete_entry(entry_id: UUID, viewer_id: UUID) -> None:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT e.author_id, j.created_by AS journal_creator
            FROM mw_journal_entries e JOIN mw_journals j ON j.id = e.journal_id
            WHERE e.id = $1
            """,
            entry_id,
        )
        if row is None:
            return
        if row["author_id"] != viewer_id and row["journal_creator"] != viewer_id:
            raise PermissionError("Only the entry author or journal creator can delete")
        await conn.execute("DELETE FROM mw_journal_entries WHERE id = $1", entry_id)


# ── Collaborators ───────────────────────────────────────────────────────


async def list_collaborators(journal_id: UUID, viewer_id: UUID) -> list[dict]:
    async with get_connection() as conn:
        if not await _has_access(conn, journal_id, viewer_id):
            return []
        rows = await conn.fetch(
            """
            SELECT u.id AS user_id,
                   COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name,
                   u.email,
                   u.avatar_url,
                   jc.role,
                   jc.created_at
            FROM mw_journal_collaborators jc
            JOIN users u ON u.id = jc.user_id
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE jc.journal_id = $1 AND jc.status = 'active'
            ORDER BY jc.created_at ASC
            """,
            journal_id,
        )
        return [
            {
                "user_id": str(r["user_id"]),
                "name": r["name"],
                "email": r["email"],
                "avatar_url": r["avatar_url"],
                "role": r["role"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]


async def add_collaborator(journal_id: UUID, user_id: UUID, invited_by: UUID) -> None:
    async with get_connection() as conn:
        if not await _is_creator(conn, journal_id, invited_by):
            raise PermissionError("Only the journal creator can add collaborators")
        await conn.execute(
            """
            INSERT INTO mw_journal_collaborators (journal_id, user_id, invited_by, role, status)
            VALUES ($1, $2, $3, 'collaborator', 'active')
            ON CONFLICT (journal_id, user_id)
            DO UPDATE SET status = 'active', invited_by = EXCLUDED.invited_by
            """,
            journal_id, user_id, invited_by,
        )
        jrow = await conn.fetchrow(
            "SELECT company_id, title FROM mw_journals WHERE id = $1", journal_id,
        )
        inviter = await conn.fetchrow(
            """
            SELECT COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name
            FROM users u
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE u.id = $1
            """, invited_by,
        )

    # Notify the new collaborator (best-effort — never fail the add). Surfaces
    # in the desktop bell; metadata.journal_id drives tap-to-navigate.
    if jrow is not None and user_id != invited_by:
        inviter_name = (inviter["name"] if inviter and inviter["name"] else "Someone")
        title = jrow["title"] or "a journal"
        try:
            from . import notification_service as notif_svc
            await notif_svc.create_notification(
                user_id=user_id,
                company_id=jrow["company_id"],
                type="journal_invite",
                title=f"Added to journal: {title}",
                body=f"{inviter_name} shared “{title}” with you.",
                link="/work",
                metadata={"journal_id": str(journal_id), "invited_by": str(invited_by)},
                send_email=True,
                email_subject=f"You were added to “{title}”",
            )
        except Exception as e:
            logger.warning("Failed to create journal invite notification %s -> %s: %s",
                           journal_id, user_id, e)


async def remove_collaborator(journal_id: UUID, user_id: UUID, removed_by: UUID) -> None:
    async with get_connection() as conn:
        if not await _is_creator(conn, journal_id, removed_by):
            raise PermissionError("Only the journal creator can remove collaborators")
        await conn.execute(
            "DELETE FROM mw_journal_collaborators WHERE journal_id = $1 AND user_id = $2",
            journal_id, user_id,
        )
