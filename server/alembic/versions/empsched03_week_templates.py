"""add week templates — a named container of shift-block definitions

Redesigns the shift-template system: a "template" used to be one standalone
shift definition (schedule_shift_templates row). Real usage is a *week* of
shifts — e.g. "Standard Week" or "Christmas Week" — composed of several named
blocks (Box Office Mon-Fri, Weekend Crew Sat-Sun, ...), each block keeping the
existing shift-definition shape. This adds a parent container,
schedule_week_templates, and points schedule_shift_templates at it via a
nullable week_template_id.

NULL week_template_id = standalone single-shift template (legacy shape, still
written directly by the scheduling-chat flow in schedule_chat.py, which is
intentionally NOT touched by this migration or its follow-up route/frontend
work). NOT NULL = a block belonging to a week template.

Revision ID: empsched03
Revises: empsched02
Create Date: 2026-08-17
"""

from alembic import op

revision = "empsched03"
down_revision = "empsched02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_week_templates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            name VARCHAR(150) NOT NULL,
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            color VARCHAR(20),
            notes TEXT,
            created_by UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedule_week_templates_company "
        "ON schedule_week_templates(company_id);"
    )

    op.execute(
        "ALTER TABLE schedule_shift_templates "
        "ADD COLUMN IF NOT EXISTS week_template_id UUID "
        "REFERENCES schedule_week_templates(id) ON DELETE CASCADE"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedule_shift_templates_week_template "
        "ON schedule_shift_templates(week_template_id);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_schedule_shift_templates_week_template")
    op.execute("ALTER TABLE schedule_shift_templates DROP COLUMN IF EXISTS week_template_id")
    op.execute("DROP INDEX IF EXISTS idx_schedule_week_templates_company")
    op.execute("DROP TABLE IF EXISTS schedule_week_templates")
