"""tellus_app_25 — brand invites (fan-initiated "get this business on Tell-Us").

Unique per (brand_id, consumer_account_id) so the invite_count shown as social
proof on a listing can't be stuffed by one account. See TELLUS_DISCOVER_PLAN.md
at the repo root for the full feature design.
"""
from alembic import op


revision = "tellus_app_25"
down_revision = "tellus_app_24"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_brand_invites (
               id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
               brand_id UUID NOT NULL REFERENCES tellus_brands(id) ON DELETE CASCADE,
               consumer_account_id UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
               created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
           )"""
    )
    op.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_brand_invites_account_brand
             ON tellus_brand_invites (brand_id, consumer_account_id)
            WHERE consumer_account_id IS NOT NULL"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_tellus_brand_invites_brand
             ON tellus_brand_invites (brand_id)"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tellus_brand_invites")
