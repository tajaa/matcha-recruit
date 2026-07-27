"""Project document sections: the mutation core with its revision-history
snapshotting, plus add / update / accept / reject / delete / reorder.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from app.database import get_connection

from ._config import _HISTORY_MAX_ENTRIES, _HISTORY_SNAPSHOT_INTERVAL_SEC, _now_iso
from ._config import _compute_blog_stats
from ._data import _parse_project

logger = logging.getLogger(__name__)


# ── Section operations ──
#
# All mutating section ops go through `_mutate_sections`: acquire row lock,
# read sections, let a mutator callable produce the new list + any "extra"
# return value for the caller, then write back in the same transaction. This
# eliminates the read-modify-write race the separate get_sections / _update_sections
# pattern had. The write is skipped entirely when the new sections JSON matches
# the old — avoids version bumps and stats recompute on no-op updates.

def _sections_from_row(raw) -> list:
    if raw is None:
        return []
    return json.loads(raw) if isinstance(raw, str) else list(raw)


async def _resolve_actor_name(user_id) -> Optional[str]:
    """Display name for a user id (clients/employees/admins, email fallback).
    Mirrors the COALESCE pattern used across the matcha services. None for a
    null/unknown user."""
    if user_id is None:
        return None
    try:
        uid = user_id if isinstance(user_id, UUID) else UUID(str(user_id))
    except (TypeError, ValueError):
        return None
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name
            FROM users u
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE u.id = $1
            """,
            uid,
        )
    name = (row["name"] or "").strip() if row else ""
    return name or None


def _maybe_append_history(
    section: dict,
    prior_content: str,
    prior_source: str,
    *,
    prior_author_id: Optional[str] = None,
    prior_author_name: Optional[str] = None,
    force: bool = False,
) -> list:
    """Append a snapshot of prior_content (with the author who wrote it) to
    section['history']. Snapshots on the >5min cadence, OR immediately when
    `force` is set — used when a *different* author takes over so a contributor's
    version is never swallowed by the debounce. No-op when prior_content empty.
    Caps at _HISTORY_MAX_ENTRIES.
    """
    history = list(section.get("history") or [])
    if not prior_content:
        return history
    last_at = history[-1].get("at") if history else None
    now = datetime.now(timezone.utc)
    if not force and last_at:
        try:
            last_dt = datetime.fromisoformat(last_at)
            if (now - last_dt).total_seconds() < _HISTORY_SNAPSHOT_INTERVAL_SEC:
                return history
        except ValueError:
            pass
    history.append({
        "content": prior_content,
        "source": prior_source or "user",
        "author_id": str(prior_author_id) if prior_author_id else None,
        "author_name": prior_author_name,
        "at": now.isoformat(),
    })
    if len(history) > _HISTORY_MAX_ENTRIES:
        history = history[-_HISTORY_MAX_ENTRIES:]
    return history


async def _mutate_sections(project_id: UUID, mutator) -> tuple[dict, object]:
    """Run `mutator(sections) -> (new_sections, extra)` under a row lock.

    Returns (project_dict, extra). `extra` is whatever the mutator wants to
    hand back to its caller (e.g. the newly-inserted section object).
    When new_sections is byte-identical to the existing list, the write and
    stats recompute are skipped — the existing row is returned untouched.
    """
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT * FROM mw_projects WHERE id = $1 FOR UPDATE",
                project_id,
            )
            if row is None:
                raise ValueError(f"Project {project_id} not found")
            current = _sections_from_row(row["sections"])
            new_sections, extra = mutator(current)
            # No-op detection: same JSON encoding → skip write.
            new_json = json.dumps(new_sections)
            old_json = json.dumps(current)
            if new_json == old_json:
                return _parse_project(row), extra

            if row["project_type"] == "blog":
                data = row["project_data"]
                if isinstance(data, str):
                    data = json.loads(data or "{}")
                data = data or {}
                data["stats"] = _compute_blog_stats(new_sections)
                updated = await conn.fetchrow(
                    """
                    UPDATE mw_projects
                    SET sections = $1::jsonb, project_data = $2::jsonb,
                        version = version + 1, updated_at = NOW()
                    WHERE id = $3
                    RETURNING *
                    """,
                    new_json, json.dumps(data), project_id,
                )
            else:
                updated = await conn.fetchrow(
                    """
                    UPDATE mw_projects
                    SET sections = $1::jsonb, version = version + 1, updated_at = NOW()
                    WHERE id = $2
                    RETURNING *
                    """,
                    new_json, project_id,
                )
    return _parse_project(updated), extra


async def _update_sections(project_id: UUID, sections: list) -> dict:
    """Back-compat wrapper: replaces the full sections list atomically. Prefer
    `_mutate_sections` for read-modify-write; use this only when the caller
    has already decided on the final list (e.g. outline seeding from AI)."""
    project, _ = await _mutate_sections(project_id, lambda _prev: (sections, None))
    return project


async def get_sections(project_id: UUID) -> list:
    async with get_connection() as conn:
        raw = await conn.fetchval("SELECT sections FROM mw_projects WHERE id = $1", project_id)
    return _sections_from_row(raw)


