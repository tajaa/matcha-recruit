"""device_tokens — APNs (and future push) device registration

Stores per-user push device tokens for the iOS Werk client. Additive; no
existing table touched.

NOTE: two heads exist on this DB (matcha = compljuris01, cappe = zzzzcappe20).
This revision extends the matcha line; the cappe head is unaffected.

Revision ID: devicetok01
Revises: compljuris01
Create Date: 2026-06-19
"""
from alembic import op

revision = "devicetok01"
down_revision = "compljuris01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS device_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token TEXT NOT NULL UNIQUE,
            platform TEXT NOT NULL DEFAULT 'ios',
            bundle_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_device_tokens_user ON device_tokens(user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS device_tokens")
