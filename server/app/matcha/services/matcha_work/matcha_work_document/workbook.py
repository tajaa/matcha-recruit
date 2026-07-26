"""Workbook → presentation generation + thread finalization."""
import json
from uuid import UUID

from app.database import get_connection

from ._coerce import _parse_jsonb, _infer_skill_from_state, _build_workbook_presentation_state
from .pdf import generate_cover_image, generate_pdf
from .elements import _sync_element_for_thread


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
