"""Espresso Tasks: background work Espresso does for a person, its rounds and findings.

Revision ID: agenttask01
Revises: agentin01

A task is a directive ("find me a 1bd in SF under $3,500 that allows dogs")
that runs in the background and keeps what it found. One table holds every
kind:

* `engine = 'chain'`: Espresso's own tasks (the research playbook first). They
  run as a chain of short worker tasks (`agent_runtime/chain.py`), so the
  chain's columns live here: `status`, `phase`, `dispatch_token`, `lease_until`,
  `attempts`, `progress`, `phase_cursor` and the paid-call counters.
* `engine = 'board'` / `'job_search'`: pointers to an agent card or a job
  search, which keep their own engines. Their status is read from the row they
  point at, so two state machines never drift. (Rows arrive with later PRs; the
  columns are here so those need no DDL.)

`mw_agent_task_rounds` is each piece of work on a task: the first run, a
refine, "search more", a document. A round's `units` are what it costs from the
monthly allowance (`agent_tasks/allowance.py`), counted unless it failed. A
deleted task keeps its rounds, so it still counts.

`mw_agent_task_items` are the findings. Each field carries its evidence
(`{value, display, status, evidence: {quote, url, origin}}`); a hard constraint
is only ever applied to a verified one.

Model phases are agent-runtime runs of a new kind, `agent_task`, pointing at
the task (like `job_search`).

The downgrade deletes agent-task runs, then the tables.
"""
from alembic import op

