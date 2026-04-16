"""Creator approval gate for channel job postings.

Mods who aren't the channel owner create postings in pending_approval
status. The owner reviews and approves (→ draft, ready for checkout)
or rejects.

Revision ID: zzu1v2w3x4y5
Revises: zzt0u1v2w3x4
Create Date: 2026-04-15
"""
from alembic import op

revision = "zzu1v2w3x4y5"
down_revision = "zzt0u1v2w3x4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE channel_job_postings
          ADD COLUMN IF NOT EXISTS approved_by uuid REFERENCES users(id),
          ADD COLUMN IF NOT EXISTS approved_at timestamptz,
          ADD COLUMN IF NOT EXISTS rejected_reason text
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_job_postings_pending
        ON channel_job_postings(channel_id, created_at DESC)
        WHERE status = 'pending_approval'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_channel_job_postings_pending")
    op.execute("""
        ALTER TABLE channel_job_postings
          DROP COLUMN IF EXISTS rejected_reason,
          DROP COLUMN IF EXISTS approved_at,
          DROP COLUMN IF EXISTS approved_by
    """)
