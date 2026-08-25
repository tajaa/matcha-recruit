"""Type-level schedule-blocking authority; enable the eligibility worker.

The tenant-authored path (credential_requirement_templates.schedule_blocking,
gated on an approved review + a legal-basis citation) already existed but
requires per-tenant admin setup nothing ships by default — a food handler
card expiring blocks nothing until an admin hand-toggles a template. This
adds a system-level default so a curated credential type (food_handler_card)
blocks scheduling out of the box, independent of template configuration.

A tenant that doesn't want this can opt out: create (or edit) any of their
own approved credential_requirement_templates for food_handler_card with
schedule_blocking=false via the existing template routes — its presence
suppresses the curated default company-wide (see schedule_eligibility.py's
_BLOCKING_AUTHORITY_SQL). No legal-basis citation is required to turn a
block off, only to turn one on.

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
    # Upsert rather than a bare UPDATE — empsched07 seeds this row, but if
    # it's ever missing a plain UPDATE would silently affect 0 rows and the
    # worker would stay disabled with no error.
    op.execute("""
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES ('schedule_eligibility', 'Schedule eligibility', 'Opens manager decisions for expired schedule-blocking credentials and work permits.', true, 200)
        ON CONFLICT (task_key) DO UPDATE SET enabled = true
    """)


def downgrade() -> None:
    op.execute("UPDATE scheduler_settings SET enabled = false WHERE task_key = 'schedule_eligibility'")
    op.execute("""
        ALTER TABLE credential_types
            DROP COLUMN IF EXISTS warning_days,
            DROP COLUMN IF EXISTS schedule_blocking
    """)
