import asyncio
import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from ...database import get_connection
from ...core.services.storage import get_storage

logger = logging.getLogger(__name__)


def _parse_jsonb(value) -> dict:
    """Parse a JSONB value from asyncpg (may be str or dict)."""
    if isinstance(value, str):
        return json.loads(value)
    if isinstance(value, dict):
        return value
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


async def create_thread(
    company_id: UUID,
    user_id: UUID,
    title: str = "Untitled Offer Letter",
) -> dict:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO mw_threads(company_id, created_by, title)
            VALUES($1, $2, $3)
            RETURNING id, title, status, current_state, version, created_at, updated_at
            """,
            company_id,
            user_id,
            title,
        )
        d = dict(row)
        d["current_state"] = _parse_jsonb(d["current_state"])
        return d


async def get_thread(thread_id: UUID, company_id: UUID) -> Optional[dict]:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, company_id, created_by, title, task_type, status,
                   current_state, version, linked_offer_letter_id,
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
                SELECT id, title, task_type, status, version, created_at, updated_at
                FROM mw_threads
                WHERE company_id=$1 AND status=$2
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
                SELECT id, title, task_type, status, version, created_at, updated_at
                FROM mw_threads
                WHERE company_id=$1
                ORDER BY updated_at DESC
                LIMIT $2 OFFSET $3
                """,
                company_id,
                limit,
                offset,
            )
        return [dict(r) for r in rows]


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
            current_state = _parse_jsonb(row["current_state"])
            version = row["version"]

    # Generate final PDF outside the transaction (CPU-bound, may be slow)
    pdf_url = await generate_pdf(current_state, thread_id, version, is_draft=False)

    return {
        "thread_id": thread_id,
        "status": "finalized",
        "version": version,
        "pdf_url": pdf_url,
        "linked_offer_letter_id": None,
    }
