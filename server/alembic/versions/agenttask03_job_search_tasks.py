"""Espresso Tasks: every existing job search gets its row in Tasks.

Revision ID: agenttask03
Revises: agenttask02

Job searches move into the Tasks section. Each search is a pointer row in
`mw_agent_tasks` (`engine = 'job_search'`, `job_search_id`, request id = the
search's id), written with the search from now on
(`agent_tasks/job_tasks.insert_pointer`). This adds the rows for searches made
before. Data only; the columns came with agenttask01.

The pointer's own `status` is `done` (what Tasks shows is read from the
search). `completed_at` is the search's, so a search that had already finished
isn't announced again when a later redraft ends. A deleted search's pointer is
deleted too. Idempotent: a search that has its row already is skipped.

The downgrade removes the pointer rows.
"""
from alembic import op

revision = "agenttask03"
down_revision = "agenttask02"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        INSERT INTO mw_agent_tasks
            (request_id, user_id, company_id, source, playbook, engine, title, directive, status,
             job_search_id, created_at, updated_at, completed_at, seen_at, deleted_at)
        SELECT s.id, s.user_id, s.company_id, 'espresso', 'job_search', 'job_search',
               LEFT(COALESCE(s.title, ''), 120), COALESCE(s.ask, ''), 'done',
               s.id, s.created_at, s.updated_at, s.completed_at, s.completed_at, s.deleted_at
        FROM mw_job_searches s
        WHERE NOT EXISTS (SELECT 1 FROM mw_agent_tasks t WHERE t.job_search_id = s.id)
        ON CONFLICT DO NOTHING
    """)


def downgrade():
    op.execute("DELETE FROM mw_agent_tasks WHERE engine = 'job_search'")
