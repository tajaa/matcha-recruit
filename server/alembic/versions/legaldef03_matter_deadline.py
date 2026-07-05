"""Legal Pilot — matter response deadline

Revision ID: legaldef03
Revises: brokerpilot01
Create Date: 2026-07-05

EEOC position statements, subpoena returns, and audit responses carry hard
due dates; missing one is catastrophic and entirely preventable. Adds
`response_deadline` (+ a short free-text note) to `legal_matters`; the
`legal_deadline_reminders` worker (scheduler-gated, default off) nudges the
matter owner at 14/7/3/1 days out, deduped via `legal_matter_audit_log`
`deadline_reminder` rows — no new table.
"""

from alembic import op


revision = "legaldef03"
down_revision = "brokerpilot01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE legal_matters ADD COLUMN IF NOT EXISTS response_deadline DATE"
    )
    op.execute(
        "ALTER TABLE legal_matters ADD COLUMN IF NOT EXISTS deadline_note VARCHAR(300)"
    )


def downgrade():
    op.execute("ALTER TABLE legal_matters DROP COLUMN IF EXISTS deadline_note")
    op.execute("ALTER TABLE legal_matters DROP COLUMN IF EXISTS response_deadline")
