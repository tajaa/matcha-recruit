import base64
import asyncio
import html
import json
import logging
import re
import secrets
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from app.database import get_connection
from app.config import get_settings
from app.core.services.compliance_service import codified_gate_sql, get_locations
from app.core.services.email import EmailService
from app.core.services.storage import get_storage
from app.matcha.services.matcha_work_modes import MODE_COLUMNS_SQL, MODES_BY_KEY

# Leaf helpers extracted to submodules (L6). Re-imported so this module's own
# code + external `doc_svc.X` callers keep working.
from app.matcha.services.matcha_work_document._coerce import (  # noqa: F401
    EMAIL_REGEX,
    VALID_REVIEW_REQUEST_STATUSES,
    _parse_jsonb,
    _infer_skill_from_state,
    _strip_markdown_text,
    _extract_slide_bullets,
    _build_workbook_presentation_state,
    _parse_date_str,
    _coerce_bool,
    _coerce_int,
    _coerce_float,
    _coerce_datetime,
    _normalize_email,
    normalize_recipient_emails,
    _coerce_state_recipient_emails,
    _coerce_offer_draft_recipient_emails,
    _row_to_review_request_status,
    _build_review_request_state_update,
)
from app.matcha.services.matcha_work_document._storage import (  # noqa: F401
    MATCHA_WORK_STORAGE_ROOT,
    _should_enforce_company_scoped_matcha_work_storage,
    build_matcha_work_thread_storage_prefix,
    _storage_key_from_path,
    _storage_path_has_prefix,
    _storage_filename,
    _migrate_matcha_work_asset_to_scope,
    ensure_matcha_work_thread_storage_scope,
)
from app.matcha.services.matcha_work_document._email_html import (  # noqa: F401
    _render_review_request_email_html,
    _render_offer_letter_draft_email_html,
    _build_offer_letter_payload,
)
from app.matcha.services.matcha_work_document._tokens import (  # noqa: F401
    _DEFAULT_TOKEN_LIMIT,
    _DEFAULT_WINDOW_HOURS,
    log_token_usage_event,
    check_token_quota,
    get_token_usage_summary,
)

logger = logging.getLogger(__name__)


# TTL+LRU cache for company profiles — avoids re-fetching on every message.
# Bounded size prevents unbounded growth on a long-running server. cachetools
# evicts oldest entries when full and drops expired entries on access.
from cachetools import TTLCache  # noqa: E402

_PROFILE_CACHE_TTL = 300  # 5 minutes
_PROFILE_CACHE_MAX = 1000  # caps memory at ~companies × profile size
_company_profile_cache: TTLCache = TTLCache(maxsize=_PROFILE_CACHE_MAX, ttl=_PROFILE_CACHE_TTL)






















































def invalidate_company_profile_cache(company_id: UUID) -> None:
    """Remove a company's cached profile so the next call fetches fresh data."""
    _company_profile_cache.pop(str(company_id), None)


async def get_company_profile_for_ai(company_id: UUID) -> dict:
    """Fetch the company profile fields relevant to AI context."""
    key = str(company_id)
    cached = _company_profile_cache.get(key)
    if cached is not None:
        return dict(cached)  # return a copy so callers can't corrupt cache

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT name, industry, size,
                   headquarters_state, headquarters_city, work_arrangement,
                   default_employment_type, benefits_summary, pto_policy_summary,
                   compensation_notes, company_values, ai_guidance_notes,
                   COALESCE(is_personal, false) AS is_personal
            FROM companies
            WHERE id = $1
            """,
            company_id,
        )
        if row is None:
            _company_profile_cache[key] = {}
            return {}
        profile = {k: v for k, v in dict(row).items() if v is not None}

    # Match the Compliance page's business-specific active locations and filtered requirements.
    try:
        locations = [
            loc for loc in await get_locations(company_id)
            if loc.get("is_active", True)
        ]
    except Exception:
        logger.warning("Failed to load compliance locations for Matcha Work AI context", exc_info=True)
        _company_profile_cache[key] = profile
        return profile

    if not locations:
        _company_profile_cache[key] = profile
        return profile

    def _location_label(loc: dict) -> str:
        city = (loc.get("city") or "").strip()
        state = (loc.get("state") or "").strip()
        return f"{city}, {state}" if city else state

    location_labels = {
        str(loc["id"]): _location_label(loc)
        for loc in locations
        if loc.get("id") and _location_label(loc)
    }
    profile["compliance_locations"] = "; ".join(location_labels.values())

    # Fetch all requirements for all locations in a single query to avoid
    # connection pool exhaustion.  The old approach called get_location_requirements()
    # per location via asyncio.gather — each call held a pool connection while also
    # trying to acquire another for get_employee_impact_for_location(), causing a
    # deadlock when the company had 6+ locations (pool max_size=10).
    location_ids = [loc["id"] for loc in locations if loc.get("id")]
    try:
        async with get_connection() as conn:
            # Same codified gate as the Requirements tab. This profile is injected
            # into EVERY matcha-work AI thread, not just compliance-mode ones, so
            # ungated it is the widest path by which a rule we never tied to a
            # statute reaches a user — stated by the model, with no tab to check
            # it against.
            req_rows = await conn.fetch(
                """
                SELECT r.location_id, r.category, r.jurisdiction_name,
                       r.current_value, r.title
                FROM compliance_requirements r
                LEFT JOIN jurisdiction_requirements cat
                  ON cat.id = r.jurisdiction_requirement_id
                WHERE r.location_id = ANY($1::uuid[])
                """
                + await codified_gate_sql("cat", conn=conn)
                + " ORDER BY r.location_id, r.category, r.jurisdiction_level",
                location_ids,
            )
    except Exception:
        logger.warning("Failed to load compliance requirements for Matcha Work AI context", exc_info=True)
        _company_profile_cache[key] = profile
        return profile

    # Group requirements by location
    reqs_by_location: dict[str, list[dict]] = defaultdict(list)
    for rr in req_rows:
        reqs_by_location[str(rr["location_id"])].append(dict(rr))

    location_lines: list[str] = []
    for loc in locations:
        loc_id_str = str(loc.get("id", ""))
        loc_reqs = reqs_by_location.get(loc_id_str, [])
        if not loc_reqs:
            continue

        entries: list[str] = []
        seen_entries: set[str] = set()
        for req in loc_reqs:
            value = (req.get("current_value") or req.get("title") or "").strip()
            if not value:
                continue
            entry = f"{req['category']} ({req['jurisdiction_name']}: {value})"
            if entry in seen_entries:
                continue
            seen_entries.add(entry)
            entries.append(entry)

        if entries:
            location_lines.append(f"  {location_labels.get(loc_id_str, _location_label(loc))}: {'; '.join(entries)}")

    if location_lines:
        profile["jurisdiction_requirements_summary"] = "\n".join(location_lines)

    _company_profile_cache[key] = profile
    return profile


async def get_thread_message_count(thread_id: UUID) -> int:
    """Return total message count for a thread."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM mw_messages WHERE thread_id=$1",
            thread_id,
        )
        return row["cnt"] if row else 0


