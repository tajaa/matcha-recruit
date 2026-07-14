"""Scheduler row for the headless scope-registry research cycle.

Companion to scoperg01's `scope_registry_authority` row: that one gates the
authority-ingest sweep (INGEST), this one gates `scope_registry_research`
(RESEARCH → CODIFY's sole value-minter, see workers/tasks/scope_registry.py:
run_scheduled_research_cycle). Seeded DISABLED — same rule as every other
scheduled task in this repo, and doubly so here since it makes live Gemini
research calls.

NOT applied by this commit — author only. Chains off cmpreqdrop01 (this
session's other authored-only migration) to avoid growing yet another
independent head; the tree already has multiple heads and needs a merge
migration before `alembic upgrade head` can reach either.

Revision ID: scoperg02
Revises: cmpreqdrop01
Create Date: 2026-07-13
"""
from alembic import op


revision = "scoperg02"
down_revision = "cmpreqdrop01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Generic run marker. The worker has no celery-beat: the hourly container
    # restart re-fires @worker_ready, so a task that makes LIVE GEMINI CALLS
    # needs its own interval guard or it re-runs every hour forever. The ingest
    # sweep improvises one off authority_indexes.last_ingested_at; a research
    # cycle has no such natural marker (a fruitless cycle writes no rows at all
    # but still burns the API), so give every scheduled task a real one.
    conn.exec_driver_sql(
        "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS last_run_at TIMESTAMP"
    )

    conn.exec_driver_sql("""
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES (
            'scope_registry_research',
            'Scope Registry Research Cycle',
            'Drive each configured chain''s keyed fetch-queue into grounded research, '
            'then reconcile — the automated counterpart to the admin Scope Studio '
            '"Research these" button. Makes live Gemini calls.',
            false,
            1
        )
        ON CONFLICT (task_key) DO NOTHING
    """)


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        "DELETE FROM scheduler_settings WHERE task_key = 'scope_registry_research'"
    )
    conn.exec_driver_sql(
        "ALTER TABLE scheduler_settings DROP COLUMN IF EXISTS last_run_at"
    )
