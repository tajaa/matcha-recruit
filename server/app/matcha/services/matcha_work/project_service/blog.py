"""Blog projects (project_type == 'blog'): field patch, status transition, and
the AI-directive applier.
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from app.database import get_connection

from ._config import _ALLOWED_BLOG_STATUSES, _ALLOWED_BLOG_TONES, _now_iso, _slugify
from ._data import _load_and_lock_data, _persist_data
from .sections import _maybe_append_history, _mutate_sections

logger = logging.getLogger(__name__)


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
