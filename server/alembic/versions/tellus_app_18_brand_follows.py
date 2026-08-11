"""tellus_app_18 — consumer follows for signed-up businesses.

Following is intentionally brand-scoped, rather than tied to one location:
people follow a business and can then open it from Comms to choose the right
store when sending a question.

Revision ID: tellus_app_18
Revises: tellus_app_17
"""
from alembic import op


revision = "tellus_app_18"
down_revision = "tellus_app_17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_brand_follows (
               consumer_account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
               brand_id UUID NOT NULL REFERENCES tellus_brands(id) ON DELETE CASCADE,
               created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
               PRIMARY KEY (consumer_account_id, brand_id)
           )"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_brand_follows_consumer_created "
        "ON tellus_brand_follows (consumer_account_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_brand_follows_brand "
        "ON tellus_brand_follows (brand_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tellus_brand_follows")
