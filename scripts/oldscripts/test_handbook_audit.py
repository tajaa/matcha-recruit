"""Drive handbook audit worker against a local PDF.

Bypasses HTTP/auth/celery — uploads PDF to S3, inserts handbook_audit_reports
row, calls _analyze_async directly, dumps the resulting payload.

Usage:
    cd server && python ../scripts/test_handbook_audit.py /path/to/handbook.pdf CA NY TX
"""

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

# Load .env
from dotenv import load_dotenv
load_dotenv(ROOT / "server" / ".env")


async def main(pdf_path: str, states: list[str], industry: str | None = None):
    from app.config import load_settings
    load_settings()
    from app.database import init_pool, get_connection
    from app.core.services.storage import get_storage
    from app.workers.tasks.handbook_audit import _analyze_async

    db_url = os.environ["DATABASE_URL"]
    await init_pool(db_url)
    pdf_bytes = Path(pdf_path).read_bytes()
    print(f"PDF: {pdf_path} ({len(pdf_bytes)} bytes)")

    storage = get_storage()
    s3_uri = await storage.upload_private_file(
        file_bytes=pdf_bytes,
        filename=Path(pdf_path).name,
        prefix="handbook-audits/test",
        content_type="application/pdf",
    )
    print(f"Uploaded: {s3_uri}")

    report_id = str(uuid.uuid4())
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO handbook_audit_reports
                (id, email, states, industry, pdf_storage_path, status)
            VALUES ($1, $2, $3, $4, $5, 'processing')
            """,
            report_id,
            "test-driver@local",
            states,
            industry,
            s3_uri,
        )
    print(f"Report seeded: {report_id}")

    print(f"Running analysis (states={states}, industry={industry})...")
    await _analyze_async(report_id)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT status, gap_counts, error_text, completed_at, "
            "jsonb_array_length(COALESCE(gaps_jsonb, '[]'::jsonb)) AS n_gaps, "
            "jsonb_array_length(COALESCE(extracted_sections_jsonb, '[]'::jsonb)) AS n_sections "
            "FROM handbook_audit_reports WHERE id = $1",
            report_id,
        )

    print("\n=== RESULT ===")
    print(f"Status: {row['status']}")
    print(f"Sections extracted: {row['n_sections']}")
    print(f"Total gaps: {row['n_gaps']}")
    if row["error_text"]:
        print(f"ERROR: {row['error_text']}")
    if row["gap_counts"]:
        gc = row["gap_counts"] if isinstance(row["gap_counts"], dict) else json.loads(row["gap_counts"])
        print(json.dumps(gc, indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test_handbook_audit.py <pdf_path> <STATE1> [STATE2 ...]")
        sys.exit(1)
    pdf = sys.argv[1]
    states = [s.upper() for s in sys.argv[2:]]
    asyncio.run(main(pdf, states))
