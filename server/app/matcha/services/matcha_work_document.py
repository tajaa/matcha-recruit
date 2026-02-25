import asyncio
import html
import json
import logging
import re
import secrets
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from ...database import get_connection
from ...config import get_settings
from ...core.services.email import EmailService
from ...core.services.storage import get_storage

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
VALID_REVIEW_REQUEST_STATUSES = {"pending", "sent", "failed", "submitted"}


def _parse_jsonb(value) -> dict:
    """Parse a JSONB value from asyncpg (may be str or dict)."""
    if isinstance(value, str):
        return json.loads(value)
    if isinstance(value, dict):
        return value
    return {}


def _default_state_for_task_type(task_type: str) -> dict:
    if task_type == "review":
        return {
            "review_title": "Anonymous Performance Review",
            "anonymized": True,
            "recipient_emails": [],
            "review_request_statuses": [],
            "review_expected_responses": 0,
            "review_received_responses": 0,
            "review_pending_responses": 0,
        }
    if task_type == "workbook":
        return {
            "workbook_title": "HR Workbook",
            "sections": [],
        }
    return {}


def _parse_date_str(date_str: str) -> Optional[datetime]:
    """Try common date formats."""
    formats = [
        "%Y-%m-%d",
        "%B %d, %Y",
        "%b %d, %Y",
        "%m/%d/%Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def _coerce_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n", ""}:
            return False
    return default


