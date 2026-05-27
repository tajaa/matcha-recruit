"""add ir_report_links (per-location magic-link intake tokens)

Revision ID: irlink0001
Revises: empintern01
Create Date: 2026-05-26
"""

from alembic import op


revision = "irlink0001"
down_revision = "empintern01"
branch_labels = None
depends_on = None


def upgrade():
    # Per-location anonymous "magic link" tokens backing the public incident
    # intake form (/intake/{token}). Single-use (used_at set on first submit),
    # one current link per (company_id, location_id) — regenerate rotates the
    # token via UPSERT. Distinct from the company-wide anonymous link held in
    # companies.report_email_token.
    op.execute("""
        CREATE TABLE IF NOT EXISTS ir_report_links (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
            token VARCHAR(32) UNIQUE NOT NULL,
            used_at TIMESTAMPTZ,
            created_by UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (company_id, location_id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ir_report_links_company "
        "ON ir_report_links(company_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ir_report_links_token "
        "ON ir_report_links(token)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS ir_report_links")
