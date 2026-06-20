"""Celery task: extract a CBA's clause library + grievance procedure via Gemini.

Dispatched ad-hoc from the CBA document-upload / re-extract routes. Downloads
the stored private PDF, parses text, runs the Labor Relations AI extractor, and
writes ``ai_extracted`` clauses + a best-effort grievance_step_config. The step
config is only seeded when the CBA has none yet (never clobbers HR edits) and is
advisory until a human confirms it.
"""

import asyncio
import json
from uuid import UUID

from ..celery_app import celery_app
from ..utils import get_db_connection


def _as_list(jsonb_val) -> list:
    """asyncpg may return jsonb as a str or already-decoded list — normalize."""
    if jsonb_val is None:
        return []
    if isinstance(jsonb_val, list):
        return jsonb_val
    try:
        parsed = json.loads(jsonb_val)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


async def _extract(cba_id: str) -> dict:
    from app.core.services.storage import get_storage
    from app.matcha.services.er_document_parser import ERDocumentParser
    from app.matcha.services.labor_relations_ai import extract_clauses_from_cba

    conn = await get_db_connection()
    try:
        cba = await conn.fetchrow(
            "SELECT id, company_id, document_storage_path, document_filename, grievance_step_config "
            "FROM lr_cbas WHERE id = $1",
            UUID(cba_id),
        )
        if not cba:
            return {"error": "cba_not_found"}
        if not cba["document_storage_path"]:
            await conn.execute("UPDATE lr_cbas SET extraction_status = 'skipped' WHERE id = $1", cba["id"])
            return {"skipped": "no_document"}

        try:
            await conn.execute(
                "UPDATE lr_cbas SET extraction_status = 'processing' WHERE id = $1", cba["id"],
            )
            storage = get_storage()
            file_bytes = await storage.download_file(cba["document_storage_path"])
            parser = ERDocumentParser()
            parsed = parser.parse_document(file_bytes, cba["document_filename"] or "cba.pdf")
            text = getattr(parsed, "text", "") or ""

            await conn.execute(
                "UPDATE lr_cbas SET extracted_text = $2 WHERE id = $1", cba["id"], text,
            )

            result = await extract_clauses_from_cba(text)
            clauses = result.get("clauses") or []
            step_config = result.get("grievance_step_config") or []

            # Replace prior AI-extracted clauses; keep HR-entered (manual) ones.
            await conn.execute(
                "DELETE FROM lr_cba_clauses WHERE cba_id = $1 AND source = 'ai_extracted'", cba["id"],
            )
            for c in clauses:
                await conn.execute(
                    """
                    INSERT INTO lr_cba_clauses
                        (cba_id, company_id, article_number, title, clause_text, category,
                         source, ai_confidence, sort_order)
                    VALUES ($1, $2, $3, $4, $5, $6, 'ai_extracted', $7, $8)
                    """,
                    cba["id"], cba["company_id"], c.get("article_number"), c.get("title"),
                    c.get("clause_text"), c.get("category"), c.get("confidence"),
                    int(c.get("sort_order") or 0),
                )

            # Seed the grievance procedure only if none exists yet.
            if step_config and not _as_list(cba["grievance_step_config"]):
                await conn.execute(
                    "UPDATE lr_cbas SET grievance_step_config = $2::jsonb WHERE id = $1",
                    cba["id"], json.dumps(step_config),
                )

            await conn.execute(
                "UPDATE lr_cbas SET extraction_status = 'complete', updated_at = NOW() WHERE id = $1",
                cba["id"],
            )
            print(f"[CBA Extraction] {cba_id}: {len(clauses)} clauses, {len(step_config)} steps")
            return {"clauses": len(clauses), "steps": len(step_config)}
        except Exception as exc:
            await conn.execute(
                "UPDATE lr_cbas SET extraction_status = 'failed', updated_at = NOW() WHERE id = $1",
                cba["id"],
            )
            print(f"[CBA Extraction] {cba_id} failed: {exc}")
            raise
    finally:
        await conn.close()


@celery_app.task(name="labor.cba_clause_extraction", bind=True, max_retries=2)
def run_cba_clause_extraction(self, cba_id: str):
    """Parse + AI-extract a stored CBA document into the clause library."""
    try:
        return asyncio.run(_extract(cba_id))
    except Exception as e:
        print(f"[CBA Extraction] Task error for {cba_id}: {e}")
        raise self.retry(exc=e, countdown=60)