def _coerce_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_datetime(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return _parse_date_str(value)
    return None


def _normalize_email(email: str) -> Optional[str]:
    normalized = (email or "").strip().lower()
    if not normalized:
        return None
    if not EMAIL_REGEX.fullmatch(normalized):
        return None
    return normalized


def normalize_recipient_emails(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for raw in values:
        email = _normalize_email(raw)
        if not email or email in seen:
            continue
        seen.add(email)
        deduped.append(email)
    return deduped


def _coerce_state_recipient_emails(state: dict) -> list[str]:
    raw = state.get("recipient_emails")
    if not isinstance(raw, list):
        return []
    return normalize_recipient_emails([str(item) for item in raw])


def _row_to_review_request_status(row: dict) -> dict:
    status = str(row.get("status") or "pending")
    if status not in VALID_REVIEW_REQUEST_STATUSES:
        status = "pending"
    return {
        "email": str(row.get("recipient_email") or "").strip().lower(),
        "status": status,
        "sent_at": row.get("sent_at"),
        "submitted_at": row.get("submitted_at"),
        "last_error": row.get("last_error"),
    }


def _build_review_request_state_update(status_rows: list[dict]) -> dict:
    recipient_emails = [str(row.get("email") or "").strip().lower() for row in status_rows if row.get("email")]
    expected = len(recipient_emails)
    received = sum(1 for row in status_rows if row.get("status") == "submitted")
    pending = max(expected - received, 0)

    latest_sent_at = None
    for row in status_rows:
        sent_at = row.get("sent_at")
        if isinstance(sent_at, datetime):
            if latest_sent_at is None or sent_at > latest_sent_at:
                latest_sent_at = sent_at

    serialized_status_rows = []
    for row in status_rows:
        serialized_status_rows.append(
            {
                "email": row.get("email"),
                "status": row.get("status"),
                "sent_at": row.get("sent_at").isoformat() if isinstance(row.get("sent_at"), datetime) else None,
                "submitted_at": (
                    row.get("submitted_at").isoformat()
                    if isinstance(row.get("submitted_at"), datetime)
                    else None
                ),
                "last_error": row.get("last_error"),
            }
        )

    return {
        "recipient_emails": recipient_emails,
        "review_request_statuses": serialized_status_rows,
        "review_expected_responses": expected,
        "review_received_responses": received,
        "review_pending_responses": pending,
        "review_last_sent_at": latest_sent_at.isoformat() if latest_sent_at else None,
    }


def _render_review_request_email_html(
    review_title: str,
    company_name: str,
    response_url: str,
    custom_message: Optional[str],
) -> str:
    escaped_title = html.escape(review_title.strip() or "Anonymous Performance Review")
    escaped_company = html.escape(company_name.strip() or "Your HR Team")
    message_block = (
        f"<p>{html.escape(custom_message.strip())}</p>"
        if custom_message and custom_message.strip()
        else ""
    )
    return f"""
<!DOCTYPE html>
<html>
  <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #111827; line-height: 1.5;">
    <div style="max-width: 560px; margin: 0 auto; padding: 20px;">
      <h2 style="margin: 0 0 12px;">Anonymous Review Request</h2>
      <p style="margin: 0 0 12px;">{escaped_company} is requesting your feedback for: <strong>{escaped_title}</strong>.</p>
      {message_block}
      <p style="margin: 0 0 16px;">Use the secure link below to submit your review response:</p>
      <p style="margin: 0 0 18px;">
        <a href="{response_url}" style="display: inline-block; background: #16a34a; color: white; padding: 10px 16px; text-decoration: none; border-radius: 6px;">
          Submit Anonymous Review
        </a>
      </p>
      <p style="margin: 0; color: #6b7280; font-size: 12px;">
        If the button does not work, open this link directly: {response_url}
      </p>
    </div>
  </body>
</html>
"""


def _build_offer_letter_payload(state: dict, fallback_company_name: str) -> dict:
    company_name = (state.get("company_name") or fallback_company_name or "").strip()
    return {
        "candidate_name": (state.get("candidate_name") or "").strip(),
        "position_title": (state.get("position_title") or "").strip(),
        "company_name": company_name,
        "salary": state.get("salary"),
        "bonus": state.get("bonus"),
        "stock_options": state.get("stock_options"),
        "start_date": _coerce_datetime(state.get("start_date")),
        "employment_type": state.get("employment_type"),
        "location": state.get("location"),
        "benefits": state.get("benefits"),
        "manager_name": state.get("manager_name"),
        "manager_title": state.get("manager_title"),
        "expiration_date": _coerce_datetime(state.get("expiration_date")),
        "benefits_medical": _coerce_bool(state.get("benefits_medical"), False),
        "benefits_medical_coverage": _coerce_int(state.get("benefits_medical_coverage")),
        "benefits_medical_waiting_days": _coerce_int(state.get("benefits_medical_waiting_days")) or 0,
        "benefits_dental": _coerce_bool(state.get("benefits_dental"), False),
        "benefits_vision": _coerce_bool(state.get("benefits_vision"), False),
        "benefits_401k": _coerce_bool(state.get("benefits_401k"), False),
        "benefits_401k_match": state.get("benefits_401k_match"),
        "benefits_wellness": state.get("benefits_wellness"),
        "benefits_pto_vacation": _coerce_bool(state.get("benefits_pto_vacation"), False),
        "benefits_pto_sick": _coerce_bool(state.get("benefits_pto_sick"), False),
        "benefits_holidays": _coerce_bool(state.get("benefits_holidays"), False),
        "benefits_other": state.get("benefits_other"),
        "contingency_background_check": _coerce_bool(state.get("contingency_background_check"), False),
        "contingency_credit_check": _coerce_bool(state.get("contingency_credit_check"), False),
        "contingency_drug_screening": _coerce_bool(state.get("contingency_drug_screening"), False),
        "company_logo_url": state.get("company_logo_url"),
        "salary_range_min": _coerce_float(state.get("salary_range_min")),
        "salary_range_max": _coerce_float(state.get("salary_range_max")),
        "candidate_email": state.get("candidate_email"),
    }


async def create_thread(
    company_id: UUID,
    user_id: UUID,
    title: str = "Untitled Chat",
    task_type: str = "offer_letter",
) -> dict:
    if task_type == "review":
        normalized_task_type = "review"
    elif task_type == "workbook":
        normalized_task_type = "workbook"
    else:
        normalized_task_type = "offer_letter"

    default_state = _default_state_for_task_type(normalized_task_type)
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO mw_threads(company_id, created_by, title, task_type, current_state)
                VALUES($1, $2, $3, $4, $5::jsonb)
                RETURNING id, company_id, created_by, title, task_type, status,
                          current_state, version, is_pinned, linked_offer_letter_id,
                          created_at, updated_at
                """,
                company_id,
                user_id,
                title,
                normalized_task_type,
                json.dumps(default_state),
            )
            await _upsert_element_from_thread_row(conn, dict(row))
        d = dict(row)
        d["current_state"] = _parse_jsonb(d["current_state"])
        return d


async def get_thread(thread_id: UUID, company_id: UUID) -> Optional[dict]:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, company_id, created_by, title, task_type, status,
                   current_state, version, is_pinned, linked_offer_letter_id,
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


async def list_threads(
    company_id: UUID,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    async with get_connection() as conn:
        if status:
            rows = await conn.fetch(
                """
                SELECT id, title, task_type, status, version, is_pinned, created_at, updated_at
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
            rows = await conn.fetch(
                """
                SELECT id, title, task_type, status, version, is_pinned, created_at, updated_at
                FROM mw_threads
                WHERE company_id=$1
                ORDER BY is_pinned DESC, updated_at DESC
                LIMIT $2 OFFSET $3
                """,
                company_id,
                limit,
                offset,
            )
        return [dict(r) for r in rows]


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


async def _upsert_element_from_thread_row(conn, thread_row: dict) -> None:
    try:
        state_json = _parse_jsonb(thread_row.get("current_state"))
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
            thread_row.get("task_type") or "offer_letter",
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
            SELECT id, company_id, created_by, task_type, title, status,
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
            """
            UPDATE mw_threads
            SET is_pinned=$1, updated_at=NOW()
            WHERE id=$2 AND company_id=$3
            RETURNING id, title, task_type, status, version, is_pinned, created_at, updated_at
            """,
            is_pinned,
            thread_id,
            company_id,
        )
        if row is None:
            return None
        await _sync_element_for_thread(conn, thread_id)
        return dict(row)


async def set_thread_task_type(
    thread_id: UUID,
    company_id: UUID,
    task_type: str,
) -> Optional[dict]:
    if task_type == "review":
        normalized_task_type = "review"
    elif task_type == "workbook":
        normalized_task_type = "workbook"
    else:
        normalized_task_type = "offer_letter"

    default_state = _default_state_for_task_type(normalized_task_type)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE mw_threads
            SET task_type=$1, current_state=$2::jsonb, updated_at=NOW()
            WHERE id=$3 AND company_id=$4
            RETURNING id, company_id, created_by, title, task_type, status,
                      current_state, version, is_pinned, linked_offer_letter_id,
                      created_at, updated_at
            """,
            normalized_task_type,
            json.dumps(default_state),
            thread_id,
            company_id,
        )
        if row is None:
            return None
        await _sync_element_for_thread(conn, thread_id)
        d = dict(row)
        d["current_state"] = _parse_jsonb(d["current_state"])
        return d


async def get_thread_messages(thread_id: UUID) -> list[dict]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, thread_id, role, content, version_created, created_at
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
) -> dict:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO mw_messages(thread_id, role, content, version_created)
            VALUES($1, $2, $3, $4)
            RETURNING id, thread_id, role, content, version_created, created_at
            """,
            thread_id,
            role,
            content,
            version_created,
        )
        return dict(row)


