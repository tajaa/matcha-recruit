"""add investigation invite token

Revision ID: zb1c2d3e4f5g
Revises: za1b2c3d4e5f
Create Date: 2026-03-11

"""
from alembic import op

revision = 'zb1c2d3e4f5g'
down_revision = 'za1b2c3d4e5f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE ir_investigation_interviews
        ADD COLUMN IF NOT EXISTS invite_token VARCHAR(64)
    """)
    op.execute("""
        ALTER TABLE ir_investigation_interviews
        ADD COLUMN IF NOT EXISTS invite_sent_at TIMESTAMP
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_irii_invite_token
        ON ir_investigation_interviews(invite_token)
        WHERE invite_token IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_irii_invite_token")
    op.execute("ALTER TABLE ir_investigation_interviews DROP COLUMN IF EXISTS invite_sent_at")
    op.execute("ALTER TABLE ir_investigation_interviews DROP COLUMN IF EXISTS invite_token")
