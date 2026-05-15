"""Add handbook_audit_reports for the free-tier Handbook Gap Analyzer.

Revision ID: zzzz9h0i1j2k3
Revises: zzzz8g9h0i1j2
Create Date: 2026-05-14
"""
from alembic import op


revision = "zzzz9h0i1j2k3"
down_revision = "zzzz8g9h0i1j2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS handbook_audit_reports (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email TEXT,
            user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            states TEXT[] NOT NULL,
            industry TEXT,
            pdf_storage_path TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'processing',
            gap_counts JSONB,
            gaps_jsonb JSONB,
            extracted_sections_jsonb JSONB,
            error_text TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_handbook_audit_email
            ON handbook_audit_reports (LOWER(email))
            WHERE email IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_handbook_audit_user
            ON handbook_audit_reports (user_id)
            WHERE user_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_handbook_audit_user")
    op.execute("DROP INDEX IF EXISTS idx_handbook_audit_email")
    op.execute("DROP TABLE IF EXISTS handbook_audit_reports")
