"""tellus_app_20 — Tell-Us APNs device-token registration.

Tell-Us has its own identity model (`tellus_accounts`), so it cannot reuse
matcha's `device_tokens` table (which references `users(id)`). This additive
table mirrors that shape but keys on `tellus_accounts`, letting the Tell-Us
push sender fan a bell notification out to a consumer/brand's registered iOS
devices.

Revision ID: tellus_app_20
Revises: tellus_app_19
"""
from alembic import op


revision = "tellus_app_20"
down_revision = "tellus_app_19"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_device_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
            token TEXT NOT NULL UNIQUE,
            platform TEXT NOT NULL DEFAULT 'ios',
            bundle_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tellus_device_tokens_account "
        "ON tellus_device_tokens (account_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tellus_device_tokens")