async def log_token_usage_event(
    company_id: UUID,
    user_id: UUID,
    thread_id: UUID,
    token_usage: Optional[dict],
    operation: str = "send_message",
) -> None:
    if not token_usage:
        return

    model = str(token_usage.get("model") or "unknown").strip() or "unknown"
    prompt_tokens = _coerce_int(token_usage.get("prompt_tokens"))
    completion_tokens = _coerce_int(token_usage.get("completion_tokens"))
    total_tokens = _coerce_int(token_usage.get("total_tokens"))
    if total_tokens is None and (prompt_tokens is not None or completion_tokens is not None):
        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

    estimated = _coerce_bool(token_usage.get("estimated"), False)

    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO mw_token_usage_events(
                company_id, user_id, thread_id, model,
                prompt_tokens, completion_tokens, total_tokens,
                estimated, operation
            )
            VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            company_id,
            user_id,
            thread_id,
            model,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            estimated,
            operation,
        )


async def get_token_usage_summary(
    company_id: UUID,
    user_id: UUID,
    period_days: int = 30,
) -> dict:
    async with get_connection() as conn:
        by_model_rows = await conn.fetch(
            """
            SELECT
                model,
                COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COUNT(*) AS operation_count,
                COUNT(*) FILTER (WHERE estimated) AS estimated_operations,
                MIN(created_at) AS first_seen_at,
                MAX(created_at) AS last_seen_at
            FROM mw_token_usage_events
            WHERE company_id=$1
              AND user_id=$2
              AND created_at >= NOW() - ($3::int * INTERVAL '1 day')
            GROUP BY model
            ORDER BY total_tokens DESC, model ASC
            """,
            company_id,
            user_id,
            period_days,
        )

        totals_row = await conn.fetchrow(
            """
            SELECT
                COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COUNT(*) AS operation_count,
                COUNT(*) FILTER (WHERE estimated) AS estimated_operations
            FROM mw_token_usage_events
            WHERE company_id=$1
              AND user_id=$2
              AND created_at >= NOW() - ($3::int * INTERVAL '1 day')
            """,
            company_id,
            user_id,
            period_days,
        )

    return {
        "period_days": period_days,
        "generated_at": datetime.now(timezone.utc),
        "totals": {
            "prompt_tokens": totals_row["prompt_tokens"] if totals_row else 0,
            "completion_tokens": totals_row["completion_tokens"] if totals_row else 0,
            "total_tokens": totals_row["total_tokens"] if totals_row else 0,
            "operation_count": totals_row["operation_count"] if totals_row else 0,
            "estimated_operations": totals_row["estimated_operations"] if totals_row else 0,
        },
        "by_model": [
            {
                "model": row["model"],
                "prompt_tokens": row["prompt_tokens"],
                "completion_tokens": row["completion_tokens"],
                "total_tokens": row["total_tokens"],
                "operation_count": row["operation_count"],
                "estimated_operations": row["estimated_operations"],
                "first_seen_at": row["first_seen_at"],
                "last_seen_at": row["last_seen_at"],
            }
            for row in by_model_rows
        ],
    }


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


