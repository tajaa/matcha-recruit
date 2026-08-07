"""tellus_app_10 — brand claim approval queue + publish-now audit trail.

Revision ID: tellus_app_10
Revises: tellus_app_09
"""
from alembic import op

revision = "tellus_app_10"
down_revision = "tellus_app_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_brand_claims (
               id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
               brand_id uuid NOT NULL REFERENCES tellus_brands(id) ON DELETE CASCADE,
               account_id uuid NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
               status text NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','approved','rejected','cancelled')),
               claimant_ip text,
               note text,
               created_at timestamptz NOT NULL DEFAULT NOW(),
               decided_at timestamptz,
               decided_by uuid REFERENCES tellus_accounts(id),
               decision_note text
           )"""
    )
    # One pending claim per brand and per account — DB-enforced race safety.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_brand_claims_pending_brand "
        "ON tellus_brand_claims (brand_id) WHERE status = 'pending'"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_brand_claims_pending_account "
        "ON tellus_brand_claims (account_id) WHERE status = 'pending'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_brand_claims_status_created "
        "ON tellus_brand_claims (status, created_at)"
    )
    op.execute(
        "ALTER TABLE tellus_reports ADD COLUMN IF NOT EXISTS published_early_at timestamptz"
    )
    op.execute(
        "ALTER TABLE tellus_reports ADD COLUMN IF NOT EXISTS published_early_by uuid "
        "REFERENCES tellus_accounts(id)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE tellus_reports DROP COLUMN IF EXISTS published_early_by")
    op.execute("ALTER TABLE tellus_reports DROP COLUMN IF EXISTS published_early_at")
    op.execute("DROP TABLE IF EXISTS tellus_brand_claims")
