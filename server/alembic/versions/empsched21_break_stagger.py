"""planned_breaks on schedule_shift_assignments (reviewed break stagger)

`compliance_guidance` is the legal record: recomputed from the jurisdiction
rule sets on every write that touches a shift's window or roster, and owned
entirely by `refresh_assignment_break_guidance`. It answers "what is owed".

Break staggering answers a different question — "when should this person
actually step off the floor, given who else is on it" — and that answer is a
manager's, kept after they review or edit it. Storing it inside
`compliance_guidance` would put a human edit in a column the next shift retime
silently overwrites, so it gets its own column.

JSONB rather than a timestamp column because one assignment can owe several
periods: a 10-hour California shift is one meal plus two rest breaks, each with
its own kind/ordinal. Shape:

    [{"kind": "meal", "ordinal": 1,
      "start_local": "2026-09-04T11:30:00-07:00",
      "duration_minutes": 30,
      "source": "manager"}]

`source` distinguishes an accepted suggestion from a hand-edited time.

Additive and nullable: NULL means nobody has reviewed a stagger for this
assignment yet, which is every existing row. No backfill — a suggestion is
computed at read time and only persisted once a manager saves it.

Revision ID: empsched21
Revises: empsched20
Create Date: 2026-09-04
"""

from alembic import op


revision = "empsched21"
down_revision = "empsched20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE schedule_shift_assignments "
        "ADD COLUMN IF NOT EXISTS planned_breaks JSONB"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE schedule_shift_assignments "
        "DROP COLUMN IF EXISTS planned_breaks"
    )