async def get_context_summary(thread_id: UUID) -> tuple[Optional[str], Optional[int]]:
    """Load the compacted context summary and the message count when it was generated."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT context_summary, context_summary_at_msg_count FROM mw_threads WHERE id=$1",
            thread_id,
        )
        if row and row["context_summary"]:
            return row["context_summary"], row.get("context_summary_at_msg_count")
        return None, None


async def save_context_summary(thread_id: UUID, summary: str, msg_count: int) -> None:
    """Persist a compacted context summary on the thread row."""
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE mw_threads SET context_summary=$1, context_summary_at_msg_count=$2, updated_at=NOW() WHERE id=$3",
            summary,
            msg_count,
            thread_id,
        )


async def create_thread(
    company_id: UUID,
    user_id: UUID,
    title: str = "New Chat",
) -> dict:
    # Pre-populate initial state with company profile hints
    initial_state: dict = {}
    try:
        profile = await get_company_profile_for_ai(company_id)
        if profile.get("name"):
            initial_state["company_name"] = profile["name"]
        if profile.get("industry"):
            initial_state["industry"] = profile["industry"]
        if profile.get("default_employment_type"):
            initial_state["employment_type"] = profile["default_employment_type"]
        if profile.get("headquarters_state"):
            initial_state["work_state"] = profile["headquarters_state"]
    except Exception:
        logger.warning("Failed to fetch company profile for thread pre-population", exc_info=True)

    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                f"""
                INSERT INTO mw_threads(company_id, created_by, title, current_state)
                VALUES($1, $2, $3, $4::jsonb)
                RETURNING id, company_id, created_by, title, status,
                          current_state, version, is_pinned, {MODE_COLUMNS_SQL}, linked_offer_letter_id,
                          created_at, updated_at
                """,
                company_id,
                user_id,
                title,
                json.dumps(initial_state),
            )
            await _upsert_element_from_thread_row(conn, dict(row))
        d = dict(row)
        d["current_state"] = _parse_jsonb(d["current_state"])
        return d


async def get_thread(thread_id: UUID, company_id: UUID, *, user_id: UUID | None = None) -> Optional[dict]:
    async with get_connection() as conn:
        if user_id is not None:
            # Allow access if company matches OR user is a thread collaborator OR
            # user is an active collaborator on the thread's parent project
            row = await conn.fetchrow(
                f"""
                SELECT id, company_id, created_by, title, status,
                       current_state, version, is_pinned, {MODE_COLUMNS_SQL},
                       linked_offer_letter_id, project_id,
                       created_at, updated_at
                FROM mw_threads
                WHERE id=$1 AND (
                    company_id IS NOT DISTINCT FROM $2
                    OR EXISTS(SELECT 1 FROM mw_thread_collaborators WHERE thread_id = $1 AND user_id = $3)
                    OR EXISTS(
                        SELECT 1 FROM mw_project_collaborators pc
                        JOIN mw_threads t ON t.project_id = pc.project_id
                        WHERE t.id = $1 AND pc.user_id = $3 AND pc.status = 'active'
                    )
                )
                """,
                thread_id,
                company_id,
                user_id,
            )
        else:
            row = await conn.fetchrow(
                f"""
                SELECT id, company_id, created_by, title, status,
                       current_state, version, is_pinned, {MODE_COLUMNS_SQL},
                       linked_offer_letter_id, project_id,
                       created_at, updated_at
                FROM mw_threads
                WHERE id=$1 AND company_id=$2
                """,
                thread_id,
                company_id,
            )
        if row is None:
            return None
        d = dict(row)
        d["current_state"] = _parse_jsonb(d["current_state"])
        return d


def _thread_list_item_from_row(row: dict) -> dict:
    return dict(row)


async def list_threads(
    company_id: UUID,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    *,
    user_id: UUID | None = None,
) -> list[dict]:
    async with get_connection() as conn:
        task_type_sql = """
                CASE
                  WHEN current_state ?| array['candidate_name','position_title','salary','salary_range_min'] THEN 'offer_letter'
                  WHEN current_state ?| array['overall_rating','review_title','review_request_statuses','review_expected_responses'] THEN 'review'
                  WHEN EXISTS (SELECT 1 FROM jsonb_object_keys(current_state) k WHERE k LIKE 'handbook_%') THEN 'handbook'
                  WHEN EXISTS (SELECT 1 FROM jsonb_object_keys(current_state) k WHERE k LIKE 'policy_%') THEN 'policy'
                  WHEN current_state ? 'sections' OR current_state ? 'workbook_title' THEN 'workbook'
                  WHEN current_state ?| array['employees','batch_status'] THEN 'onboarding'
                  WHEN current_state ?| array['presentation_title','slides'] THEN 'presentation'
                  ELSE 'chat'
                END AS task_type
        """
        # Build the access clause — threads owned by company, where user is a thread collaborator,
        # OR where user is an active collaborator on the thread's parent project
        if user_id is not None:
            # $1=company_id(UUID), $2=user_id(UUID) — UUIDs first, ints after
            access_clause = (
                "project_id IS NULL AND (company_id=$1"
                " OR EXISTS(SELECT 1 FROM mw_thread_collaborators WHERE thread_id = mw_threads.id AND user_id = $2)"
                " OR EXISTS(SELECT 1 FROM mw_project_collaborators pc WHERE pc.project_id = mw_threads.project_id"
                " AND pc.user_id = $2 AND pc.status = 'active'))"
            )
        else:
            access_clause = "project_id IS NULL AND company_id=$1"

        collab_count_sql = "(SELECT COUNT(*) FROM mw_thread_collaborators WHERE thread_id = mw_threads.id) AS collaborator_count"

        if status:
            if user_id is not None:
                rows = await conn.fetch(
                    f"""
                    SELECT id, title, status, version, is_pinned, {MODE_COLUMNS_SQL}, created_at, updated_at,
                           {task_type_sql},
                           {collab_count_sql}
                    FROM mw_threads
                    WHERE {access_clause} AND status=$3
                    ORDER BY is_pinned DESC, updated_at DESC
                    LIMIT $4 OFFSET $5
                    """,
                    company_id,
                    user_id,
                    status,
                    limit,
                    offset,
                )
            else:
                rows = await conn.fetch(
                    f"""
                    SELECT id, title, status, version, is_pinned, {MODE_COLUMNS_SQL}, created_at, updated_at,
                           {task_type_sql},
                           {collab_count_sql}
                    FROM mw_threads
                    WHERE company_id=$1 AND status=$2
                    ORDER BY is_pinned DESC, updated_at DESC
                    LIMIT $3 OFFSET $4
                    """,
                    company_id,
                    status,
                    limit,
                    offset,
                )
        else:
            if user_id is not None:
                rows = await conn.fetch(
                    f"""
                    SELECT id, title, status, version, is_pinned, {MODE_COLUMNS_SQL}, created_at, updated_at,
                           {task_type_sql},
                           {collab_count_sql}
                    FROM mw_threads
                    WHERE {access_clause}
                    ORDER BY is_pinned DESC, updated_at DESC
                    LIMIT $3 OFFSET $4
                    """,
                    company_id,
                    user_id,
                    limit,
                    offset,
                )
            else:
                rows = await conn.fetch(
                    f"""
                    SELECT id, title, status, version, is_pinned, {MODE_COLUMNS_SQL}, created_at, updated_at,
                           {task_type_sql},
                           {collab_count_sql}
                    FROM mw_threads
                    WHERE company_id=$1
                    ORDER BY is_pinned DESC, updated_at DESC
                    LIMIT $2 OFFSET $3
                    """,
                    company_id,
                    limit,
                    offset,
                )
        return [_thread_list_item_from_row(dict(r)) for r in rows]


async def list_elements(
    company_id: UUID,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    async with get_connection() as conn:
        if status:
            rows = await conn.fetch(
                """
                SELECT id, thread_id, element_type, title, status, version,
                       linked_offer_letter_id, created_at, updated_at
                FROM mw_elements
                WHERE company_id=$1 AND status=$2 AND is_materialized=true
                ORDER BY updated_at DESC
                LIMIT $3 OFFSET $4
                """,
                company_id,
                status,
                limit,
                offset,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, thread_id, element_type, title, status, version,
                       linked_offer_letter_id, created_at, updated_at
                FROM mw_elements
                WHERE company_id=$1 AND is_materialized=true
                ORDER BY updated_at DESC
                LIMIT $2 OFFSET $3
                """,
                company_id,
                limit,
                offset,
            )
        return [dict(r) for r in rows]


