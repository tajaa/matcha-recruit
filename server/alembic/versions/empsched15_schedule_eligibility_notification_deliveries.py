"""Deduplicate schedule-eligibility notifications by recipient.

Revision ID: empsched15
Revises: empsched14
"""
from alembic import op


revision = "empsched15"
down_revision = "empsched14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS schedule_eligibility_notification_deliveries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            case_id UUID REFERENCES schedule_eligibility_cases(id) ON DELETE SET NULL,
            requirement_id UUID NOT NULL,
            expires_at DATE NOT NULL,
            notification_kind VARCHAR(40) NOT NULL,
            recipient_scope VARCHAR(100) NOT NULL,
            recipient_email VARCHAR(320) NOT NULL,
            sent_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (
                company_id, requirement_id, expires_at, notification_kind,
                recipient_scope, recipient_email
            )
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_schedule_eligibility_notification_deliveries_case
            ON schedule_eligibility_notification_deliveries(case_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS schedule_eligibility_notification_deliveries")
