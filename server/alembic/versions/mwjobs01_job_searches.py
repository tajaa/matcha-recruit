"""Espresso job search: saved searches, ranked leads, and a run kind for their phases.

Revision ID: mwjobs01
Revises: mwsales02
Depends on: assistthread01

A search is a chain of short worker tasks (one phase each). Its model phases
are ordinary agent-runtime runs of a new kind, `job_search`, which needs no
project or channel: the run row points at its search instead.

`depends_on` matters. `agentrt01` is the last migration that rewrites the two
CHECKs widened here, and it is an ancestor of `assistthread01` but not of
`mwsales02`. Without the dependency a fresh `upgrade heads` could run
`agentrt01` after this one and silently drop `job_search` again.

The downgrade deletes job-search runs, then the tables.
"""
from alembic import op

revision = "mwjobs01"
down_revision = "mwsales02"
branch_labels = None
depends_on = "assistthread01"

_LIVE = "'queued','planning','discovering','screening','enriching','approaching'"


def upgrade():
    op.execute(f"""
        CREATE TABLE mw_job_searches (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            request_id UUID NOT NULL,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            title TEXT NOT NULL DEFAULT '',
            ask TEXT NOT NULL DEFAULT '',
            criteria JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            plan JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            weights JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            weights_source TEXT NOT NULL DEFAULT 'default'
                CHECK (weights_source IN ('default', 'user')),
            use_resume BOOLEAN NOT NULL DEFAULT FALSE,
            status TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ({_LIVE}, 'done', 'failed', 'cancelled')),
            phase_cursor JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            dispatch_token UUID,
            lease_until TIMESTAMPTZ,
            attempts INTEGER NOT NULL DEFAULT 0,
            progress JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            provider_calls INTEGER NOT NULL DEFAULT 0,
            fetch_calls INTEGER NOT NULL DEFAULT 0,
            model_runs INTEGER NOT NULL DEFAULT 0,
            tokens BIGINT NOT NULL DEFAULT 0,
            redrafts INTEGER NOT NULL DEFAULT 0,
            model TEXT,
            error TEXT,
            deleted_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            UNIQUE (user_id, request_id)
        )
    """)
    op.execute(
        "CREATE INDEX idx_mw_job_searches_owner ON mw_job_searches(user_id, created_at DESC)"
    )
    # One live search per person: a search is ~15 worker tasks on a shared queue.
    op.execute(f"""
        CREATE UNIQUE INDEX uq_mw_job_searches_one_live ON mw_job_searches(user_id)
        WHERE status IN ({_LIVE})
    """)
    op.execute("""
        CREATE TABLE mw_job_leads (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            search_id UUID NOT NULL REFERENCES mw_job_searches(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            dedupe_key TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            company TEXT NOT NULL DEFAULT '',
            location TEXT NOT NULL DEFAULT '',
            state_code TEXT,
            remote BOOLEAN,
            schedule_type TEXT,
            posted_text TEXT,
            source TEXT NOT NULL
                CHECK (source IN ('google_jobs', 'greenhouse', 'lever', 'ashby', 'web')),
            provider_job_id TEXT,
            source_url TEXT,
            apply_links JSONB NOT NULL DEFAULT '[]'::jsonb,
            ats JSONB NOT NULL DEFAULT '{}'::jsonb,
            description TEXT NOT NULL DEFAULT '',
            highlights JSONB NOT NULL DEFAULT '[]'::jsonb,
            comp JSONB NOT NULL DEFAULT '{}'::jsonb,
            comp_status TEXT NOT NULL DEFAULT 'not_disclosed'
                CHECK (comp_status IN ('posted', 'mentioned', 'not_disclosed')),
            comp_annual_min NUMERIC,
            comp_annual_max NUMERIC,
            comp_currency TEXT,
            pay_law_hint TEXT,
            enriched_at TIMESTAMPTZ,
            screen_status TEXT NOT NULL DEFAULT 'pending'
                CHECK (screen_status IN ('pending', 'relevant', 'irrelevant')),
            screen_reason TEXT,
            fit_score SMALLINT CHECK (fit_score BETWEEN 0 AND 5),
            fit_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
            rank_score DOUBLE PRECISION,
            rank INTEGER,
            rank_band SMALLINT,
            rank_explain JSONB NOT NULL DEFAULT '{}'::jsonb,
            approach JSONB NOT NULL DEFAULT '{}'::jsonb,
            approach_status TEXT NOT NULL DEFAULT 'none'
                CHECK (approach_status IN ('none', 'queued', 'drafting', 'done', 'failed')),
            user_state TEXT NOT NULL DEFAULT 'new'
                CHECK (user_state IN ('new', 'saved', 'applied', 'dismissed')),
            notes TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (search_id, dedupe_key)
        )
    """)
    op.execute("CREATE INDEX idx_mw_job_leads_rank ON mw_job_leads(search_id, rank)")

    op.execute("""
        ALTER TABLE mw_project_agent_runs
            ADD COLUMN IF NOT EXISTS job_search_id UUID
                REFERENCES mw_job_searches(id) ON DELETE CASCADE
    """)
    op.execute("ALTER TABLE mw_project_agent_runs DROP CONSTRAINT IF EXISTS mw_project_agent_runs_kind_check")
    op.execute("""
        ALTER TABLE mw_project_agent_runs ADD CONSTRAINT mw_project_agent_runs_kind_check
            CHECK (kind IN ('repo_question', 'task_draft', 'card_agent', 'assistant', 'job_search'))
    """)
    op.execute("ALTER TABLE mw_project_agent_runs DROP CONSTRAINT IF EXISTS mw_project_agent_runs_project_required")
    op.execute("""
        ALTER TABLE mw_project_agent_runs ADD CONSTRAINT mw_project_agent_runs_project_required
            CHECK (kind IN ('assistant', 'job_search') OR project_id IS NOT NULL)
    """)
    op.execute("""
        ALTER TABLE mw_project_agent_runs ADD CONSTRAINT mw_project_agent_runs_job_search_link
            CHECK (kind <> 'job_search' OR job_search_id IS NOT NULL)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_project_agent_runs_job_search
            ON mw_project_agent_runs(job_search_id, created_at)
            WHERE kind = 'job_search'
    """)


def downgrade():
    # Steps go with their runs (ON DELETE CASCADE).
    op.execute("DELETE FROM mw_project_agent_runs WHERE kind = 'job_search'")
    op.execute("DROP INDEX IF EXISTS idx_mw_project_agent_runs_job_search")
    op.execute("ALTER TABLE mw_project_agent_runs DROP CONSTRAINT IF EXISTS mw_project_agent_runs_job_search_link")
    op.execute("ALTER TABLE mw_project_agent_runs DROP CONSTRAINT IF EXISTS mw_project_agent_runs_project_required")
    op.execute("""
        ALTER TABLE mw_project_agent_runs ADD CONSTRAINT mw_project_agent_runs_project_required
            CHECK (kind = 'assistant' OR project_id IS NOT NULL)
    """)
    op.execute("ALTER TABLE mw_project_agent_runs DROP CONSTRAINT IF EXISTS mw_project_agent_runs_kind_check")
    op.execute("""
        ALTER TABLE mw_project_agent_runs ADD CONSTRAINT mw_project_agent_runs_kind_check
            CHECK (kind IN ('repo_question', 'task_draft', 'card_agent', 'assistant'))
    """)
    op.execute("ALTER TABLE mw_project_agent_runs DROP COLUMN IF EXISTS job_search_id")
    op.execute("DROP TABLE mw_job_leads")
    op.execute("DROP TABLE mw_job_searches")