VALID_ELEMENT_TYPES = {"offer_letter", "review", "workbook"}


async def _upsert_element_from_thread_row(conn, thread_row: dict) -> None:
    try:
        state_json = _parse_jsonb(thread_row.get("current_state"))
        inferred_type = _infer_skill_from_state(state_json)
        if inferred_type not in VALID_ELEMENT_TYPES:
            # chat/onboarding threads don't get element records
            return
        existing_is_materialized = await conn.fetchval(
            "SELECT is_materialized FROM mw_elements WHERE thread_id=$1",
            thread_row["id"],
        )
        is_materialized = bool(thread_row.get("linked_offer_letter_id")) or thread_row["status"] == "finalized"
        if thread_row["status"] == "archived" and bool(existing_is_materialized):
            # Keep archived items visible when they were previously materialized.
            is_materialized = True
        await conn.execute(
            """
            INSERT INTO mw_elements(
                thread_id,
                company_id,
                created_by,
                element_type,
                title,
                status,
                state_json,
                version,
                linked_offer_letter_id,
                is_materialized,
                created_at,
                updated_at
            )
            VALUES($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11, $12)
            ON CONFLICT(thread_id) DO UPDATE
            SET
                company_id=EXCLUDED.company_id,
                created_by=EXCLUDED.created_by,
                element_type=EXCLUDED.element_type,
                title=EXCLUDED.title,
                status=EXCLUDED.status,
                state_json=EXCLUDED.state_json,
                version=EXCLUDED.version,
                linked_offer_letter_id=EXCLUDED.linked_offer_letter_id,
                is_materialized=EXCLUDED.is_materialized,
                updated_at=EXCLUDED.updated_at
            """,
            thread_row["id"],
            thread_row["company_id"],
            thread_row["created_by"],
            inferred_type,
            thread_row["title"],
            thread_row["status"],
            json.dumps(state_json),
            thread_row.get("version") or 0,
            thread_row.get("linked_offer_letter_id"),
            is_materialized,
            thread_row.get("created_at"),
            thread_row.get("updated_at") or datetime.now(timezone.utc),
        )
    except Exception as e:
        logger.warning(
            "Failed to upsert mw_elements record for thread %s: %s",
            thread_row.get("id"),
            e,
        )


async def _sync_element_for_thread(conn, thread_id: UUID) -> None:
    try:
        row = await conn.fetchrow(
            """
            SELECT id, company_id, created_by, title, status,
                   current_state, version, linked_offer_letter_id,
                   created_at, updated_at
            FROM mw_threads
            WHERE id=$1
            """,
            thread_id,
        )
        if row is None:
            return
        await _upsert_element_from_thread_row(conn, dict(row))
    except Exception as e:
        logger.warning("Failed to sync mw_elements for thread %s: %s", thread_id, e)


async def sync_element_record(thread_id: UUID) -> None:
    async with get_connection() as conn:
        await _sync_element_for_thread(conn, thread_id)


async def set_thread_pinned(
    thread_id: UUID,
    company_id: UUID,
    is_pinned: bool,
) -> Optional[dict]:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE mw_threads
            SET is_pinned=$1, updated_at=NOW()
            WHERE id=$2 AND company_id=$3
            RETURNING id, title, status, version, is_pinned, {MODE_COLUMNS_SQL}, created_at, updated_at, current_state
            """,
            is_pinned,
            thread_id,
            company_id,
        )
        if row is None:
            return None
        await _sync_element_for_thread(conn, thread_id)
        return _thread_list_item_from_row(dict(row))


async def set_thread_mode(
    thread_id: UUID,
    company_id: UUID,
    mode_key: str,
    enabled: bool,
) -> Optional[dict]:
    """Registry-driven mode toggle. mode_key must exist in
    matcha_work_modes.MODES_BY_KEY — the column name comes from the registry,
    never from the caller, so the f-string SQL stays injection-safe."""
    mode = MODES_BY_KEY.get(mode_key)
    if mode is None:
        raise ValueError(f"Unknown thread mode: {mode_key}")
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE mw_threads
            SET {mode.column}=$1, updated_at=NOW()
            WHERE id=$2 AND company_id=$3
            RETURNING id, title, status, version, is_pinned, {MODE_COLUMNS_SQL}, created_at, updated_at, current_state
            """,
            enabled,
            thread_id,
            company_id,
        )
        if row is None:
            return None
        return _thread_list_item_from_row(dict(row))


# Legacy named setters — kept for pre-registry callsites. New code goes
# through set_thread_mode.

async def set_thread_node_mode(
    thread_id: UUID,
    company_id: UUID,
    node_mode: bool,
) -> Optional[dict]:
    return await set_thread_mode(thread_id, company_id, "node", node_mode)


async def set_thread_compliance_mode(
    thread_id: UUID,
    company_id: UUID,
    compliance_mode: bool,
) -> Optional[dict]:
    return await set_thread_mode(thread_id, company_id, "compliance", compliance_mode)


async def set_thread_payer_mode(
    thread_id: UUID,
    company_id: UUID,
    payer_mode: bool,
) -> Optional[dict]:
    return await set_thread_mode(thread_id, company_id, "payer", payer_mode)


async def get_thread_messages(thread_id: UUID, limit: int | None = None) -> list[dict]:
    async with get_connection() as conn:
        if limit is not None:
            rows = await conn.fetch(
                """
                SELECT id, thread_id, role, content, version_created, metadata, created_at
                FROM (
                    SELECT id, thread_id, role, content, version_created, metadata, created_at
                    FROM mw_messages
                    WHERE thread_id=$1
                    ORDER BY created_at DESC
                    LIMIT $2
                ) recent_messages
                ORDER BY created_at ASC
                """,
                thread_id,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, thread_id, role, content, version_created, metadata, created_at
                FROM mw_messages
                WHERE thread_id=$1
                ORDER BY created_at ASC
                """,
                thread_id,
            )
        return [dict(r) for r in rows]


async def add_message(
    thread_id: UUID,
    role: str,
    content: str,
    version_created: Optional[int] = None,
    metadata: Optional[dict] = None,
) -> dict:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO mw_messages(thread_id, role, content, version_created, metadata)
            VALUES($1, $2, $3, $4, $5::jsonb)
            RETURNING id, thread_id, role, content, version_created, metadata, created_at
            """,
            thread_id,
            role,
            content,
            version_created,
            json.dumps(metadata) if metadata else None,
        )
        await conn.execute(
            "UPDATE mw_threads SET updated_at = NOW() WHERE id = $1",
            thread_id,
        )
        return dict(row)










