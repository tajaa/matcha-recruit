"""Add server_error_reports table for backend error tracking.

Mirrors client_error_reports. Captures Python exceptions, HTTP 5xx responses,
unhandled DB errors, background task failures, and Celery task failures from
the FastAPI app and Celery workers. Errors are inserted via a logging handler
attached to the root logger plus explicit report_server_error() calls.

Revision ID: zzs9t0u1v2w3
Revises: zzr8s9t0u1v2
Create Date: 2026-04-14
"""
from alembic import op

revision = "zzs9t0u1v2w3"
down_revision = "zzr8s9t0u1v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS server_error_reports (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            fingerprint TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN (
                'exception', 'http_error', 'db_error', 'background_task',
                'celery_task', 'startup', 'warning', 'unhandled'
            )),
            level TEXT NOT NULL DEFAULT 'ERROR',
            logger_name TEXT,
            message TEXT NOT NULL,
            exception_type TEXT,
            traceback TEXT,
            source TEXT NOT NULL DEFAULT 'api' CHECK (source IN ('api', 'celery', 'worker', 'startup')),
            hostname TEXT,
            request_method TEXT,
            request_path TEXT,
            request_status INT,
            user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            user_email TEXT,
            context JSONB,
            occurrences INT NOT NULL DEFAULT 1,
            first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_server_error_reports_fingerprint "
        "ON server_error_reports(fingerprint) WHERE resolved_at IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_server_error_reports_last_seen "
        "ON server_error_reports(last_seen DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_server_error_reports_kind "
        "ON server_error_reports(kind, last_seen DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_server_error_reports_source "
        "ON server_error_reports(source, last_seen DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_server_error_reports_source")
    op.execute("DROP INDEX IF EXISTS idx_server_error_reports_kind")
    op.execute("DROP INDEX IF EXISTS idx_server_error_reports_last_seen")
    op.execute("DROP INDEX IF EXISTS idx_server_error_reports_fingerprint")
    op.execute("DROP TABLE IF EXISTS server_error_reports")
