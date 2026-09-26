"""Index device-session creation time for bounded retention.

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


def downgrade() -> None:
    op.execute("DROP INDEX idx_auth_device_sessions_created_at")