async def apply_update(
    thread_id: UUID,
    updates: dict,
    diff_summary: Optional[str] = None,
) -> dict:
    """Merge updates into current_state, bump version, snapshot to mw_document_versions."""
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT current_state, version FROM mw_threads WHERE id=$1 FOR UPDATE",
                thread_id,
            )
            current_state = _parse_jsonb(row["current_state"])
            current_version = row["version"]

            merged_state = {**current_state, **updates}
            # Clear fields that were explicitly set to None
            merged_state = {k: v for k, v in merged_state.items() if v is not None}
            new_version = current_version + 1

            await conn.execute(
                """
                UPDATE mw_threads
                SET current_state=$1, version=$2, updated_at=NOW()
                WHERE id=$3
                """,
                json.dumps(merged_state),
                new_version,
                thread_id,
            )
            await conn.execute(
                """
                INSERT INTO mw_document_versions(thread_id, version, state_json, diff_summary)
                VALUES($1, $2, $3, $4)
                ON CONFLICT(thread_id, version) DO NOTHING
                """,
                thread_id,
                new_version,
                json.dumps(merged_state),
                diff_summary,
            )
            await _sync_element_for_thread(conn, thread_id)
        return {"version": new_version, "current_state": merged_state}


async def revert_to_version(thread_id: UUID, target_version: int) -> dict:
    """Load a historical snapshot and create a NEW version with that state."""
    async with get_connection() as conn:
        snap = await conn.fetchrow(
            "SELECT state_json FROM mw_document_versions WHERE thread_id=$1 AND version=$2",
            thread_id,
            target_version,
        )
        if snap is None:
            raise ValueError(f"Version {target_version} not found for thread {thread_id}")

        old_state = _parse_jsonb(snap["state_json"])

        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT version FROM mw_threads WHERE id=$1 FOR UPDATE",
                thread_id,
            )
            new_version = row["version"] + 1

            await conn.execute(
                """
                UPDATE mw_threads
                SET current_state=$1, version=$2, updated_at=NOW()
                WHERE id=$3
                """,
                json.dumps(old_state),
                new_version,
                thread_id,
            )
            await conn.execute(
                """
                INSERT INTO mw_document_versions(thread_id, version, state_json, diff_summary)
                VALUES($1, $2, $3, $4)
                ON CONFLICT(thread_id, version) DO NOTHING
                """,
                thread_id,
                new_version,
                json.dumps(old_state),
                f"Reverted to version {target_version}",
            )
            await _sync_element_for_thread(conn, thread_id)
        return {"version": new_version, "current_state": old_state}


async def list_versions(thread_id: UUID, include_state: bool = False) -> list[dict]:
    async with get_connection() as conn:
        if include_state:
            rows = await conn.fetch(
                """
                SELECT id, thread_id, version, state_json, diff_summary, created_at
                FROM mw_document_versions
                WHERE thread_id=$1
                ORDER BY version DESC
                """,
                thread_id,
            )
            result = []
            for r in rows:
                d = dict(r)
                d["state_json"] = _parse_jsonb(d["state_json"])
                result.append(d)
            return result
        else:
            rows = await conn.fetch(
                """
                SELECT id, thread_id, version, diff_summary, created_at
                FROM mw_document_versions
                WHERE thread_id=$1
                ORDER BY version DESC
                """,
                thread_id,
            )
            return [
                {**dict(r), "state_json": {}}
                for r in rows
            ]


async def _get_cached_pdf_url(
    thread_id: UUID,
    version: int,
    is_draft: bool,
    expected_prefix: Optional[str] = None,
) -> Optional[str]:
    async with get_connection() as conn:
        pdf_url = await conn.fetchval(
            """
            SELECT pdf_url
            FROM mw_pdf_cache
            WHERE thread_id=$1 AND version=$2 AND is_draft=$3
            """,
            thread_id,
            version,
            is_draft,
        )
    if expected_prefix and _should_enforce_company_scoped_matcha_work_storage():
        if not _storage_path_has_prefix(pdf_url, expected_prefix):
            return None
    return pdf_url


async def _cache_pdf_url(
    thread_id: UUID, version: int, pdf_url: str, is_draft: bool = True
) -> None:
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO mw_pdf_cache(thread_id, version, pdf_url, is_draft)
            VALUES($1, $2, $3, $4)
            ON CONFLICT(thread_id, version, is_draft) DO UPDATE
            SET pdf_url=EXCLUDED.pdf_url
            """,
            thread_id,
            version,
            pdf_url,
            is_draft,
        )


async def generate_pdf(
    state: dict,
    thread_id: UUID,
    version: int,
    company_id: UUID,
    is_draft: bool = True,
    logo_src: Optional[str] = None,
) -> Optional[str]:
    """Check cache → render HTML → WeasyPrint → S3 → cache URL."""
    expected_prefix = build_matcha_work_thread_storage_prefix(company_id, thread_id, "pdfs")
    cached = await _get_cached_pdf_url(thread_id, version, is_draft, expected_prefix=expected_prefix)
    if cached:
        return cached

    # Lazy import to avoid circular imports at module load time
    from app.matcha.routes.employee_lifecycle.offer_letters import _generate_offer_letter_html

    render_state = dict(state)
    render_state.setdefault("created_at", datetime.utcnow())

    # Convert date strings to datetime objects for the HTML template
    for date_field in ("start_date", "expiration_date"):
        val = render_state.get(date_field)
        if isinstance(val, str):
            parsed = _parse_date_str(val)
            render_state[date_field] = parsed  # None if unparseable → shows "TBD"

    def _render_pdf() -> Optional[bytes]:
        try:
            html_content = _generate_offer_letter_html(render_state, logo_src=logo_src)
            if is_draft:
                watermark_css = """
                body::before {
                    content: 'DRAFT';
                    position: fixed;
                    top: 50%;
                    left: 50%;
                    transform: translate(-50%, -50%) rotate(-45deg);
                    font-size: 120pt;
                    color: rgba(200, 200, 200, 0.3);
                    font-weight: bold;
                    z-index: -1;
                    pointer-events: none;
                }
                """
                html_content = html_content.replace("</style>", watermark_css + "</style>")
            from app.core.services.pdf import render_pdf

            return render_pdf(html_content)
        except ImportError:
            logger.error("WeasyPrint not installed — PDF generation skipped")
            return None
        except Exception as e:
            logger.error("PDF generation failed: %s", e, exc_info=True)
            return None

    pdf_bytes = await asyncio.to_thread(_render_pdf)
    if pdf_bytes is None:
        return None

    filename = f"v{version}{'_draft' if is_draft else '_final'}.pdf"
    try:
        pdf_url = await get_storage().upload_file(
            pdf_bytes,
            filename,
            prefix=expected_prefix,
            content_type="application/pdf",
        )
    except Exception as e:
        logger.error("Failed to upload PDF to storage: %s", e, exc_info=True)
        return None

    await _cache_pdf_url(thread_id, version, pdf_url, is_draft=is_draft)
    return pdf_url


def _render_presentation_html(state: dict) -> str:
    """Build HTML for a presentation PDF (slides → printable pages)."""
    title = html.escape(str(state.get("presentation_title") or "Presentation"))
    subtitle = html.escape(str(state.get("subtitle") or ""))
    theme = str(state.get("theme") or "professional").lower()
    slides = state.get("slides") or []

    # Theme-based color palette
    themes = {
        "professional": {"bg": "#1a1a2e", "accent": "#4ade80", "text": "#f1f5f9", "slide_bg": "#16213e"},
        "minimal": {"bg": "#ffffff", "accent": "#334155", "text": "#0f172a", "slide_bg": "#f8fafc"},
        "bold": {"bg": "#0f172a", "accent": "#f59e0b", "text": "#f8fafc", "slide_bg": "#1e293b"},
    }
    colors = themes.get(theme, themes["professional"])

    cover_image_url = state.get("cover_image_url")
    slides_html = []
    # Cover slide
    subtitle_html = f"<p class='subtitle'>{subtitle}</p>" if subtitle else ""
    cover_img_html = f"<img src='{html.escape(cover_image_url)}' class='cover-img' />" if cover_image_url else ""
    slides_html.append(f"""
        <div class="slide cover-slide">
          {cover_img_html}
          <div class="cover-content">
            <h1 class="cover-title">{title}</h1>
            {subtitle_html}
          </div>
        </div>""")

    for slide in slides:
        if not isinstance(slide, dict):
            continue
        slide_title = html.escape(str(slide.get("title") or ""))
        bullets = slide.get("bullets") or []
        if not slide_title and not bullets:
            continue
        bullets_html = "".join(
            f"<li>{html.escape(str(b))}</li>"
            for b in bullets
            if str(b).strip()
        )
        slides_html.append(f"""
        <div class="slide content-slide">
          <h2 class="slide-title">{slide_title}</h2>
          <ul class="bullets">{bullets_html}</ul>
        </div>""")

    slides_block = "\n".join(slides_html)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @page {{ size: 1280px 720px; margin: 0; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background: {colors['bg']}; color: {colors['text']}; }}
  .slide {{
    width: 1280px; height: 720px;
    display: flex; flex-direction: column; justify-content: center;
    padding: 60px 80px;
    page-break-after: always;
    background: {colors['slide_bg']};
    border-top: 6px solid {colors['accent']};
  }}
  .cover-slide {{
    background: {colors['bg']};
    border-top: none;
    align-items: flex-start;
    border-left: 8px solid {colors['accent']};
    padding-left: 72px;
    position: relative;
    overflow: hidden;
  }}
  .cover-img {{
    position: absolute; top: 0; left: 0; width: 100%; height: 100%;
    object-fit: cover; opacity: 0.25;
  }}
  .cover-content {{ max-width: 800px; position: relative; z-index: 1; }}
  .cover-title {{
    font-size: 52px; font-weight: 800; line-height: 1.15;
    color: {colors['text']}; margin-bottom: 20px; letter-spacing: -1px;
  }}
  .subtitle {{
    font-size: 24px; color: {colors['accent']}; font-weight: 500;
  }}
  .slide-title {{
    font-size: 34px; font-weight: 700; color: {colors['accent']};
    margin-bottom: 32px; letter-spacing: -0.5px;
  }}
  .bullets {{
    list-style: none; padding: 0;
  }}
  .bullets li {{
    font-size: 22px; line-height: 1.5; padding: 8px 0 8px 28px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    position: relative;
  }}
  .bullets li:last-child {{ border-bottom: none; }}
  .bullets li::before {{
    content: '▸';
    position: absolute; left: 0;
    color: {colors['accent']}; font-size: 16px;
  }}
</style>
</head>
<body>
{slides_block}
</body>
</html>"""