async def list_versions(thread_id: UUID) -> list[dict]:
    async with get_connection() as conn:
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


async def _get_cached_pdf_url(thread_id: UUID, version: int, is_draft: bool) -> Optional[str]:
    async with get_connection() as conn:
        return await conn.fetchval(
            """
            SELECT pdf_url
            FROM mw_pdf_cache
            WHERE thread_id=$1 AND version=$2 AND is_draft=$3
            """,
            thread_id,
            version,
            is_draft,
        )


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
    is_draft: bool = True,
    logo_src: Optional[str] = None,
) -> Optional[str]:
    """Check cache → render HTML → WeasyPrint → S3 → cache URL."""
    cached = await _get_cached_pdf_url(thread_id, version, is_draft)
    if cached:
        return cached

    # Lazy import to avoid circular imports at module load time
    from ..routes.offer_letters import _generate_offer_letter_html

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
            from weasyprint import HTML

            return HTML(string=html_content).write_pdf()
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
            prefix=f"matcha-work/{thread_id}",
            content_type="application/pdf",
        )
    except Exception as e:
        logger.error("Failed to upload PDF to storage: %s", e, exc_info=True)
        return None

    await _cache_pdf_url(thread_id, version, pdf_url, is_draft=is_draft)
    return pdf_url


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


async def finalize_thread(thread_id: UUID, company_id: UUID) -> dict:
    """Lock thread status to 'finalized' and generate final PDF (no watermark)."""
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT current_state, version, status, task_type
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
            task_type = row["task_type"]

    pdf_url = None
    if task_type == "offer_letter":
        # Generate final PDF outside the transaction (CPU-bound, may be slow)
        pdf_url = await generate_pdf(current_state, thread_id, version, is_draft=False)

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
            SELECT title, task_type, status, current_state, c.name AS company_name
            FROM mw_threads t
            JOIN companies c ON c.id = t.company_id
            WHERE t.id=$1 AND t.company_id=$2
            """,
            thread_id,
            company_id,
        )
    if thread_row is None:
        raise ValueError("Thread not found")

    if thread_row["task_type"] != "review":
        raise ValueError("Review requests are only available for review threads")
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
            await conn.execute(
                """
                DELETE FROM mw_review_requests
                WHERE thread_id=$1
                  AND NOT (recipient_email = ANY($2::text[]))
                """,
                thread_id,
                normalized_recipients,
            )
            for email in normalized_recipients:
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
