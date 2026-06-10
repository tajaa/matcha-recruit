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

# Create-time templates. `kind` is stored on the journal; if a kind ships a
# `seed`, a starter entry is inserted so the writer opens to a scaffold instead
# of a blank page. `icon` is a sensible default when the create form didn't pick
# one. Keep kinds in sync with the desktop NewJournalSheet picker + the
# `mw_journals.kind` column comment.
JOURNAL_KINDS = {"journal", "note", "blog", "todo", "novel", "screenplay"}

JOURNAL_KIND_DEFAULTS: dict[str, dict] = {
    "journal": {"icon": "book.closed"},
    "note":    {"icon": "note.text"},
    "blog":    {"icon": "doc.richtext"},
    "todo":    {"icon": "checklist"},
    "novel":   {"icon": "books.vertical"},
    "screenplay": {"icon": "film"},
}

# Starter-entry scaffolds (markdown, matching the journal editor's syntax).
JOURNAL_KIND_SEEDS: dict[str, dict] = {
    "blog": {
        "title": "Untitled post",
        "content": (
            "# Working title\n\n"
            "_One-line hook — why should a reader care?_\n\n"
            "## Introduction\n\n"
            "## Key points\n\n- \n- \n- \n\n"
            "## Conclusion\n\n"
            "**Call to action:** \n"
        ),
    },
    "todo": {
        "title": "To-dos",
        "content": (
            "## Today\n\n- [ ] \n- [ ] \n- [ ] \n\n"
            "## This week\n\n- [ ] \n- [ ] \n\n"
            "## Someday\n\n- [ ] \n"
        ),
    },
    "novel": {
        "title": "Chapter 1",
        "content": (
            "# Chapter 1\n\n"
            "> Notes: POV, setting, what changes by the end.\n\n"
            "---\n\n"
            "The opening line.\n"
        ),
    },
    # Screenplay seeds VALID FOUNTAIN (not markdown) — the desktop screenplay
    # editor parses `content` as Fountain. Title page = key:value lines at the
    # very top followed by a blank line; then sluglines (INT./EXT.), action,
    # CHARACTER cues, dialogue, and TO:-terminated transitions.
    "screenplay": {
        "title": None,
        "content": (
            "Title: Untitled\n"
            "Credit: Written by\n"
            "Author: \n"
            "Draft date: \n"
            "\n"
            "INT. LOCATION - DAY\n"
            "\n"
            "Action describing the scene.\n"
            "\n"
            "CHARACTER\n"
            "Their first line of dialogue.\n"
            "\n"
            "CUT TO:\n"
        ),
    },
}


def _normalize_kind(kind: Optional[str]) -> str:
    # Default to `note`: every journal is now a single-document note (Evernote
    # model). The `journal` (diary) kind is no longer minted — it's kept in
    # JOURNAL_KINDS only so any pre-migration row still validates on update.
    k = (kind or "note").lower().strip()
    return k if k in JOURNAL_KINDS else "note"


# Fountain title-page key lines to skip when building a note-list preview.
_FOUNTAIN_TP_KEYS = (
    "title:", "credit:", "author:", "authors:", "source:",
    "draft date:", "date:", "contact:", "notes:", "copyright:",
)


def _preview(text: Optional[str], limit: int = 140) -> Optional[str]:
    """A one-line snippet of a journal's body for the Notes-style list — first
    non-empty content, with light markdown/fountain markers stripped."""
    if not text:
        return None
    parts: list[str] = []
    total = 0
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.lower().startswith(_FOUNTAIN_TP_KEYS):
            continue  # skip Fountain title-page lines
        line = line.lstrip("#>=-*• \t").strip()
        for chk in ("[ ]", "[x]", "[X]"):
            if line.startswith(chk):
                line = line[len(chk):].strip()
        line = line.replace("**", "").replace("`", "").replace("==", "").replace("~~", "")
        if not line:
            continue
        parts.append(line)
        total += len(line)
        if total >= limit:
            break
    s = " ".join(parts).strip()
    if not s:
        return None
    return s[:limit] + "…" if len(s) > limit else s