async def generate_presentation_pdf(
    state: dict,
    thread_id: UUID,
    version: int,
    company_id: UUID,
) -> Optional[str]:
    """Render presentation slides to PDF via WeasyPrint and upload to S3."""
    expected_prefix = build_matcha_work_thread_storage_prefix(company_id, thread_id, "presentation-pdfs")
    cached = await _get_cached_pdf_url(thread_id, version, is_draft=False, expected_prefix=expected_prefix)
    if cached:
        return cached

    # Inline the storage-owned cover image to a `data:` URI BEFORE the render
    # thread — the SSRF-safe fetcher blocks raw storage URLs, so the cover would
    # otherwise silently drop. Inlining returns None for external/failed URLs,
    # in which case the cover is omitted gracefully (None falls back to the
    # original value so a data:/non-storage URL is left as-is for the fetcher).
    render_state = state
    cover_url = state.get("cover_image_url")
    if cover_url:
        inlined_cover = await get_storage().inline_image_data_uri(cover_url)
        render_state = dict(state)
        render_state["cover_image_url"] = inlined_cover  # None → cover omitted

    def _render() -> Optional[bytes]:
        try:
            from weasyprint import CSS
            from app.core.services.pdf import render_pdf
            html_content = _render_presentation_html(render_state)
            return render_pdf(
                html_content,
                stylesheets=[CSS(string="@page { size: 1280px 720px; margin: 0; }")],
            )
        except ImportError:
            logger.error("WeasyPrint not installed — presentation PDF skipped")
            return None
        except Exception as e:
            logger.error("Presentation PDF render failed: %s", e, exc_info=True)
            return None

    pdf_bytes = await asyncio.to_thread(_render)
    if pdf_bytes is None:
        return None

    filename = f"presentation_v{version}.pdf"
    try:
        pdf_url = await get_storage().upload_file(
            pdf_bytes,
            filename,
            prefix=expected_prefix,
            content_type="application/pdf",
        )
    except Exception as e:
        logger.error("Failed to upload presentation PDF: %s", e, exc_info=True)
        return None

    await _cache_pdf_url(thread_id, version, pdf_url, is_draft=False)
    return pdf_url


async def generate_cover_image(
    presentation_title: str,
    subtitle: Optional[str] = None,
    *,
    company_id: UUID,
    thread_id: UUID,
) -> Optional[str]:
    """Generate a cover image via Gemini 3.1 Flash Image and upload to S3."""
    import os
    try:
        from app.core.services.genai_client import get_genai_client
        from google.genai import types as _genai_types
        from app.config import get_settings
        settings = get_settings()
        api_key = os.getenv("GEMINI_API_KEY") or settings.gemini_api_key
        if not api_key:
            return None
        client = get_genai_client(api_key=api_key)
        prompt_parts = [f"Professional corporate presentation cover slide illustration for: {presentation_title}"]
        if subtitle:
            prompt_parts.append(f"Subtitle: {subtitle}")
        prompt_parts.append("Clean, modern, abstract data visualization, dark background with green accents, no text, high quality, 16:9 aspect ratio")
        prompt = ". ".join(prompt_parts)

        def _call() -> Optional[tuple[bytes, str]]:
            try:
                response = client.models.generate_content(
                    model="gemini-3.1-flash-image-preview",
                    contents=prompt,
                    config=_genai_types.GenerateContentConfig(
                        response_modalities=["IMAGE", "TEXT"],
                        image_config=_genai_types.ImageConfig(aspect_ratio="16:9"),
                    ),
                )
                for part in response.candidates[0].content.parts:
                    if part.inline_data and part.inline_data.data:
                        mime = part.inline_data.mime_type or "image/png"
                        return part.inline_data.data, mime
            except Exception as e:
                logger.warning("Gemini image generation call failed: %s", e)
            return None

        result = await asyncio.to_thread(_call)
        if result is None:
            return None

        image_bytes, mime_type = result
        ext = "png" if "png" in mime_type else "jpg"
        filename = f"cover_{secrets.token_hex(8)}.{ext}"
        prefix = build_matcha_work_thread_storage_prefix(company_id, thread_id, "covers")
        url = await get_storage().upload_file(
            image_bytes,
            filename,
            prefix=prefix,
            content_type=mime_type,
        )
        return url
    except Exception as e:
        logger.warning("Cover image generation failed: %s", e)
        return None