async def add_section(project_id: UUID, section: dict) -> dict:
    new_section = {
        "id": os.urandom(8).hex(),
        "title": section.get("title"),
        "content": section.get("content", ""),
        "source_message_id": section.get("source_message_id"),
        "content_source": section.get("content_source") or "user",
        "content_updated_at": _now_iso(),
        "history": [],
    }
    if section.get("diagram_data"):
        new_section["diagram_data"] = section["diagram_data"]

    def mutate(sections):
        return ([*sections, new_section], new_section)

    project, inserted = await _mutate_sections(project_id, mutate)
    return {"section": inserted, **project}


async def update_section(
    project_id: UUID,
    section_id: str,
    updates: dict,
    *,
    actor_user_id=None,
    actor_name: Optional[str] = None,
) -> dict:
    """User-facing section update. Stamps content_source='user', records the
    editing author, and appends an author-attributed history snapshot when
    content changes (forced when a different author takes over).
    """
    source = updates.get("_source") or "user"
    actor_id_str = str(actor_user_id) if actor_user_id else None

    def mutate(sections):
        out = []
        for s in sections:
            if s.get("id") == section_id:
                merged = {**s}
                content_changed = (
                    "content" in updates and updates["content"] != s.get("content")
                )
                if content_changed:
                    prior_author_id = s.get("last_edited_by")
                    # Force a snapshot when a different author takes over, so the
                    # prior contributor's version is preserved even within 5 min.
                    force = actor_id_str is not None and actor_id_str != prior_author_id
                    merged["history"] = _maybe_append_history(
                        s,
                        s.get("content") or "",
                        s.get("content_source") or "user",
                        prior_author_id=prior_author_id,
                        prior_author_name=s.get("last_edited_by_name"),
                        force=force,
                    )
                    merged["content"] = updates["content"]
                    merged["content_source"] = source
                    merged["content_updated_at"] = _now_iso()
                    # Who wrote the now-current content — drives "Last edited by X"
                    # and the author stamp on the NEXT snapshot that displaces it.
                    merged["last_edited_by"] = actor_id_str
                    merged["last_edited_by_name"] = actor_name
                    merged["last_edited_at"] = _now_iso()
                    # Intentionally preserve pending_revision. Only
                    # accept_section_revision / reject_section_revision clear
                    # it — user edits and pending AI suggestions coexist so
                    # the banner stays actionable until the user decides.
                if "title" in updates:
                    merged["title"] = updates["title"]
                if "diagram_data" in updates:
                    merged["diagram_data"] = updates["diagram_data"]
                out.append(merged)
            else:
                out.append(s)
        return (out, None)

    project, _ = await _mutate_sections(project_id, mutate)
    return project


async def accept_section_revision(
    project_id: UUID,
    section_id: str,
    *,
    actor_user_id=None,
    actor_name: Optional[str] = None,
) -> dict:
    """Promote pending_revision → content. Snapshots the displaced content with
    its prior author, and records the accepting human as the new content's
    editor (content_source stays 'ai' since the text is AI-authored)."""
    actor_id_str = str(actor_user_id) if actor_user_id else None

    def mutate(sections):
        out = []
        for s in sections:
            if s.get("id") == section_id:
                pending = s.get("pending_revision")
                if not pending:
                    out.append(s)
                    continue
                merged = {**s}
                prior_author_id = s.get("last_edited_by")
                merged["history"] = _maybe_append_history(
                    s,
                    s.get("content") or "",
                    s.get("content_source") or "user",
                    prior_author_id=prior_author_id,
                    prior_author_name=s.get("last_edited_by_name"),
                    force=actor_id_str is not None and actor_id_str != prior_author_id,
                )
                merged["content"] = pending
                merged["content_source"] = "ai"
                merged["content_updated_at"] = _now_iso()
                merged["last_edited_by"] = actor_id_str
                merged["last_edited_by_name"] = actor_name
                merged["last_edited_at"] = _now_iso()
                merged["pending_revision"] = None
                merged["pending_change_summary"] = None
                out.append(merged)
            else:
                out.append(s)
        return (out, None)

    project, _ = await _mutate_sections(project_id, mutate)
    return project


async def reject_section_revision(project_id: UUID, section_id: str) -> dict:
    """Discard pending_revision, leaving content untouched."""
    def mutate(sections):
        out = []
        for s in sections:
            if s.get("id") == section_id and (s.get("pending_revision") or s.get("pending_change_summary")):
                merged = {**s, "pending_revision": None, "pending_change_summary": None}
                out.append(merged)
            else:
                out.append(s)
        return (out, None)

    project, _ = await _mutate_sections(project_id, mutate)
    return project


async def delete_section(project_id: UUID, section_id: str) -> dict:
    def mutate(sections):
        return ([s for s in sections if s.get("id") != section_id], None)

    project, _ = await _mutate_sections(project_id, mutate)
    return project


async def reorder_sections(project_id: UUID, section_ids: list[str]) -> dict:
    def mutate(sections):
        section_map = {s["id"]: s for s in sections}
        reordered = [section_map[sid] for sid in section_ids if sid in section_map]
        seen = set(section_ids)
        for s in sections:
            if s["id"] not in seen:
                reordered.append(s)
        return (reordered, None)

    project, _ = await _mutate_sections(project_id, mutate)
    return project
