"""Type-level schedule-blocking authority; enable the eligibility worker.

The tenant-authored path (credential_requirement_templates.schedule_blocking,
gated on an approved review + a legal-basis citation) already existed but
requires per-tenant admin setup nothing ships by default — a food handler
card expiring blocks nothing until an admin hand-toggles a template. This
adds a system-level default so a curated credential type (food_handler_card)
blocks scheduling out of the box, independent of template configuration.

Revision ID: empsched10
Revises: empsched09
"""
from alembic import op

revision = "empsched10"
down_revision = "empsched09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE credential_types
            ADD COLUMN IF NOT EXISTS schedule_blocking BOOLEAN NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS warning_days INTEGER NOT NULL DEFAULT 14
    """)
    op.execute("UPDATE credential_types SET schedule_blocking = true WHERE key = 'food_handler_card'")
    op.execute("UPDATE scheduler_settings SET enabled = true WHERE task_key = 'schedule_eligibility'")


def downgrade() -> None:
    op.execute("UPDATE scheduler_settings SET enabled = false WHERE task_key = 'schedule_eligibility'")
    op.execute("""
        ALTER TABLE credential_types
            DROP COLUMN IF EXISTS warning_days,
            DROP COLUMN IF EXISTS schedule_blocking
    """)