async def save_offer_letter_draft(thread_id: UUID, company_id: UUID) -> dict:
    """Persist current thread state into offer_letters as a draft and link the thread."""
    async with get_connection() as conn:
        async with conn.transaction():
            thread_row = await conn.fetchrow(
                """
                SELECT t.current_state, t.status, t.linked_offer_letter_id, c.name AS fallback_company_name
                FROM mw_threads t
                JOIN companies c ON c.id = t.company_id
                WHERE t.id = $1 AND t.company_id = $2
                FOR UPDATE
                """,
                thread_id,
                company_id,
            )
            if thread_row is None:
                raise ValueError("Thread not found")
            if thread_row["status"] == "archived":
                raise ValueError("Cannot save draft for an archived thread")

            state = _parse_jsonb(thread_row["current_state"])
            payload = _build_offer_letter_payload(state, thread_row["fallback_company_name"] or "")

            if not payload["candidate_name"] or not payload["position_title"]:
                raise ValueError("Candidate name and position title are required to save a draft")

            existing_offer_id = thread_row["linked_offer_letter_id"]
            saved = None
            if existing_offer_id is not None:
                saved = await conn.fetchrow(
                    """
                    UPDATE offer_letters
                    SET candidate_name = $1,
                        position_title = $2,
                        company_name = $3,
                        salary = $4,
                        bonus = $5,
                        stock_options = $6,
                        start_date = $7,
                        employment_type = $8,
                        location = $9,
                        benefits = $10,
                        manager_name = $11,
                        manager_title = $12,
                        expiration_date = $13,
                        benefits_medical = $14,
                        benefits_medical_coverage = $15,
                        benefits_medical_waiting_days = $16,
                        benefits_dental = $17,
                        benefits_vision = $18,
                        benefits_401k = $19,
                        benefits_401k_match = $20,
                        benefits_wellness = $21,
                        benefits_pto_vacation = $22,
                        benefits_pto_sick = $23,
                        benefits_holidays = $24,
                        benefits_other = $25,
                        contingency_background_check = $26,
                        contingency_credit_check = $27,
                        contingency_drug_screening = $28,
                        company_logo_url = $29,
                        salary_range_min = $30,
                        salary_range_max = $31,
                        candidate_email = $32,
                        status = 'draft',
                        updated_at = NOW()
                    WHERE id = $33 AND company_id = $34
                    RETURNING id, status, updated_at
                    """,
                    payload["candidate_name"],
                    payload["position_title"],
                    payload["company_name"],
                    payload["salary"],
                    payload["bonus"],
                    payload["stock_options"],
                    payload["start_date"],
                    payload["employment_type"],
                    payload["location"],
                    payload["benefits"],
                    payload["manager_name"],
                    payload["manager_title"],
                    payload["expiration_date"],
                    payload["benefits_medical"],
                    payload["benefits_medical_coverage"],
                    payload["benefits_medical_waiting_days"],
                    payload["benefits_dental"],
                    payload["benefits_vision"],
                    payload["benefits_401k"],
                    payload["benefits_401k_match"],
                    payload["benefits_wellness"],
                    payload["benefits_pto_vacation"],
                    payload["benefits_pto_sick"],
                    payload["benefits_holidays"],
                    payload["benefits_other"],
                    payload["contingency_background_check"],
                    payload["contingency_credit_check"],
                    payload["contingency_drug_screening"],
                    payload["company_logo_url"],
                    payload["salary_range_min"],
                    payload["salary_range_max"],
                    payload["candidate_email"],
                    existing_offer_id,
                    company_id,
                )

            if saved is None:
                saved = await conn.fetchrow(
                    """
                    INSERT INTO offer_letters (
                        candidate_name, position_title, company_name, company_id, status,
                        salary, bonus, stock_options, start_date, employment_type, location, benefits,
                        manager_name, manager_title, expiration_date,
                        benefits_medical, benefits_medical_coverage, benefits_medical_waiting_days,
                        benefits_dental, benefits_vision, benefits_401k, benefits_401k_match,
                        benefits_wellness, benefits_pto_vacation, benefits_pto_sick,
                        benefits_holidays, benefits_other,
                        contingency_background_check, contingency_credit_check, contingency_drug_screening,
                        company_logo_url, salary_range_min, salary_range_max, candidate_email
                    )
                    VALUES (
                        $1, $2, $3, $4, 'draft',
                        $5, $6, $7, $8, $9, $10, $11,
                        $12, $13, $14,
                        $15, $16, $17,
                        $18, $19, $20, $21,
                        $22, $23, $24,
                        $25, $26,
                        $27, $28, $29,
                        $30, $31, $32, $33
                    )
                    RETURNING id, status, updated_at
                    """,
                    payload["candidate_name"],
                    payload["position_title"],
                    payload["company_name"],
                    company_id,
                    payload["salary"],
                    payload["bonus"],
                    payload["stock_options"],
                    payload["start_date"],
                    payload["employment_type"],
                    payload["location"],
                    payload["benefits"],
                    payload["manager_name"],
                    payload["manager_title"],
                    payload["expiration_date"],
                    payload["benefits_medical"],
                    payload["benefits_medical_coverage"],
                    payload["benefits_medical_waiting_days"],
                    payload["benefits_dental"],
                    payload["benefits_vision"],
                    payload["benefits_401k"],
                    payload["benefits_401k_match"],
                    payload["benefits_wellness"],
                    payload["benefits_pto_vacation"],
                    payload["benefits_pto_sick"],
                    payload["benefits_holidays"],
                    payload["benefits_other"],
                    payload["contingency_background_check"],
                    payload["contingency_credit_check"],
                    payload["contingency_drug_screening"],
                    payload["company_logo_url"],
                    payload["salary_range_min"],
                    payload["salary_range_max"],
                    payload["candidate_email"],
                )

            await conn.execute(
                """
                UPDATE mw_threads
                SET linked_offer_letter_id = $1, updated_at = NOW()
                WHERE id = $2 AND company_id = $3
                """,
                saved["id"],
                thread_id,
                company_id,
            )
            await _sync_element_for_thread(conn, thread_id)

            return {
                "thread_id": thread_id,
                "linked_offer_letter_id": saved["id"],
                "offer_status": saved["status"],
                "saved_at": saved["updated_at"],
            }


