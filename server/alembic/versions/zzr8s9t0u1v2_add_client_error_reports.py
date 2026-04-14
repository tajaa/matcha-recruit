"""Add client_error_reports table for native client-side error tracking.

Captures JavaScript errors, unhandled promise rejections, failed API responses,
and React render errors reported from the browser. Used in place of Sentry or
other paid services. POST /api/client-errors inserts rows; admin UI at
/admin/client-errors browses them.

Revision ID: zzr8s9t0u1v2
Revises: zzq7r8s9t0u1
Create Date: 2026-04-14
"""
from alembic import op

revision = "zzr8s9t0u1v2"
down_revision = "zzq7r8s9t0u1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS client_error_reports (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            user_email TEXT,
            kind TEXT NOT NULL CHECK (kind IN ('js_error', 'promise_rejection', 'api_error', 'react_error')),
            message TEXT NOT NULL,
            stack TEXT,
            url TEXT,
            user_agent TEXT,
            api_endpoint TEXT,
            api_status_code INT,
            context JSONB,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_client_error_reports_occurred "
        "ON client_error_reports(occurred_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_client_error_reports_user "
        "ON client_error_reports(user_id, occurred_at DESC) "
        "WHERE user_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_client_error_reports_kind "
        "ON client_error_reports(kind, occurred_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_client_error_reports_kind")
    op.execute("DROP INDEX IF EXISTS idx_client_error_reports_user")
    op.execute("DROP INDEX IF EXISTS idx_client_error_reports_occurred")
    op.execute("DROP TABLE IF EXISTS client_error_reports")