def _parse_journal(row) -> dict:
    keys = row.keys()
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "description": row["description"],
        "color": row["color"],
        "icon": row["icon"],
        "status": row["status"],
        "kind": row["kind"] if "kind" in keys else "journal",
        "folder_id": (
            str(row["folder_id"]) if "folder_id" in keys and row["folder_id"] else None
        ),
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
        "preview": (
            _preview(row["preview_raw"]) if "preview_raw" in row.keys() else None
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
                   j.kind, j.folder_id, j.created_by, j.created_at, j.updated_at,
                   (SELECT COUNT(*) FROM mw_journal_entries WHERE journal_id = j.id) AS entry_count,
                   (SELECT COUNT(*) FROM mw_journal_collaborators
                       WHERE journal_id = j.id AND status = 'active') AS collaborator_count,
                   (SELECT role FROM mw_journal_collaborators
                       WHERE journal_id = j.id AND user_id = $1 AND status = 'active') AS collaborator_role,
                   (SELECT e.content FROM mw_journal_entries e
                       WHERE e.journal_id = j.id
                       ORDER BY e.updated_at DESC, e.created_at DESC
                       LIMIT 1) AS preview_raw
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
                   j.kind, j.folder_id, j.created_by, j.created_at, j.updated_at,
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


async def _ensure_default_folder(conn, company_id: UUID, creator_id: UUID) -> UUID:
    """Return the company's default root "Notes" notebook, creating it if
    missing. Evernote model: every note lives in a notebook, so unfiled new
    notes land here. Idempotent on (company_id, parent_id IS NULL, name)."""
    existing = await conn.fetchval(
        """
        SELECT id FROM mw_journal_folders
        WHERE company_id = $1 AND parent_id IS NULL AND name = 'Notes'
        LIMIT 1
        """,
        company_id,
    )
    if existing is not None:
        return existing
    return await conn.fetchval(
        """
        INSERT INTO mw_journal_folders (company_id, parent_id, name, created_by)
        VALUES ($1, NULL, 'Notes', $2)
        RETURNING id
        """,
        company_id, creator_id,
    )


async def create_journal(
    creator_id: UUID,
    company_id: UUID,
    *,
    title: str,
    description: Optional[str] = None,
    color: Optional[str] = None,
    icon: Optional[str] = None,
    kind: Optional[str] = None,
    folder_id: Optional[UUID] = None,
) -> dict:
    kind = _normalize_kind(kind)
    # Fall back to the kind's default icon when the form didn't pick one.
    if not icon:
        icon = JOURNAL_KIND_DEFAULTS.get(kind, {}).get("icon")
    async with get_connection() as conn:
        # A folder, if given, must belong to the same company; otherwise file
        # the new note into the default "Notes" notebook (Evernote model — no
        # truly-unfiled notes from create; the note menu's "Move to → None"
        # still allows un-filing after the fact).
        if folder_id is not None:
            ok = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM mw_journal_folders WHERE id = $1 AND company_id = $2)",
                folder_id, company_id,
            )
            if not ok:
                folder_id = None
        if folder_id is None:
            folder_id = await _ensure_default_folder(conn, company_id, creator_id)
        row = await conn.fetchrow(
            """
            INSERT INTO mw_journals (company_id, created_by, title, description, color, icon, kind, folder_id)
            VALUES ($1, $2, COALESCE(NULLIF($3, ''), 'Untitled Journal'), $4, $5, $6, $7, $8)
            RETURNING id, title, description, color, icon, status, kind, folder_id,
                      created_by, created_at, updated_at
            """,
            company_id, creator_id, title, description, color, icon, kind, folder_id,
        )
        journal = _parse_journal(row)
        # Seed a starter entry so writers open to a scaffold, not a blank page.
        seed = JOURNAL_KIND_SEEDS.get(kind)
        if seed:
            await conn.execute(
                """
                INSERT INTO mw_journal_entries (journal_id, author_id, title, content)
                VALUES ($1, $2, $3, $4)
                """,
                UUID(journal["id"]), creator_id, seed.get("title"), seed.get("content", ""),
            )
        return journal


