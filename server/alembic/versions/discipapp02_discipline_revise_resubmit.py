"""Discipline denial dispositions: add changes_requested approval state.

Closes the gap where HR denial was hard-terminal (discipapp01's own docstring:
"no un-deny path"). Denial now takes a disposition:

  - reject  -> unchanged discipapp01 behavior (approval_status/status='denied',
    terminal, no further transition_status calls will ever succeed on the row).
  - revise  -> approval_status='changes_requested', status stays 'draft'. The
    record becomes editable (new PATCH /records/{id}) and resubmittable (new
    POST /records/{id}/resubmit -> approval_status='pending' again). No new
    columns: the "why" reuses the existing denial_reason column, and the round
    trail lives in discipline_audit_log (approval_changes_requested /
    draft_revised / approval_resubmitted rows), same pattern as every other
    decision on this table.

transition_status's approval-bypass guard (discipline_engine.py) widens from
NOT IN ('pending','denied') to NOT IN ('pending','denied','changes_requested')
so a record awaiting revision is exactly as protected from the 6 existing
status-changing routes as a pending one — same choke point, no new guard code.

The partial index that backs the HR approval queue covered only
approval_status='pending'; a changes_requested record needs the same index
for its own "needs revision" queue, so it's dropped and recreated over both
values rather than adding a second index.

Revision ID: discipapp02
Revises: discipapp01
Create Date: 2026-08-04
"""

from alembic import op


revision = "discipapp02"
down_revision = "discipapp01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE progressive_discipline DROP CONSTRAINT IF EXISTS progressive_discipline_approval_status_check"
    )
    op.execute(
        """
        ALTER TABLE progressive_discipline ADD CONSTRAINT progressive_discipline_approval_status_check
          CHECK (approval_status IN ('not_required','pending','approved','denied','changes_requested'))
        """
    )

    op.execute("DROP INDEX IF EXISTS idx_progressive_discipline_approval")
    op.execute(
        """
        CREATE INDEX idx_progressive_discipline_approval
        ON progressive_discipline(company_id, approval_status)
        WHERE approval_status IN ('pending', 'changes_requested')
        """
    )


def downgrade():
    # Any row parked in changes_requested has no discipapp01-era home — fold
    # it into denied (terminal) rather than leaving a value the narrowed CHECK
    # below would then reject outright.
    op.execute(
        "UPDATE progressive_discipline SET approval_status = 'denied', status = 'denied' "
        "WHERE approval_status = 'changes_requested'"
    )

    op.execute("DROP INDEX IF EXISTS idx_progressive_discipline_approval")
    op.execute(
        "CREATE INDEX idx_progressive_discipline_approval "
        "ON progressive_discipline(company_id, approval_status) WHERE approval_status = 'pending'"
    )

    op.execute(
        "ALTER TABLE progressive_discipline DROP CONSTRAINT IF EXISTS progressive_discipline_approval_status_check"
    )
    op.execute(
        """
        ALTER TABLE progressive_discipline ADD CONSTRAINT progressive_discipline_approval_status_check
          CHECK (approval_status IN ('not_required','pending','approved','denied'))
        """
    )
