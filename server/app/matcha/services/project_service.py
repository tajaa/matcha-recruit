"""Project service — CRUD + section management for mw_projects."""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from ...database import get_connection

logger = logging.getLogger(__name__)


_ALLOWED_PROJECT_TYPES = {"general", "presentation", "recruiting", "consultation", "blog", "collab"}
_ALLOWED_STAGES = {"lead", "proposal", "active", "completed", "archived"}
_ALLOWED_PRICING_MODELS = {"hourly", "retainer", "fixed", "free"}
_ALLOWED_BLOG_TONES = {"expert-casual", "technical", "exec-brief", "conversational", "academic"}
_ALLOWED_BLOG_STATUSES = {"draft", "scheduled", "published"}


def _slugify(text: str) -> str:
    s = (text or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:80] or "untitled"


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


def _compute_blog_stats(sections: list) -> dict:
    wc = 0
    for s in sections or []:
        if not isinstance(s, dict):
            continue
        content = s.get("content") or ""
        wc += len([w for w in re.split(r"\s+", content.strip()) if w])
    return {"word_count": wc, "read_minutes": max(1, round(wc / 225)) if wc else 0}


def _seed_consultation_data(extra_data: Optional[dict]) -> dict:
    """Build the initial project_data shape for a new consultation."""
    extra = extra_data or {}
    client_in = extra.get("client") or {}
    eng_in = extra.get("engagement") or {}
    pricing = eng_in.get("pricing_model") or "hourly"
    if pricing not in _ALLOWED_PRICING_MODELS:
        pricing = "hourly"
    return {
        "client": {
            "name": client_in.get("name"),
            "org": client_in.get("org"),
            "website": client_in.get("website"),
            "avatar_url": None,
            "primary_contact": client_in.get("primary_contact") or {},
            "additional_contacts": [],
        },
        "stage": "active",
        "tags": list(extra.get("tags") or []),
        "engagement": {
            "start_date": eng_in.get("start_date"),
            "end_date": None,
            "pricing_model": pricing,
            "rate_cents_per_hour": eng_in.get("rate_cents_per_hour"),
            "monthly_retainer_cents": eng_in.get("monthly_retainer_cents"),
            "fixed_fee_cents": eng_in.get("fixed_fee_cents"),
            "sow_url": eng_in.get("sow_url"),
            "contract_signed_at": None,
        },
        "sessions": [],
        "deliverables": [],
        "action_items": [],
        "custom_fields": [],
        "last_contact_at": None,
    }


