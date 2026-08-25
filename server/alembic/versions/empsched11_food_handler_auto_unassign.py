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


def downgrade() -> None:
    op.execute("""
        UPDATE credential_types
           SET auto_unassign_on_expiry = false
         WHERE key = 'food_handler_card'
    """)
    op.execute("""
        ALTER TABLE credential_types
            DROP COLUMN IF EXISTS auto_unassign_on_expiry
    """)
