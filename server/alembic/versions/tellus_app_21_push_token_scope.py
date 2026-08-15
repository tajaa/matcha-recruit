"""tellus_app_21 — scope tellus_device_tokens uniqueness per (account, token).

`register_token`'s old `ON CONFLICT (token) DO UPDATE SET account_id = ...`
let any account that learned another device's APNs token silently reassign
that device's push stream to itself (the token-unique constraint forced a
steal instead of a second row). Scoping the unique key to the pair means two
accounts can each hold a row for the same physical device — `send_to_accounts`
already dedupes by `SELECT DISTINCT token` so a shared device still gets one
alert, not two.

Revision ID: tellus_app_21
Revises: tellus_app_20
"""
from alembic import op


revision = "tellus_app_21"
down_revision = "tellus_app_20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tellus_device_tokens DROP CONSTRAINT IF EXISTS tellus_device_tokens_token_key"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_tellus_device_tokens_account_token "
        "ON tellus_device_tokens (account_id, token)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tellus_device_tokens_account_token")
    op.execute(
        "ALTER TABLE tellus_device_tokens ADD CONSTRAINT tellus_device_tokens_token_key UNIQUE (token)"
    )