revision = "agenttask01"
down_revision = "agentin01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE mw_agent_tasks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            request_id UUID NOT NULL,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            source TEXT NOT NULL DEFAULT 'espresso' CHECK (source IN ('espresso', 'board')),
            playbook TEXT NOT NULL CHECK (playbook ~ '^[a-z][a-z_]{0,39}$'),
            engine TEXT NOT NULL DEFAULT 'chain' CHECK (engine IN ('chain', 'job_search', 'board')),
            title TEXT NOT NULL DEFAULT '',
            directive TEXT NOT NULL DEFAULT '',
            brief JSONB NOT NULL DEFAULT '{}'::jsonb,
            plan JSONB NOT NULL DEFAULT '{}'::jsonb,
            input_ids UUID[] NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'running', 'waiting', 'done', 'failed', 'cancelled')),
            phase TEXT,
            phase_cursor JSONB NOT NULL DEFAULT '{}'::jsonb,
            dispatch_token UUID,
            lease_until TIMESTAMPTZ,
            attempts INTEGER NOT NULL DEFAULT 0,
            progress JSONB NOT NULL DEFAULT '{}'::jsonb,
            needs JSONB,
            waiting_since TIMESTAMPTZ,
            provider_calls INTEGER NOT NULL DEFAULT 0,
            fetch_calls INTEGER NOT NULL DEFAULT 0,
            browser_views INTEGER NOT NULL DEFAULT 0,
            model_runs INTEGER NOT NULL DEFAULT 0,
            tokens BIGINT NOT NULL DEFAULT 0,
            current_round INTEGER NOT NULL DEFAULT 0,
            origin_channel_id UUID REFERENCES channels(id) ON DELETE SET NULL,
            origin_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            project_id UUID REFERENCES mw_projects(id) ON DELETE CASCADE,
            card_task_id UUID UNIQUE REFERENCES mw_tasks(id) ON DELETE CASCADE,
            job_search_id UUID UNIQUE REFERENCES mw_job_searches(id) ON DELETE CASCADE,
            model TEXT,
            error TEXT,
            seen_at TIMESTAMPTZ,
            deleted_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            UNIQUE (user_id, request_id),
            CONSTRAINT mw_agent_tasks_board_link CHECK (engine <> 'board' OR card_task_id IS NOT NULL),
            CONSTRAINT mw_agent_tasks_job_link CHECK (engine <> 'job_search' OR job_search_id IS NOT NULL)
        )
    """)
    op.execute("""
        CREATE INDEX idx_mw_agent_tasks_owner
            ON mw_agent_tasks(user_id, created_at DESC) WHERE deleted_at IS NULL
    """)
    # Reconcile scans live chains and waiting tasks.
    op.execute("""
        CREATE INDEX idx_mw_agent_tasks_open
            ON mw_agent_tasks(status, updated_at)
            WHERE deleted_at IS NULL AND status IN ('queued', 'running', 'waiting')
    """)

    op.execute("""
        CREATE TABLE mw_agent_task_rounds (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            task_id UUID NOT NULL REFERENCES mw_agent_tasks(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            n INTEGER NOT NULL CHECK (n >= 1),
            kind TEXT NOT NULL
                CHECK (kind IN ('initial', 'refine', 'more', 'document', 'action', 'card_run')),
            request_id UUID,
            directive TEXT NOT NULL DEFAULT '',
            scope JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'running', 'done', 'failed', 'cancelled')),
            units INTEGER NOT NULL DEFAULT 0 CHECK (units >= 0),
            items_added INTEGER NOT NULL DEFAULT 0,
            run_id UUID REFERENCES mw_project_agent_runs(id) ON DELETE SET NULL,
            summary JSONB NOT NULL DEFAULT '{}'::jsonb,
            document JSONB,
            error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            UNIQUE (task_id, n),
            UNIQUE (task_id, request_id)
        )
    """)
    # The monthly allowance sums a person's rounds since the 1st.
    op.execute("""
        CREATE INDEX idx_mw_agent_task_rounds_allowance
            ON mw_agent_task_rounds(user_id, created_at) WHERE units > 0
    """)

    op.execute("""
        CREATE TABLE mw_agent_task_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            task_id UUID NOT NULL REFERENCES mw_agent_tasks(id) ON DELETE CASCADE,
            round_n INTEGER NOT NULL DEFAULT 1,
            dedupe_key TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'other'
                CHECK (kind IN ('listing', 'product', 'place', 'slot', 'flight', 'offer', 'other')),
            title TEXT NOT NULL DEFAULT '',
            subtitle TEXT NOT NULL DEFAULT '',
            url TEXT,
            origin TEXT NOT NULL DEFAULT 'web'
                CHECK (origin IN ('provider', 'web', 'browser', 'card', 'job_search')),
            provider TEXT,
            fields JSONB NOT NULL DEFAULT '{}'::jsonb,
            images JSONB NOT NULL DEFAULT '[]'::jsonb,
            image_candidates JSONB NOT NULL DEFAULT '[]'::jsonb,
            status TEXT NOT NULL DEFAULT 'candidate'
                CHECK (status IN ('candidate', 'verified', 'unavailable', 'irrelevant')),
            violations JSONB NOT NULL DEFAULT '[]'::jsonb,
            enriched_at TIMESTAMPTZ,
            screened_at TIMESTAMPTZ,
            fit_score SMALLINT CHECK (fit_score BETWEEN 0 AND 5),
            fit_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
            rank INTEGER,
            rank_band SMALLINT,
            rank_score DOUBLE PRECISION,
            rank_explain JSONB NOT NULL DEFAULT '{}'::jsonb,
            user_state TEXT NOT NULL DEFAULT 'new'
                CHECK (user_state IN ('new', 'saved', 'dismissed', 'chosen')),
            notes TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (task_id, dedupe_key)
        )
    """)
    op.execute("CREATE INDEX idx_mw_agent_task_items_rank ON mw_agent_task_items(task_id, rank)")

    op.execute("""
        ALTER TABLE mw_project_agent_runs
            ADD COLUMN IF NOT EXISTS agent_task_id UUID
                REFERENCES mw_agent_tasks(id) ON DELETE CASCADE
    """)
    op.execute("ALTER TABLE mw_project_agent_runs DROP CONSTRAINT IF EXISTS mw_project_agent_runs_kind_check")
    op.execute("""
        ALTER TABLE mw_project_agent_runs ADD CONSTRAINT mw_project_agent_runs_kind_check
            CHECK (kind IN ('repo_question', 'task_draft', 'card_agent', 'assistant', 'job_search',
                            'agent_task'))
    """)
    op.execute("ALTER TABLE mw_project_agent_runs DROP CONSTRAINT IF EXISTS mw_project_agent_runs_project_required")
    op.execute("""
        ALTER TABLE mw_project_agent_runs ADD CONSTRAINT mw_project_agent_runs_project_required
            CHECK (kind IN ('assistant', 'job_search', 'agent_task') OR project_id IS NOT NULL)
    """)
    op.execute("""
        ALTER TABLE mw_project_agent_runs ADD CONSTRAINT mw_project_agent_runs_agent_task_link
            CHECK (kind <> 'agent_task' OR agent_task_id IS NOT NULL)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_project_agent_runs_agent_task
            ON mw_project_agent_runs(agent_task_id, created_at)
            WHERE kind = 'agent_task'
    """)


def downgrade():
    # Steps go with their runs (ON DELETE CASCADE).
    op.execute("DELETE FROM mw_project_agent_runs WHERE kind = 'agent_task'")
    op.execute("DROP INDEX IF EXISTS idx_mw_project_agent_runs_agent_task")
    op.execute("ALTER TABLE mw_project_agent_runs DROP CONSTRAINT IF EXISTS mw_project_agent_runs_agent_task_link")
    op.execute("ALTER TABLE mw_project_agent_runs DROP CONSTRAINT IF EXISTS mw_project_agent_runs_project_required")
    op.execute("""
        ALTER TABLE mw_project_agent_runs ADD CONSTRAINT mw_project_agent_runs_project_required
            CHECK (kind IN ('assistant', 'job_search') OR project_id IS NOT NULL)
    """)
    op.execute("ALTER TABLE mw_project_agent_runs DROP CONSTRAINT IF EXISTS mw_project_agent_runs_kind_check")
    op.execute("""
        ALTER TABLE mw_project_agent_runs ADD CONSTRAINT mw_project_agent_runs_kind_check
            CHECK (kind IN ('repo_question', 'task_draft', 'card_agent', 'assistant', 'job_search'))
    """)
    op.execute("ALTER TABLE mw_project_agent_runs DROP COLUMN IF EXISTS agent_task_id")
    op.execute("DROP TABLE mw_agent_task_items")
    op.execute("DROP TABLE mw_agent_task_rounds")
    op.execute("DROP TABLE mw_agent_tasks")
