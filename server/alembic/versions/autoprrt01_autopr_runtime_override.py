"""Let a card pin the model and reasoning effort AutoPR runs it with.

AutoPR picked its runtime from one place: the hardcoded `model`/`effort` rows in
`autopr_kind_field` (apps/msandbox/harness/lib.sh). Every `investigate` run got
`gpt-5.6-sol` at `medium`, whatever the card needed. A ticket that stalls
because the model is out of its depth and a ticket that stalls with the work
done but the tests unrun both re-ran identically, and the only way out was to
approve another ten minutes and hope.

Two nullable columns are the manual half of the fix: NULL means "decide
automatically from why the last run stopped", and a set value pins the runtime
for this card until someone clears it. `autopr_runtime_source` records which of
the two produced the runtime actually used on the last run, so the card can say
"auto-raised to xhigh" rather than leaving the operator to guess.

Additive, nullable, re-runnable. Nothing reads these until the harness ships,
and an unapplied migration leaves `to_jsonb(t) ->> 'autopr_model'` NULL, which
is exactly the "decide automatically" case.

Revision ID: autoprrt01
Revises: ratelimit01
"""

from alembic import op


revision = "autoprrt01"
down_revision = "ratelimit01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE mw_tasks
        ADD COLUMN IF NOT EXISTS autopr_model VARCHAR(64)
        """
    )
    op.execute(
        """
        ALTER TABLE mw_tasks
        ADD COLUMN IF NOT EXISTS autopr_effort VARCHAR(16)
        """
    )
    op.execute(
        """
        ALTER TABLE mw_tasks
        ADD COLUMN IF NOT EXISTS autopr_runtime_source VARCHAR(16)
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE mw_tasks DROP COLUMN IF EXISTS autopr_runtime_source")
    op.execute("ALTER TABLE mw_tasks DROP COLUMN IF EXISTS autopr_effort")
    op.execute("ALTER TABLE mw_tasks DROP COLUMN IF EXISTS autopr_model")
