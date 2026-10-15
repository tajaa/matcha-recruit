"""Espresso Job search: a job's first message, put in the person's Gmail drafts.

Revision ID: mwjobs02
Revises: agenttask03

"Draft email" on a job saves its drafted outreach as a Gmail draft, to edit and
send from Espresso's Email (or Gmail). The job remembers that draft so asking
again returns it, and Email notes on the job when it is sent (`email_sent_at`)
or deleted (the columns are cleared).

Columns only, all nullable, so the upgrade is instant. The partial index finds
a job by its draft when Email sends or deletes one. The downgrade drops them.
"""
from alembic import op

revision = "mwjobs02"
down_revision = "agenttask03"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE mw_job_leads
            ADD COLUMN IF NOT EXISTS email_draft_id TEXT,
            ADD COLUMN IF NOT EXISTS email_drafted_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS email_sent_at TIMESTAMPTZ
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_job_leads_email_draft
            ON mw_job_leads (user_id, email_draft_id) WHERE email_draft_id IS NOT NULL
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_mw_job_leads_email_draft")
    op.execute("""
        ALTER TABLE mw_job_leads
            DROP COLUMN IF EXISTS email_sent_at,
            DROP COLUMN IF EXISTS email_drafted_at,
            DROP COLUMN IF EXISTS email_draft_id
    """)
