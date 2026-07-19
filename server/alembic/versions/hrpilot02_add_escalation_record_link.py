"""add linked-record columns to mw_escalated_queries

An HR Pilot hard-stop hand-off can now file a real record (IR incident /
ER case) from the supervisor's own narrative. The reviewer opening the
escalation must see "already filed as <record>" or they will double-file
the intake — so the escalation row links the created record. Nullable,
no FK: the link is polymorphic across ir_incidents / er_cases and the
escalation must outlive record deletion.

Revision ID: hrpilot02
Revises: hrpilot01
Create Date: 2026-07-19
"""

from alembic import op


revision = "hrpilot02"
down_revision = "hrpilot01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE mw_escalated_queries
        ADD COLUMN IF NOT EXISTS linked_record_type VARCHAR(30),
        ADD COLUMN IF NOT EXISTS linked_record_id UUID
        """
    )


def downgrade():
    op.execute(
        """
        ALTER TABLE mw_escalated_queries
        DROP COLUMN IF EXISTS linked_record_type,
        DROP COLUMN IF EXISTS linked_record_id
        """
    )
