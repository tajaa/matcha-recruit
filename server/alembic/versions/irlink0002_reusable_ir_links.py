"""reusable + revocable per-location magic links (status + rotation history)

Revision ID: irlink0002
Revises: dealflowtmpl01
Create Date: 2026-06-01

Makes per-location intake links (ir_report_links) reusable instead of
single-use:
  - is_active / revoked_at  -> soft revoke (link stays for history + revive)
  - use_count               -> incremented per submit (display + max_uses cap)
  - max_uses / expires_at   -> optional limits (NULL = unlimited / never)
  - used_at                 -> REPURPOSED as "last used at" (no longer burns
                               the link; kept for display only)

Plus ir_report_link_history: every rotate/revoke retires the old token here so
a compromised token can be correlated to the reports filed through it.
"""

from alembic import op


revision = "irlink0002"
down_revision = "dealflowtmpl01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE ir_report_links
            ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true,
            ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS use_count INT NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS max_uses INT,
            ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS ir_report_link_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            link_id UUID NOT NULL REFERENCES ir_report_links(id) ON DELETE CASCADE,
            company_id UUID NOT NULL,
            location_id UUID NOT NULL,
            token VARCHAR(32) NOT NULL,
            went_live_at TIMESTAMPTZ,
            retired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            retired_reason TEXT NOT NULL CHECK (retired_reason IN ('rotated', 'revoked')),
            use_count INT NOT NULL DEFAULT 0,
            created_by UUID,
            retired_by UUID
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ir_report_link_history_link "
        "ON ir_report_link_history(link_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ir_report_link_history_company "
        "ON ir_report_link_history(company_id)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS ir_report_link_history")
    op.execute("""
        ALTER TABLE ir_report_links
            DROP COLUMN IF EXISTS is_active,
            DROP COLUMN IF EXISTS revoked_at,
            DROP COLUMN IF EXISTS use_count,
            DROP COLUMN IF EXISTS max_uses,
            DROP COLUMN IF EXISTS expires_at
    """)
