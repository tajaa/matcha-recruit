"""
Migrate existing Matcha Work S3 objects into company-scoped prefixes.

Run with:
    python -m scripts.migrate_matcha_work_storage_scope
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_settings
from app.core.services.storage import get_storage
from app.database import close_pool, get_connection, init_pool
from app.matcha.services import matcha_work_document as doc_svc


async def migrate_thread_assets() -> tuple[int, int]:
    scanned = 0
    changed = 0

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, company_id, current_state
            FROM mw_threads
            ORDER BY created_at ASC
            """
        )

    for row in rows:
        scanned += 1
        thread_id = row["id"]
        company_id = row["company_id"]
        current_state = doc_svc._parse_jsonb(row["current_state"])
        normalized_state = await doc_svc.ensure_matcha_work_thread_storage_scope(
            thread_id,
            company_id,
            current_state,
        )
        if normalized_state != current_state:
            changed += 1
            print(f"migrated thread assets: thread={thread_id} company={company_id}")

    return scanned, changed


async def migrate_pdf_cache() -> tuple[int, int]:
    storage = get_storage()
    scanned = 0
    changed = 0

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT c.thread_id, c.version, c.is_draft, c.pdf_url, t.company_id, t.current_state
            FROM mw_pdf_cache c
            JOIN mw_threads t ON t.id = c.thread_id
            ORDER BY c.created_at ASC NULLS LAST
            """
        )

    for row in rows:
        scanned += 1
        thread_id = row["thread_id"]
        company_id = row["company_id"]
        pdf_url = row["pdf_url"]
        state = doc_svc._parse_jsonb(row["current_state"])
        skill = doc_svc._infer_skill_from_state(state)
        asset_kind = "pdfs" if skill == "offer_letter" else "presentation-pdfs"
        expected_prefix = doc_svc.build_matcha_work_thread_storage_prefix(company_id, thread_id, asset_kind)

        if doc_svc._storage_path_has_prefix(pdf_url, expected_prefix):
            continue
        if not storage.is_supported_storage_path(pdf_url):
            print(f"skipped unsupported pdf cache url: thread={thread_id} url={pdf_url}")
            continue

        try:
            pdf_bytes = await storage.download_file(pdf_url)
        except Exception as exc:
            print(f"skipped unreadable pdf: thread={thread_id} url={pdf_url}: {exc}")
            continue

        filename = doc_svc._storage_filename(
            pdf_url,
            f"v{row['version']}{'_draft' if row['is_draft'] else ''}.pdf",
        )
        new_pdf_url = await storage.upload_file(
            pdf_bytes,
            filename,
            prefix=expected_prefix,
            content_type="application/pdf",
        )

        async with get_connection() as conn:
            await conn.execute(
                """
                UPDATE mw_pdf_cache
                SET pdf_url=$1
                WHERE thread_id=$2 AND version=$3 AND is_draft=$4
                """,
                new_pdf_url,
                thread_id,
                row["version"],
                row["is_draft"],
            )

        if new_pdf_url != pdf_url:
            try:
                await storage.delete_file(pdf_url)
            except Exception as exc:
                print(f"warning: failed to delete legacy pdf {pdf_url}: {exc}")

        changed += 1
        print(f"migrated cached pdf: thread={thread_id} version={row['version']} company={company_id}")

    return scanned, changed


async def main() -> None:
    settings = load_settings()
    await init_pool(settings.database_url)

    try:
        if not doc_svc._should_enforce_company_scoped_matcha_work_storage():
            raise RuntimeError("S3 storage is not configured; Matcha Work storage migration is not applicable.")

        thread_scanned, thread_changed = await migrate_thread_assets()
        pdf_scanned, pdf_changed = await migrate_pdf_cache()

        print(
            "done:",
            f"thread_rows={thread_scanned}",
            f"thread_rows_changed={thread_changed}",
            f"pdf_cache_rows={pdf_scanned}",
            f"pdf_cache_rows_changed={pdf_changed}",
        )
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
