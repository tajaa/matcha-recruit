"""add discipline compliance-gate + AI-draft fields

Adds the columns the compliance gate and the AI letter drafter need on
`progressive_discipline`:

- `occurrence_dates`     — the date(s) of the conduct being disciplined. The
                           gate needs these to test overlap against protected
                           leave; `issued_date` is when HR wrote the letter, not
                           when the conduct happened. DATE[] (not a range)
                           because attendance infractions are discrete absence
                           days; a contiguous range is just the expanded array.
- `compliance_check`     — the full verdict (blocks + advisories + statute row)
                           computed at issue time, frozen on the record. The
                           immutable trail lives in `discipline_audit_log`; this
                           column is the queryable convenience copy.
- `advisory_ack_reason`  — why HR proceeded despite advisories. Distinct from
                           `override_reason`, which means "overrode the ladder
                           level" — a different decision.
- `situation_narrative`  — the raw account HR typed that seeded the AI draft.
                           Audit value: what HR said vs. what the letter says.

Existing rows get `occurrence_dates = '{}'`; readers must tolerate the empty
array (the gate treats "no occurrence dates" as nothing to test, not as clear).

Revision ID: discipcomp01
Revises: brokerpilot02
"""
from alembic import op

revision = "discipcomp01"
down_revision = "brokerpilot02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE progressive_discipline
            ADD COLUMN IF NOT EXISTS occurrence_dates DATE[] NOT NULL DEFAULT '{}',
            ADD COLUMN IF NOT EXISTS compliance_check JSONB,
            ADD COLUMN IF NOT EXISTS advisory_ack_reason TEXT,
            ADD COLUMN IF NOT EXISTS situation_narrative TEXT
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE progressive_discipline
            DROP COLUMN IF EXISTS occurrence_dates,
            DROP COLUMN IF EXISTS compliance_check,
            DROP COLUMN IF EXISTS advisory_ack_reason,
            DROP COLUMN IF EXISTS situation_narrative
        """
    )
