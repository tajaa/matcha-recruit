"""Add resource_pins for free-tier favorite resources.

Revision ID: zzzz7f8g9h0i1
Revises: zzzz6e7f8g9h0
Create Date: 2026-05-09
"""
from alembic import op


revision = "zzzz7f8g9h0i1"
down_revision = "zzzz6e7f8g9h0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS resource_pins (
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            resource_kind VARCHAR(32) NOT NULL
                CHECK (resource_kind IN ('template','job_description','glossary','state_guide','calculator')),
            resource_id VARCHAR(128) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, resource_kind, resource_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_resource_pins_user
            ON resource_pins(user_id, created_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS resource_pins")