async def send_offer_letter_draft(
    thread_id: UUID,
    company_id: UUID,
    recipient_emails: list[str],
    custom_message: Optional[str] = None,
) -> dict:
    async with get_connection() as conn:
        thread_row = await conn.fetchrow(
            """
            SELECT t.title, t.status, t.current_state, t.version, c.name AS company_name
            FROM mw_threads t
            JOIN companies c ON c.id = t.company_id
            WHERE t.id=$1 AND t.company_id=$2
            """,
            thread_id,
            company_id,
        )
    if thread_row is None:
        raise ValueError("Thread not found")
    if thread_row["status"] == "archived":
        raise ValueError("Cannot send draft from an archived thread")
    if thread_row["status"] == "finalized":
        raise ValueError("Thread is finalized. Draft sending is only available before finalize")

    state = _parse_jsonb(thread_row["current_state"])
    normalized_recipients = normalize_recipient_emails(recipient_emails)
    if not normalized_recipients:
        normalized_recipients = _coerce_offer_draft_recipient_emails(state)
    if not normalized_recipients:
        raise ValueError("At least one valid recipient email is required")
    if len(normalized_recipients) > 20:
        raise ValueError("A maximum of 20 recipients is supported per draft send")

    # Reuse existing draft-save validations and persist the latest state first.
    draft_result = await save_offer_letter_draft(thread_id, company_id)

    version = int(thread_row["version"] or 0)
    pdf_url = await generate_pdf(
        state,
        thread_id,
        version,
        is_draft=True,
        company_id=company_id,
    )
    if not pdf_url:
        raise ValueError("Unable to generate draft PDF")

    try:
        pdf_bytes = await get_storage().download_file(pdf_url)
    except Exception as exc:
        logger.warning("Failed to download Matcha Work draft PDF for thread %s: %s", thread_id, exc)
        raise ValueError("Unable to load draft PDF for email attachment") from exc

    attachment_filename = f"offer-letter-draft-v{version}.pdf"
    attachment = {
        "filename": attachment_filename,
        "content": base64.b64encode(pdf_bytes).decode("ascii"),
        "disposition": "attachment",
    }

    candidate_name = str(state.get("candidate_name") or "").strip()
    position_title = str(state.get("position_title") or "").strip()
    company_name = str(thread_row["company_name"] or "").strip() or "Your HR Team"

    subject = (
        f"Offer letter draft for review — {candidate_name} ({position_title})"
        if candidate_name and position_title
        else "Offer letter draft for review"
    )
    html_content = _render_offer_letter_draft_email_html(
        company_name=company_name,
        candidate_name=candidate_name,
        position_title=position_title,
        custom_message=custom_message,
    )
    text_content = (
        f"{company_name} shared an offer letter draft for {candidate_name or 'a candidate'} "
        f"({position_title or 'position attached'}). The draft PDF is attached for review."
    )

    email_service = EmailService()
    sent_count = 0
    failed_count = 0
    recipients: list[dict] = []

    for recipient_email in normalized_recipients:
        status_value = "failed"
        last_error = None
        if not email_service.is_configured():
            last_error = "email_service_not_configured"
        else:
            try:
                sent = await email_service.send_email(
                    to_email=recipient_email,
                    to_name=None,
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content,
                    attachments=[attachment],
                )
                if sent:
                    status_value = "sent"
                else:
                    last_error = "send_failed"
            except Exception as exc:
                logger.warning(
                    "Failed to send Matcha Work offer draft email to %s: %s",
                    recipient_email,
                    exc,
                )
                last_error = "send_exception"

        if status_value == "sent":
            sent_count += 1
        else:
            failed_count += 1
        recipients.append(
            {
                "email": recipient_email,
                "status": status_value,
                "last_error": last_error,
            }
        )

    await add_message(
        thread_id,
        "system",
        (
            f"Offer letter draft email send attempted: {sent_count} sent, "
            f"{failed_count} failed ({len(normalized_recipients)} recipient(s))."
        ),
        version_created=None,
    )

    return {
        "thread_id": thread_id,
        "version": version,
        "pdf_url": pdf_url,
        "sent_count": sent_count,
        "failed_count": failed_count,
        "recipients": recipients,
        "linked_offer_letter_id": draft_result["linked_offer_letter_id"],
        "offer_status": draft_result["offer_status"],
        "saved_at": draft_result["saved_at"],
    }


async def generate_workbook_presentation(thread_id: UUID, company_id: UUID) -> dict:
    """Generate slide-ready presentation state from a workbook thread."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT current_state, status
            FROM mw_threads
            WHERE id=$1 AND company_id=$2
            """,
            thread_id,
            company_id,
        )
    if row is None:
        raise ValueError("Thread not found")
    if row["status"] == "archived":
        raise ValueError("Cannot generate a presentation for an archived thread")
    if row["status"] == "finalized":
        raise ValueError("Cannot generate a presentation for a finalized thread")

    initial_state = _parse_jsonb(row["current_state"])
    initial_presentation = _build_workbook_presentation_state(initial_state)
    cover_url = await generate_cover_image(
        presentation_title=initial_presentation.get("title") or "Presentation",
        subtitle=initial_presentation.get("subtitle"),
        company_id=company_id,
        thread_id=thread_id,
    )

    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT current_state, version, status
                FROM mw_threads
                WHERE id=$1 AND company_id=$2
                FOR UPDATE
                """,
                thread_id,
                company_id,
            )
            if row is None:
                raise ValueError("Thread not found")
            if row["status"] == "archived":
                raise ValueError("Cannot generate a presentation for an archived thread")
            if row["status"] == "finalized":
                raise ValueError("Cannot generate a presentation for a finalized thread")

            current_state = _parse_jsonb(row["current_state"])
            presentation = _build_workbook_presentation_state(current_state)
            if cover_url:
                presentation["cover_image_url"] = cover_url
            merged_state = {**current_state, "presentation": presentation}
            new_version = int(row["version"] or 0) + 1

            await conn.execute(
                """
                UPDATE mw_threads
                SET current_state=$1, version=$2, updated_at=NOW()
                WHERE id=$3
                """,
                json.dumps(merged_state),
                new_version,
                thread_id,
            )
            await conn.execute(
                """
                INSERT INTO mw_document_versions(thread_id, version, state_json, diff_summary)
                VALUES($1, $2, $3, $4)
                ON CONFLICT(thread_id, version) DO NOTHING
                """,
                thread_id,
                new_version,
                json.dumps(merged_state),
                "Generated workbook presentation",
            )
            await conn.execute(
                """
                INSERT INTO mw_messages(thread_id, role, content, version_created)
                VALUES($1, 'system', $2, $3)
                """,
                thread_id,
                f"Generated presentation with {presentation['slide_count']} slides.",
                new_version,
            )
            await _sync_element_for_thread(conn, thread_id)

    return {
        "thread_id": thread_id,
        "version": new_version,
        "current_state": merged_state,
        "slide_count": presentation["slide_count"],
        "generated_at": presentation["generated_at"],
    }


async def finalize_thread(thread_id: UUID, company_id: UUID) -> dict:
    """Lock thread status to 'finalized' and generate final PDF (no watermark)."""
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT current_state, version, status
                FROM mw_threads
                WHERE id=$1 AND company_id=$2
                FOR UPDATE
                """,
                thread_id,
                company_id,
            )
            if row is None:
                raise ValueError("Thread not found")
            if row["status"] == "finalized":
                raise ValueError("Thread is already finalized")
            if row["status"] == "archived":
                raise ValueError("Cannot finalize an archived thread")

            await conn.execute(
                "UPDATE mw_threads SET status='finalized', updated_at=NOW() WHERE id=$1",
                thread_id,
            )
            await _sync_element_for_thread(conn, thread_id)
            current_state = _parse_jsonb(row["current_state"])
            version = row["version"]

    pdf_url = None
    if _infer_skill_from_state(current_state) == "offer_letter":
        # Generate final PDF outside the transaction (CPU-bound, may be slow)
        pdf_url = await generate_pdf(
            current_state,
            thread_id,
            version,
            is_draft=False,
            company_id=company_id,
        )

    return {
        "thread_id": thread_id,
        "status": "finalized",
        "version": version,
        "pdf_url": pdf_url,
        "linked_offer_letter_id": None,
    }


async def _list_review_requests_for_thread(thread_id: UUID) -> list[dict]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT recipient_email, status, sent_at, submitted_at, last_error
            FROM mw_review_requests
            WHERE thread_id=$1
            ORDER BY recipient_email ASC
            """,
            thread_id,
        )
    return [_row_to_review_request_status(dict(row)) for row in rows]


async def list_review_requests(thread_id: UUID, company_id: UUID) -> list[dict]:
    async with get_connection() as conn:
        thread_exists = await conn.fetchval(
            """
            SELECT EXISTS(
                SELECT 1
                FROM mw_threads
                WHERE id=$1 AND company_id=$2
            )
            """,
            thread_id,
            company_id,
        )
    if not thread_exists:
        raise ValueError("Thread not found")
    return await _list_review_requests_for_thread(thread_id)


async def sync_review_request_state(thread_id: UUID) -> dict:
    status_rows = await _list_review_requests_for_thread(thread_id)
    updates = _build_review_request_state_update(status_rows)
    update_keys = set(updates.keys())

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT current_state, version
            FROM mw_threads
            WHERE id=$1
            """,
            thread_id,
        )
    if row is None:
        raise ValueError("Thread not found")

    current_state = _parse_jsonb(row["current_state"])
    unchanged = True
    for key in update_keys:
        if current_state.get(key) != updates.get(key):
            unchanged = False
            break
    if unchanged:
        return {"version": row["version"], "current_state": current_state}

    return await apply_update(
        thread_id,
        updates,
        diff_summary="Updated review request tracking",
    )


