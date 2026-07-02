"""Tell-Us — brand-configurable reward approval.

Brands choose how feedback earns points:
  - auto   — useful feedback credits immediately on submission (previous behavior)
  - manual — feedback lands with reward_status='pending'; the brand reviews and
             approves (points credit) or rejects (no credit) each submission.

`tellus_reports.reward_status` tracks the per-report decision: NULL for
anonymous submissions (nothing to credit), 'approved' for auto-credited or
brand-approved, 'pending'/'rejected' in manual mode.

Revision ID: tellus_app_03
Revises: tellus_app_02
Create Date: 2026-07-01
"""
from alembic import op


revision = "tellus_app_03"
down_revision = "tellus_app_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tellus_brands ADD COLUMN IF NOT EXISTS reward_mode TEXT NOT NULL DEFAULT 'auto'"
    )
    op.execute(
        """DO $$ BEGIN
            ALTER TABLE tellus_brands ADD CONSTRAINT ck_tellus_brands_reward_mode
                CHECK (reward_mode IN ('auto', 'manual'));
        EXCEPTION WHEN duplicate_object THEN NULL; END $$"""
    )
    op.execute(
        "ALTER TABLE tellus_reports ADD COLUMN IF NOT EXISTS reward_status TEXT"
    )
    op.execute(
        """DO $$ BEGIN
            ALTER TABLE tellus_reports ADD CONSTRAINT ck_tellus_reports_reward_status
                CHECK (reward_status IN ('pending', 'approved', 'rejected'));
        EXCEPTION WHEN duplicate_object THEN NULL; END $$"""
    )
    # Brand dashboard "awaiting review" queue.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_reports_reward_pending "
        "ON tellus_reports (brand_id, created_at DESC) WHERE reward_status = 'pending'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tellus_reports_reward_pending")
    op.execute("ALTER TABLE tellus_reports DROP COLUMN IF EXISTS reward_status")
    op.execute("ALTER TABLE tellus_brands DROP COLUMN IF EXISTS reward_mode")
