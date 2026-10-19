"""Espresso Job search: a job read from Workable's public API.

Revision ID: mwjobs03
Revises: recap01

Job search now reads Workable postings (apply.workable.com) through
Workable's public jobs API, as it reads Greenhouse, Lever and Ashby, and
records `source = 'workable'` on the job. The source CHECK from `mwjobs01`
allows only the first three ATSs, so it is widened here. Before this, the web
run's Workable links were dropped at the read step.

One ALTER on a small table, so the upgrade is instant. The downgrade records
Workable jobs as `web` (read from a page) and restores the narrower CHECK.
"""
from alembic import op

revision = "mwjobs03"
down_revision = "recap01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE mw_job_leads
            DROP CONSTRAINT IF EXISTS mw_job_leads_source_check,
            ADD CONSTRAINT mw_job_leads_source_check
                CHECK (source IN ('google_jobs', 'greenhouse', 'lever', 'ashby', 'workable', 'web'))
    """)


def downgrade():
    op.execute("UPDATE mw_job_leads SET source = 'web' WHERE source = 'workable'")
    op.execute("""
        ALTER TABLE mw_job_leads
            DROP CONSTRAINT IF EXISTS mw_job_leads_source_check,
            ADD CONSTRAINT mw_job_leads_source_check
                CHECK (source IN ('google_jobs', 'greenhouse', 'lever', 'ashby', 'web'))
    """)
