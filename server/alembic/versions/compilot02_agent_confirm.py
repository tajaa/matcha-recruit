"""Compliance Pilot — agentic loop: confirm-first action lifecycle.

The single-shot Pilot only ever wrote actions that were already RUNNING (the admin
clicked a ProposalCard, the route inserted status='running' and launched the task).
The agentic loop stages actions from inside a chat turn instead, so an action now
has a life BEFORE it runs:

    proposed -> running -> done | failed
    proposed -> cancelled           (admin declined, or the model staged a replacement)
    proposed -> superseded          (single-slot: a newer stage displaces the older)

`confirmed_at` / `confirmed_by` record who turned a proposal into a run — the
two-turn confirm gate is the whole safety envelope for writes the model staged, so
it needs an audit stamp distinct from `actor_id` (who the chat turn belonged to).

`uq_compilot_action_running` (partial UNIQUE on session_id WHERE status='running')
is deliberately untouched: 'proposed' rows are outside its predicate, so a session
may hold several proposals while still running at most one.

Column widths: 'superseded' (10) is the longest new value and status is VARCHAR(12).
No type change needed.
"""
from alembic import op

# revision identifiers
revision = "compilot02"
down_revision = "irdocvia01"
branch_labels = None
depends_on = None

_CONSTRAINT = "compliance_pilot_actions_status_check"


def upgrade():
    op.execute(
        f"ALTER TABLE compliance_pilot_actions DROP CONSTRAINT IF EXISTS {_CONSTRAINT}"
    )
    op.execute(
        f"ALTER TABLE compliance_pilot_actions ADD CONSTRAINT {_CONSTRAINT} "
        "CHECK (status IN ('proposed','running','done','failed','superseded','cancelled'))"
    )
    op.execute(
        "ALTER TABLE compliance_pilot_actions "
        "ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE compliance_pilot_actions "
        "ADD COLUMN IF NOT EXISTS confirmed_by UUID REFERENCES users(id) ON DELETE SET NULL"
    )


def downgrade():
    # The narrow CHECK cannot express the new statuses, so remap before re-adding it.
    # 'failed' is the honest landing spot: a proposed/cancelled/superseded action
    # never ran, and on the old schema "never produced a result" reads as failed.
    op.execute(
        "UPDATE compliance_pilot_actions SET status='failed', finished_at=COALESCE(finished_at, NOW()) "
        "WHERE status IN ('proposed','superseded','cancelled')"
    )
    op.execute(
        f"ALTER TABLE compliance_pilot_actions DROP CONSTRAINT IF EXISTS {_CONSTRAINT}"
    )
    op.execute(
        f"ALTER TABLE compliance_pilot_actions ADD CONSTRAINT {_CONSTRAINT} "
        "CHECK (status IN ('running','done','failed'))"
    )
    op.execute("ALTER TABLE compliance_pilot_actions DROP COLUMN IF EXISTS confirmed_by")
    op.execute("ALTER TABLE compliance_pilot_actions DROP COLUMN IF EXISTS confirmed_at")
