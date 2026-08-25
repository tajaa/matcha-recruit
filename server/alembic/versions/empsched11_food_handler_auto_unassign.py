"""Automatically remove future food-handler assignments after expiry.

The earlier schedule-blocking flag prevents new assignments.  Food-handler
cards additionally need the operational consequence described in the ticket:
once expired, future assignments are removed by the eligibility worker.
Keeping this as a credential-type policy avoids silently changing the
manager-mediated behaviour of unrelated credential requirements.

Revision ID: empsched11
Revises: empsched10
"""
from alembic import op


revision = "empsched11"
down_revision = "empsched10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE credential_types
            ADD COLUMN IF NOT EXISTS auto_unassign_on_expiry BOOLEAN NOT NULL DEFAULT false
    """)
    op.execute("""
        UPDATE credential_types
           SET auto_unassign_on_expiry = true
         WHERE key = 'food_handler_card'
    """)
    # This projection is managed by its source case.  Unlike the generic EMS
    # source index, its identity remains unique after an event is completed so
    # a replay can revive the same event instead of inserting another one.
    op.execute("""
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY company_id, source_kind, source_ref
                       ORDER BY CASE status WHEN 'logged' THEN 0 ELSE 1 END,
                                created_at, id
                   ) AS row_number
              FROM ems_events
             WHERE source_kind='schedule_eligibility_case'
               AND source_ref IS NOT NULL
        )
        UPDATE ems_events e
           SET source_kind=NULL, source_ref=NULL, updated_at=NOW()
          FROM ranked r
         WHERE e.id=r.id AND r.row_number > 1
    """)
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uniq_ems_schedule_eligibility_source
        ON ems_events(company_id, source_kind, source_ref)
        WHERE source_kind='schedule_eligibility_case' AND source_ref IS NOT NULL""")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uniq_ems_schedule_eligibility_source")
    op.execute("""
        UPDATE credential_types
           SET auto_unassign_on_expiry = false
         WHERE key = 'food_handler_card'
    """)
    op.execute("""
        ALTER TABLE credential_types
            DROP COLUMN IF EXISTS auto_unassign_on_expiry
    """)