async def update_journal(journal_id: UUID, viewer_id: UUID, patch: dict) -> dict:
    """Owner-only edit: title/description/color/icon/kind + folder placement.

    `folder_id` is handled specially so an explicit null moves the journal to
    the root of the hub (the simple loop below skips Nones, which is correct for
    the other fields but would block un-foldering)."""
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
        if "kind" in patch and patch["kind"] is not None:
            sets.append(f"kind = ${idx}")
            params.append(_normalize_kind(patch["kind"]))
            idx += 1
        # folder move — present-but-null = move to root; validate same-company.
        if "folder_id" in patch:
            target = patch["folder_id"]
            if target is not None:
                fid = target if isinstance(target, UUID) else UUID(str(target))
                ok = await conn.fetchval(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM mw_journal_folders f
                        JOIN mw_journals j ON j.id = $2
                        WHERE f.id = $1 AND f.company_id = j.company_id
                    )
                    """,
                    fid, journal_id,
                )
                if not ok:
                    raise PermissionError("Folder not found in this workspace")
                sets.append(f"folder_id = ${idx}")
                params.append(fid)
            else:
                sets.append("folder_id = NULL")
        if not sets:
            row = await conn.fetchrow(
                "SELECT id, title, description, color, icon, status, kind, folder_id, "
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
            WHERE id = ${len(params)}
            RETURNING id, title, description, color, icon, status, kind, folder_id,
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
        # Bump the parent journal so the Notes-style list re-sorts by recent edit.
        await conn.execute(
            "UPDATE mw_journals SET updated_at = NOW() WHERE id = $1", row["journal_id"],
        )
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


# ── Folders (Obsidian-style hub organization) ───────────────────────────
#
# Company-scoped adjacency-list tree (mirrors mw_project_folders). Journals
# carry a single `folder_id` placement; deleting a folder cascades to child
# folders and SET-NULLs the journals back to the hub root.


def _parse_folder(row) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "parent_id": str(row["parent_id"]) if row["parent_id"] else None,
        "created_by": str(row["created_by"]) if row["created_by"] else None,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "color": row["color"] if "color" in row.keys() else None,
    }


async def list_journal_folders(company_id: UUID) -> list[dict]:
    """The full folder tree for the company (flat list; client builds the
    hierarchy from parent_id)."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, parent_id, created_by, created_at, color
            FROM mw_journal_folders
            WHERE company_id = $1
            ORDER BY name ASC
            """,
            company_id,
        )
        return [_parse_folder(r) for r in rows]


async def create_journal_folder(
    creator_id: UUID, company_id: UUID, *, name: str,
    parent_id: Optional[UUID] = None, color: Optional[str] = None,
) -> dict:
    async with get_connection() as conn:
        if parent_id is not None:
            ok = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM mw_journal_folders WHERE id = $1 AND company_id = $2)",
                parent_id, company_id,
            )
            if not ok:
                raise PermissionError("Parent folder not found in this workspace")
        row = await conn.fetchrow(
            """
            INSERT INTO mw_journal_folders (company_id, parent_id, name, created_by, color)
            VALUES ($1, $2, COALESCE(NULLIF($3, ''), 'New Folder'), $4, $5)
            RETURNING id, name, parent_id, created_by, created_at, color
            """,
            company_id, parent_id, name, creator_id, color,
        )
        return _parse_folder(row)


async def _is_descendant(conn, folder_id: UUID, maybe_ancestor: UUID) -> bool:
    """True if `maybe_ancestor` is folder_id itself or sits below it — used to
    reject reparenting a folder into its own subtree (which would orphan a
    cycle)."""
    cur = maybe_ancestor
    seen = set()
    while cur is not None and cur not in seen:
        if cur == folder_id:
            return True
        seen.add(cur)
        cur = await conn.fetchval(
            "SELECT parent_id FROM mw_journal_folders WHERE id = $1", cur,
        )
    return False


async def update_journal_folder(
    folder_id: UUID, company_id: UUID, patch: dict
) -> dict:
    """Rename and/or reparent a folder (company-scoped). Guards against moving a
    folder into its own subtree."""
    async with get_connection() as conn:
        owned = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM mw_journal_folders WHERE id = $1 AND company_id = $2)",
            folder_id, company_id,
        )
        if not owned:
            raise PermissionError("Folder not found in this workspace")
        sets, params = [], []
        if "name" in patch and patch["name"]:
            params.append(patch["name"])
            sets.append(f"name = ${len(params)}")
        if "color" in patch and patch["color"] is not None:
            params.append(patch["color"])
            sets.append(f"color = ${len(params)}")
        if "parent_id" in patch:
            target = patch["parent_id"]
            if target is not None:
                pid = target if isinstance(target, UUID) else UUID(str(target))
                ok = await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM mw_journal_folders WHERE id = $1 AND company_id = $2)",
                    pid, company_id,
                )
                if not ok:
                    raise PermissionError("Parent folder not found in this workspace")
                if await _is_descendant(conn, folder_id, pid):
                    raise PermissionError("Cannot move a folder into its own subtree")
                params.append(pid)
                sets.append(f"parent_id = ${len(params)}")
            else:
                sets.append("parent_id = NULL")
        if not sets:
            row = await conn.fetchrow(
                "SELECT id, name, parent_id, created_by, created_at, color "
                "FROM mw_journal_folders WHERE id = $1", folder_id,
            )
            return _parse_folder(row)
        params.append(folder_id)
        row = await conn.fetchrow(
            f"""
            UPDATE mw_journal_folders SET {", ".join(sets)}
            WHERE id = ${len(params)}
            RETURNING id, name, parent_id, created_by, created_at, color
            """,
            *params,
        )
        return _parse_folder(row)


async def delete_journal_folder(folder_id: UUID, company_id: UUID) -> None:
    """Delete a folder. Child folders cascade; journals filed here SET NULL
    back to the hub root (FK on mw_journals.folder_id)."""
    async with get_connection() as conn:
        owned = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM mw_journal_folders WHERE id = $1 AND company_id = $2)",
            folder_id, company_id,
        )
        if not owned:
            raise PermissionError("Folder not found in this workspace")
        await conn.execute("DELETE FROM mw_journal_folders WHERE id = $1", folder_id)