async def send_review_requests(
    thread_id: UUID,
    company_id: UUID,
    recipient_emails: list[str],
    custom_message: Optional[str] = None,
) -> dict:
    async with get_connection() as conn:
        thread_row = await conn.fetchrow(
            """
            SELECT title, status, current_state, c.name AS company_name
            FROM mw_threads t
            JOIN companies c ON c.id = t.company_id
            WHERE t.id=$1 AND t.company_id=$2
            """,
            thread_id,
            company_id,
        )
    if thread_row is None:
        raise ValueError("Thread not found")

    if thread_row["status"] == "archived":
        raise ValueError("Cannot send review requests for an archived thread")

    state = _parse_jsonb(thread_row["current_state"])
    normalized_recipients = normalize_recipient_emails(recipient_emails)
    if not normalized_recipients:
        normalized_recipients = _coerce_state_recipient_emails(state)
    if not normalized_recipients:
        raise ValueError("At least one valid recipient email is required")
    if len(normalized_recipients) > 100:
        raise ValueError("A maximum of 100 recipient emails is supported per send")

    review_title = (
        state.get("review_title")
        or state.get("review_subject")
        or thread_row["title"]
        or "Anonymous Performance Review"
    )
    company_name = thread_row["company_name"] or "Your HR Team"
    settings = get_settings()
    app_base_url = (settings.app_base_url or "").rstrip("/")
    if not app_base_url:
        raise ValueError("APP_BASE_URL is required to send review request links")

    pending_requests: list[dict] = []
    async with get_connection() as conn:
        async with conn.transaction():
            existing_rows = await conn.fetch(
                """
                SELECT recipient_email, status
                FROM mw_review_requests
                WHERE thread_id=$1
                  AND recipient_email = ANY($2::text[])
                FOR UPDATE
                """,
                thread_id,
                normalized_recipients,
            )
            existing_status_by_email = {
                str(row["recipient_email"]).strip().lower(): str(row["status"] or "pending")
                for row in existing_rows
            }
            await conn.execute(
                """
                DELETE FROM mw_review_requests
                WHERE thread_id=$1
                  AND status != 'submitted'
                  AND NOT (recipient_email = ANY($2::text[]))
                """,
                thread_id,
                normalized_recipients,
            )
            for email in normalized_recipients:
                if existing_status_by_email.get(email) == "submitted":
                    continue
                token = secrets.token_urlsafe(24)
                row = await conn.fetchrow(
                    """
                    INSERT INTO mw_review_requests(
                        thread_id, company_id, recipient_email, token, status
                    )
                    VALUES($1, $2, $3, $4, 'pending')
                    ON CONFLICT(thread_id, recipient_email) DO UPDATE
                    SET token=EXCLUDED.token,
                        status='pending',
                        sent_at=NULL,
                        submitted_at=NULL,
                        last_error=NULL,
                        feedback=NULL,
                        rating=NULL,
                        updated_at=NOW()
                    RETURNING recipient_email, token
                    """,
                    thread_id,
                    company_id,
                    email,
                    token,
                )
                pending_requests.append(dict(row))

    email_service = EmailService()
    sent_count = 0
    failed_count = 0

    async with get_connection() as conn:
        for request_row in pending_requests:
            recipient_email = request_row["recipient_email"]
            token = request_row["token"]
            response_url = f"{app_base_url}/review-request/{token}"
            subject = f"Anonymous review request: {review_title}"
            html_content = _render_review_request_email_html(
                review_title=review_title,
                company_name=company_name,
                response_url=response_url,
                custom_message=custom_message,
            )

            status_value = "failed"
            sent_at = None
            last_error = None
            if not email_service.is_configured():
                last_error = "email_service_not_configured"
            else:
                try:
                    sent = await email_service.send_email(
                        to_email=recipient_email,
                        to_name=None,
                        subject=subject,
                        html_content=html_content,
                    )
                    if sent:
                        status_value = "sent"
                        sent_at = datetime.now(timezone.utc)
                    else:
                        last_error = "send_failed"
                except Exception as e:
                    logger.warning(
                        "Failed to send Matcha Work review request email to %s: %s",
                        recipient_email,
                        e,
                    )
                    last_error = "send_exception"

            if status_value == "sent":
                sent_count += 1
            else:
                failed_count += 1

            await conn.execute(
                """
                UPDATE mw_review_requests
                SET status=$1,
                    sent_at=$2,
                    last_error=$3,
                    updated_at=NOW()
                WHERE thread_id=$4 AND recipient_email=$5
                """,
                status_value,
                sent_at,
                last_error,
                thread_id,
                recipient_email,
            )

    state_sync = await sync_review_request_state(thread_id)
    status_rows = await _list_review_requests_for_thread(thread_id)
    expected_responses = len(status_rows)
    received_responses = sum(1 for row in status_rows if row["status"] == "submitted")
    pending_responses = max(expected_responses - received_responses, 0)

    await add_message(
        thread_id,
        "system",
        (
            f"Review requests sent to {expected_responses} recipient(s): "
            f"{sent_count} sent, {failed_count} failed. "
            f"Received {received_responses}/{expected_responses} response(s)."
        ),
        version_created=state_sync["version"],
    )

    return {
        "thread_id": thread_id,
        "expected_responses": expected_responses,
        "received_responses": received_responses,
        "pending_responses": pending_responses,
        "sent_count": sent_count,
        "failed_count": failed_count,
        "recipients": status_rows,
    }


async def get_public_review_request(token: str) -> Optional[dict]:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                r.recipient_email,
                r.status,
                r.submitted_at,
                t.title,
                t.current_state
            FROM mw_review_requests r
            JOIN mw_threads t ON t.id = r.thread_id
            WHERE r.token=$1
            """,
            token,
        )
    if row is None:
        return None

    state = _parse_jsonb(row["current_state"])
    review_title = (
        state.get("review_title")
        or state.get("review_subject")
        or row["title"]
        or "Anonymous Performance Review"
    )

    return {
        "token": token,
        "review_title": review_title,
        "recipient_email": row["recipient_email"],
        "status": row["status"],
        "submitted_at": row["submitted_at"],
    }


async def submit_public_review_request(
    token: str,
    feedback: str,
    rating: Optional[int] = None,
) -> dict:
    async with get_connection() as conn:
        async with conn.transaction():
            existing = await conn.fetchrow(
                """
                SELECT id, thread_id, recipient_email, status
                FROM mw_review_requests
                WHERE token=$1
                FOR UPDATE
                """,
                token,
            )
            if existing is None:
                raise ValueError("Review request not found")
            if existing["status"] == "submitted":
                raise ValueError("Review response already submitted")

            updated = await conn.fetchrow(
                """
                UPDATE mw_review_requests
                SET status='submitted',
                    feedback=$1,
                    rating=$2,
                    submitted_at=NOW(),
                    last_error=NULL,
                    updated_at=NOW()
                WHERE id=$3
                RETURNING thread_id, submitted_at
                """,
                feedback.strip(),
                rating,
                existing["id"],
            )

    thread_id = updated["thread_id"]
    state_sync = await sync_review_request_state(thread_id)
    await add_message(
        thread_id,
        "system",
        "A review response was submitted from one of the requested recipients.",
        version_created=state_sync["version"],
    )

    return {
        "status": "submitted",
        "submitted_at": updated["submitted_at"],
    }
