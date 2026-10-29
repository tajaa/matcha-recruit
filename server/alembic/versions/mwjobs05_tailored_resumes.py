"""Espresso Job search: a résumé tailored to one job, to read before applying.

Revision ID: mwjobs05
Revises: cappesocial04

"Tailor my résumé" on a job rewrites the person's saved résumé for that
posting (`job_search/tailor.py`): one model run in the worker, checked against
the résumé before it is kept. The job holds the result and where its run is:

  resume_status        none / queued / drafting / done / failed
  resume_tailored      the checked result (empty until done)
  resume_token         the run allowed to write it; a newer request replaces it
  resume_requested_at  when it was asked for: a queued or drafting one older
                       than `tailor.STALE_MINUTES` reads as failed

Columns only, with constant defaults, so the upgrade is instant on PG 11+.
The CHECK is added NOT VALID and validated separately, so the ALTER takes no
long lock. The downgrade drops them.
"""
from alembic import op

revision = "mwjobs05"
down_revision = "cappesocial04"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE mw_job_leads
            ADD COLUMN IF NOT EXISTS resume_status TEXT NOT NULL DEFAULT 'none',
            ADD COLUMN IF NOT EXISTS resume_tailored JSONB NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN IF NOT EXISTS resume_token UUID,
            ADD COLUMN IF NOT EXISTS resume_requested_at TIMESTAMPTZ
    """)
    op.execute("ALTER TABLE mw_job_leads DROP CONSTRAINT IF EXISTS mw_job_leads_resume_status_check")
    op.execute("""
        ALTER TABLE mw_job_leads ADD CONSTRAINT mw_job_leads_resume_status_check
            CHECK (resume_status IN ('none', 'queued', 'drafting', 'done', 'failed')) NOT VALID
    """)
    op.execute("ALTER TABLE mw_job_leads VALIDATE CONSTRAINT mw_job_leads_resume_status_check")


def downgrade():
    op.execute("ALTER TABLE mw_job_leads DROP CONSTRAINT IF EXISTS mw_job_leads_resume_status_check")
    op.execute("""
        ALTER TABLE mw_job_leads
            DROP COLUMN IF EXISTS resume_requested_at,
            DROP COLUMN IF EXISTS resume_token,
            DROP COLUMN IF EXISTS resume_tailored,
            DROP COLUMN IF EXISTS resume_status
    """)
