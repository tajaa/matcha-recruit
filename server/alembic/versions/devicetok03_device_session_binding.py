"""Bind Matcha Schedule push tokens to the device session that registered them.

A push token registered under a mobile access token records that token's
device session. Mobile logout deletes the row, a failed mobile refresh deletes
the row, the send path skips rows whose session is revoked, and pruning an
expired session cascades. Legacy Werk rows keep NULL and are unaffected.

Revision ID: devicetok03
Revises: devicetok02
"""

from alembic import op


revision = "devicetok03"
down_revision = "devicetok02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE device_tokens
        ADD COLUMN device_session_id UUID
            REFERENCES auth_device_sessions(id) ON DELETE CASCADE
    """)
    op.execute("""
        CREATE INDEX idx_device_tokens_device_session
        ON device_tokens(device_session_id) WHERE device_session_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX idx_device_tokens_device_session")
    op.execute("ALTER TABLE device_tokens DROP COLUMN device_session_id")
