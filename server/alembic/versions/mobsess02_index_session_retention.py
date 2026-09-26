"""Index device-session creation time for bounded retention; add the refresh
generation that makes mobile refresh rotation compare-and-swap (a replayed
older refresh token revokes the session instead of minting a second lineage).

Revision ID: mobsess02
Revises: mobsess01
"""

from alembic import op


revision = "mobsess02"
down_revision = "mobsess01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX idx_auth_device_sessions_created_at
        ON auth_device_sessions(created_at)
    """)
    op.execute("""
        ALTER TABLE auth_device_sessions
        ADD COLUMN refresh_generation INTEGER NOT NULL DEFAULT 0
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE auth_device_sessions DROP COLUMN refresh_generation")
    op.execute("DROP INDEX idx_auth_device_sessions_created_at")
