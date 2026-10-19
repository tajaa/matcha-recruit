"""Espresso Job search: the job-board postings Espresso has read, kept.

Revision ID: mwjobs04
Revises: mwjobs03

Every Greenhouse, Lever, Ashby or Workable posting a job search or the
assistant's `find_jobs` reads from its board's API is kept here, live with
what was read or closed when the ATS said so (`job_search/postings.py`). A
posting read live in the last 12 hours isn't read again, one closed in the
last 14 days is skipped, and a later search starts from the live ones with a
related title in its places. Asked "any others?", the assistant used to send
the same board searches and read the same postings again, about 4 in 5 of
them closed.

`mw_job_board_searches` remembers each board search Brave was sent (its
text only), so the same search within a day asks for its next page.

Both tables hold public job postings and search text, with no user, company
or résumé on them, so they are shared and have no tenant column.

Two new tables and their indexes, empty, so the upgrade is instant. The
downgrade drops them; nothing else reads them.
"""
from alembic import op

revision = "mwjobs04"
down_revision = "mwjobs03"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_job_postings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            provider TEXT NOT NULL CHECK (provider IN ('greenhouse', 'lever', 'ashby', 'workable')),
            board_key TEXT NOT NULL,
            job_key TEXT NOT NULL,
            ref JSONB,
            url TEXT,
            live BOOLEAN NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            company TEXT NOT NULL DEFAULT '',
            location TEXT NOT NULL DEFAULT '',
            state_code TEXT,
            remote BOOLEAN,
            title_terms TEXT NOT NULL DEFAULT '',
            comp_status TEXT,
            comp_annual_min NUMERIC,
            comp_annual_max NUMERIC,
            comp_currency TEXT,
            record JSONB,
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            live_at TIMESTAMPTZ,
            closed_at TIMESTAMPTZ,
            CONSTRAINT mw_job_postings_key UNIQUE (provider, board_key, job_key)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_job_postings_live_title
            ON mw_job_postings USING gin (to_tsvector('english', title_terms)) WHERE live
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_job_postings_live_at
            ON mw_job_postings (live_at DESC) WHERE live
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_job_board_searches (
            query TEXT PRIMARY KEY,
            started_at TIMESTAMPTZ NOT NULL,
            searched_at TIMESTAMPTZ NOT NULL,
            next_offset INTEGER NOT NULL,
            exhausted BOOLEAN NOT NULL DEFAULT false
        )
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS mw_job_board_searches")
    op.execute("DROP TABLE IF EXISTS mw_job_postings")