async def create_project(
    company_id: UUID,
    user_id: UUID,
    title: str = "Untitled Project",
    project_type: str = "general",
    hiring_client_id: Optional[UUID] = None,
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

        if project_type == "consultation":
            initial_project_data = _seed_consultation_data(extra_data)
        elif project_type == "blog":
            seed_extra = dict(extra_data or {})
            seed_extra.setdefault("title", title)
            initial_project_data = _seed_blog_data(seed_extra)
        else:
            initial_project_data = {}
        row = await conn.fetchrow(
            """
            INSERT INTO mw_projects (company_id, created_by, title, project_type, hiring_client_id, project_data)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            RETURNING *
            """,
            company_id, user_id, title, project_type, hiring_client_id,
            json.dumps(initial_project_data),
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
        if user_id:
            role_subquery = f", (SELECT role FROM mw_project_collaborators WHERE project_id = p.id AND user_id = ${1 if not company_id else 2} AND status = 'active' LIMIT 1) AS collaborator_role"

        query = f"""
            SELECT p.*,
                   rc.name AS hiring_client_name,
                   (SELECT COUNT(*) FROM mw_threads WHERE project_id = p.id) as chat_count
                   {role_subquery}
            FROM mw_projects p
            LEFT JOIN recruiting_clients rc ON rc.id = p.hiring_client_id
            {where_clause}
            ORDER BY p.updated_at DESC
        """
        rows = await conn.fetch(query, *args)
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
        async with conn.transaction():
            prior = await conn.fetchrow(
                "SELECT title, project_type, project_data FROM mw_projects WHERE id = $1 FOR UPDATE",
                project_id,
            )
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
    return _parse_project(row)


# ── Blog operations ──


async def patch_blog(project_id: UUID, patch: dict) -> dict:
    """Partial update of blog project_data (excerpt/tone/tags/slug/author/audience)."""
    async with get_connection() as conn:
        async with conn.transaction():
            data = await _load_and_lock_data(conn, project_id)
            if "slug" in patch and patch["slug"] is not None:
                data["slug"] = _slugify(str(patch["slug"]))
            if "excerpt" in patch:
                data["excerpt"] = patch["excerpt"]
            if "audience" in patch:
                data["audience"] = patch["audience"]
            if "tone" in patch:
                tone = patch["tone"]
                if tone not in _ALLOWED_BLOG_TONES:
                    raise ValueError(f"Unknown tone '{tone}'")
                data["tone"] = tone
            if "tags" in patch and isinstance(patch["tags"], list):
                data["tags"] = [str(t) for t in patch["tags"]]
            if "author" in patch and isinstance(patch["author"], dict):
                author = dict(data.get("author") or {})
                author.update(patch["author"])
                data["author"] = author
            return await _persist_data(conn, project_id, data)


async def transition_blog_status(project_id: UUID, to: str) -> dict:
    """Flip blog status. Phase 1: draft <-> published only."""
    if to not in _ALLOWED_BLOG_STATUSES:
        raise ValueError(f"Unknown status '{to}'")
    async with get_connection() as conn:
        async with conn.transaction():
            data = await _load_and_lock_data(conn, project_id)
            data["status"] = to
            if to == "published":
                data["published_at"] = datetime.now(timezone.utc).isoformat()
            elif to == "draft":
                data["published_at"] = None
            return await _persist_data(conn, project_id, data)


async def archive_project(project_id: UUID):
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE mw_projects SET status = 'archived', updated_at = NOW() WHERE id = $1",
            project_id,
        )


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


_HISTORY_SNAPSHOT_INTERVAL_SEC = 300
_HISTORY_MAX_ENTRIES = 20


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _maybe_append_history(section: dict, prior_content: str, prior_source: str) -> list:
    """Append a snapshot of prior_content to section['history'] if >5min since
    last snapshot. Returns updated history list. Caps at _HISTORY_MAX_ENTRIES.
    No-op when prior_content is empty.
    """
    history = list(section.get("history") or [])
    if not prior_content:
        return history
    last_at = history[-1].get("at") if history else None
    now = datetime.now(timezone.utc)
    if last_at:
        try:
            last_dt = datetime.fromisoformat(last_at)
            if (now - last_dt).total_seconds() < _HISTORY_SNAPSHOT_INTERVAL_SEC:
                return history
        except ValueError:
            pass
    history.append({
        "content": prior_content,
        "source": prior_source or "user",
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


async def update_section(project_id: UUID, section_id: str, updates: dict) -> dict:
    """User-facing section update. Stamps content_source='user' and appends
    a history snapshot (>=5min cadence) when content changes.
    """
    source = updates.get("_source") or "user"

    def mutate(sections):
        out = []
        for s in sections:
            if s.get("id") == section_id:
                merged = {**s}
                content_changed = (
                    "content" in updates and updates["content"] != s.get("content")
                )
                if content_changed:
                    merged["history"] = _maybe_append_history(
                        s,
                        s.get("content") or "",
                        s.get("content_source") or "user",
                    )
                    merged["content"] = updates["content"]
                    merged["content_source"] = source
                    merged["content_updated_at"] = _now_iso()
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


async def accept_section_revision(project_id: UUID, section_id: str) -> dict:
    """Promote pending_revision → content. Records history snapshot."""
    def mutate(sections):
        out = []
        for s in sections:
            if s.get("id") == section_id:
                pending = s.get("pending_revision")
                if not pending:
                    out.append(s)
                    continue
                merged = {**s}
                merged["history"] = _maybe_append_history(
                    s,
                    s.get("content") or "",
                    s.get("content_source") or "user",
                )
                merged["content"] = pending
                merged["content_source"] = "ai"
                merged["content_updated_at"] = _now_iso()
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


async def apply_blog_directives(
    project_id: UUID,
    outline: Optional[list] = None,
    draft: Optional[dict] = None,
    revision: Optional[dict] = None,
    replace: Optional[list] = None,
) -> tuple[dict, bool]:
    """Apply AI blog directives under a single row lock.

    Returns (project_dict, changed_bool).

    - `outline` seeds sections only when the blog currently has zero sections.
    - `draft` is a dict keyed by section_id → markdown content.
    - `revision` is {section_id, content, change_summary?}.
    - `replace` is the full new ordered list of sections:
      [{id?, title, content?}, ...]. Replaces the entire sections list.
      Items with an id matching an existing section preserve existing content
      (and may update title). Items without id become new sections. Existing
      sections whose id is not in `replace` are deleted. Rejected if empty.
    """
    import uuid as _uuid

    def mutate(sections: list):
        changed = False
        new_sections = list(sections)

        # Destructive restructure takes precedence. When replace is provided
        # the AI intends to overwrite the section list wholesale. Skip outline
        # seeding and treat draft/revision directives against the NEW section
        # ids (after the replace).
        if isinstance(replace, list) and replace:
            existing_by_id = {s.get("id"): s for s in new_sections if s.get("id")}
            replaced: list = []
            for item in replace:
                if not isinstance(item, dict):
                    continue
                title = (item.get("title") or "").strip()
                raw_id = item.get("id")
                if raw_id and raw_id in existing_by_id:
                    base = existing_by_id[raw_id]
                    merged = {**base}
                    if title:
                        merged["title"] = title
                    if "content" in item:
                        new_content = (item.get("content") or "").strip()
                        if new_content:
                            merged["content"] = new_content
                    replaced.append(merged)
                else:
                    if not title:
                        continue
                    content = (item.get("content") or "").strip()
                    replaced.append({
                        "id": _uuid.uuid4().hex[:12],
                        "title": title,
                        "content": content,
                        "content_source": "ai",
                        "content_updated_at": _now_iso(),
                        "history": [],
                    })
            # Guard: never allow an empty replacement to silently wipe the blog.
            if replaced:
                new_sections = replaced
                changed = True

        if outline and not new_sections:
            seeded = []
            for item in outline:
                if not isinstance(item, dict):
                    continue
                title = (item.get("title") or "").strip()
                if not title:
                    continue
                bullets = item.get("bullets") or []
                bullets = [str(b).strip() for b in bullets if isinstance(b, (str, int, float)) and str(b).strip()]
                content = "\n".join(f"- {b}" for b in bullets) if bullets else ""
                seeded.append({
                    "id": _uuid.uuid4().hex[:12],
                    "title": title,
                    "content": content,
                    "content_source": "ai",
                    "content_updated_at": _now_iso(),
                    "history": [],
                })
            if seeded:
                new_sections = seeded
                changed = True

        by_id = {s.get("id"): i for i, s in enumerate(new_sections) if s.get("id")}

        # AI drafts/revisions on sections the user has edited land as
        # pending_revision — never overwrite user content silently. First-time
        # drafts on empty/AI-seeded sections write directly.
        if isinstance(draft, dict):
            for sid, content in draft.items():
                if not isinstance(content, str) or not content.strip():
                    continue
                idx = by_id.get(sid)
                if idx is None:
                    continue
                sec = new_sections[idx]
                existing = (sec.get("content") or "").strip()
                source = sec.get("content_source") or ("user" if existing else "ai")
                if existing and source == "user":
                    new_sections[idx] = {
                        **sec,
                        "pending_revision": content.strip(),
                        "pending_change_summary": "AI draft (review before applying)",
                    }
                else:
                    new_sections[idx] = {
                        **sec,
                        "history": _maybe_append_history(sec, existing, source),
                        "content": content.strip(),
                        "content_source": "ai",
                        "content_updated_at": _now_iso(),
                    }
                changed = True

        if isinstance(revision, dict):
            rsid = revision.get("section_id")
            rcontent = (revision.get("content") or "").strip()
            rsummary = (revision.get("change_summary") or "").strip() or "AI revision (review before applying)"
            if rsid and rcontent:
                idx = by_id.get(rsid)
                if idx is not None:
                    sec = new_sections[idx]
                    # Revisions ALWAYS stage as pending — user explicitly accepts.
                    new_sections[idx] = {
                        **sec,
                        "pending_revision": rcontent,
                        "pending_change_summary": rsummary,
                    }
                    changed = True

        if not changed:
            # Signal no-op so _mutate_sections skips the write.
            return (sections, False)
        return (new_sections, True)

    project, changed_flag = await _mutate_sections(project_id, mutate)
    return project, bool(changed_flag)


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


# ── Consultation operations ──


def _new_id(prefix: str) -> str:
    return f"{prefix}_{os.urandom(6).hex()}"


def _max_session_iso(sessions: list[dict]) -> Optional[str]:
    dates = [s.get("at") for s in sessions if isinstance(s, dict) and s.get("at")]
    return max(dates) if dates else None


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


async def patch_consultation(project_id: UUID, patch: dict) -> dict:
    """Deep-merge client + engagement, replace stage/tags/custom_fields when provided."""
    async with get_connection() as conn:
        async with conn.transaction():
            data = await _load_and_lock_data(conn, project_id)
            if "client" in patch and isinstance(patch["client"], dict):
                client = dict(data.get("client") or {})
                client.update(patch["client"])
                data["client"] = client
            if "engagement" in patch and isinstance(patch["engagement"], dict):
                eng = dict(data.get("engagement") or {})
                pricing = patch["engagement"].get("pricing_model")
                if pricing is not None and pricing not in _ALLOWED_PRICING_MODELS:
                    raise ValueError(f"Unknown pricing_model '{pricing}'")
                eng.update(patch["engagement"])
                data["engagement"] = eng
            if "stage" in patch:
                if patch["stage"] not in _ALLOWED_STAGES:
                    raise ValueError(f"Unknown stage '{patch['stage']}'")
                data["stage"] = patch["stage"]
            if "tags" in patch and isinstance(patch["tags"], list):
                data["tags"] = [str(t) for t in patch["tags"]]
            if "custom_fields" in patch and isinstance(patch["custom_fields"], list):
                data["custom_fields"] = patch["custom_fields"]
            # If the client name changed, sync project title to match
            new_title = None
            if "client" in patch and isinstance(patch["client"], dict) and patch["client"].get("name"):
                new_title = patch["client"]["name"]
            if new_title:
                await conn.execute(
                    "UPDATE mw_projects SET title = $1 WHERE id = $2", new_title, project_id
                )
            return await _persist_data(conn, project_id, data)


async def append_session(project_id: UUID, session: dict) -> dict:
    """Append a session entry and refresh last_contact_at."""
    entry = {
        "id": _new_id("s"),
        "at": session.get("at") or datetime.now(timezone.utc).isoformat(),
        "duration_min": session.get("duration_min"),
        "notes": session.get("notes"),
        "billable": bool(session.get("billable", True)),
        "rate_cents_override": session.get("rate_cents_override"),
        "linked_thread_id": session.get("linked_thread_id"),
        "invoice_id": None,
    }
    async with get_connection() as conn:
        async with conn.transaction():
            data = await _load_and_lock_data(conn, project_id)
            sessions = list(data.get("sessions") or [])
            sessions.append(entry)
            data["sessions"] = sessions
            data["last_contact_at"] = _max_session_iso(sessions)
            return await _persist_data(conn, project_id, data)


async def update_session(project_id: UUID, session_id: str, patch: dict) -> dict:
    async with get_connection() as conn:
        async with conn.transaction():
            data = await _load_and_lock_data(conn, project_id)
            sessions = list(data.get("sessions") or [])
            found = False
            for i, s in enumerate(sessions):
                if isinstance(s, dict) and s.get("id") == session_id:
                    merged = {**s, **{k: v for k, v in patch.items() if k in (
                        "at", "duration_min", "notes", "billable",
                        "rate_cents_override", "linked_thread_id", "invoice_id",
                    )}}
                    sessions[i] = merged
                    found = True
                    break
            if not found:
                raise ValueError("Session not found")
            data["sessions"] = sessions
            data["last_contact_at"] = _max_session_iso(sessions)
            return await _persist_data(conn, project_id, data)


async def delete_session(project_id: UUID, session_id: str) -> dict:
    async with get_connection() as conn:
        async with conn.transaction():
            data = await _load_and_lock_data(conn, project_id)
            sessions = [s for s in (data.get("sessions") or []) if not (isinstance(s, dict) and s.get("id") == session_id)]
            data["sessions"] = sessions
            data["last_contact_at"] = _max_session_iso(sessions)
            return await _persist_data(conn, project_id, data)


async def append_action_item(
    project_id: UUID,
    text: str,
    source_thread_id: Optional[str] = None,
    pending_confirmation: bool = False,
) -> dict:
    entry = {
        "id": _new_id("a"),
        "text": text,
        "completed": False,
        "pending_confirmation": pending_confirmation,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_thread_id": source_thread_id,
    }
    async with get_connection() as conn:
        async with conn.transaction():
            data = await _load_and_lock_data(conn, project_id)
            items = list(data.get("action_items") or [])
            items.append(entry)
            data["action_items"] = items
            return await _persist_data(conn, project_id, data)


async def patch_action_item(project_id: UUID, item_id: str, patch: dict) -> dict:
    async with get_connection() as conn:
        async with conn.transaction():
            data = await _load_and_lock_data(conn, project_id)
            items = list(data.get("action_items") or [])
            found = False
            for i, it in enumerate(items):
                if isinstance(it, dict) and it.get("id") == item_id:
                    merged = {**it, **{k: v for k, v in patch.items() if k in ("text", "completed", "pending_confirmation")}}
                    items[i] = merged
                    found = True
                    break
            if not found:
                raise ValueError("Action item not found")
            data["action_items"] = items
            return await _persist_data(conn, project_id, data)


async def delete_action_item(project_id: UUID, item_id: str) -> dict:
    async with get_connection() as conn:
        async with conn.transaction():
            data = await _load_and_lock_data(conn, project_id)
            data["action_items"] = [
                it for it in (data.get("action_items") or [])
                if not (isinstance(it, dict) and it.get("id") == item_id)
            ]
            return await _persist_data(conn, project_id, data)


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
            INSERT INTO mw_project_collaborators (project_id, user_id, invited_by, role, status)
            VALUES ($1, $2, $3, 'collaborator', 'active')
            ON CONFLICT (project_id, user_id) DO UPDATE SET status = 'active'
            """,
            project_id, user_id, invited_by,
        )

        project = await conn.fetchrow("SELECT title FROM mw_projects WHERE id = $1", project_id)
        inviter = await conn.fetchrow("SELECT email FROM users WHERE id = $1", invited_by)
        inviter_client = await conn.fetchrow("SELECT name FROM clients WHERE user_id = $1", invited_by)
        inviter_name = (inviter_client["name"] if inviter_client and inviter_client["name"] else None) or inviter["email"].split("@")[0]
        project_title = project["title"] if project else "a project"

        msg_content = f"**{inviter_name}** has invited you to join the project **{project_title}**."
        conversation = await conn.fetchrow(
            """INSERT INTO inbox_conversations (title, is_group, created_by, last_message_at, last_message_preview)
               VALUES ($1, false, $2, NOW(), $3)
               RETURNING id""",
            f"Project Invite: {project_title}", invited_by, msg_content[:100],
        )
        conv_id = conversation["id"]
        await conn.execute("INSERT INTO inbox_participants (conversation_id, user_id) VALUES ($1, $2)", conv_id, invited_by)
        await conn.execute("INSERT INTO inbox_participants (conversation_id, user_id) VALUES ($1, $2)", conv_id, user_id)
        await conn.execute("INSERT INTO inbox_messages (conversation_id, sender_id, content) VALUES ($1, $2, $3)", conv_id, invited_by, msg_content)

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
