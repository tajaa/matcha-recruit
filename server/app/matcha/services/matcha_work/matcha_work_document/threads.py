"""Thread CRUD/list."""
import json
import logging
from typing import Optional
from uuid import UUID

from app.database import get_connection
from app.matcha.services.matcha_work.matcha_work_modes import MODE_COLUMNS_SQL

from ._coerce import _parse_jsonb
from ._profile import get_company_profile_for_ai
from .elements import _upsert_element_from_thread_row

logger = logging.getLogger(__name__)


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
