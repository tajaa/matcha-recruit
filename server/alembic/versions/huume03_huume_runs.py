"""huume: agent run/step audit tables

Huume's bounded tool-calling loop (server/app/matcha/services/huume/agent.py)
persists one huume_runs row per agent turn plus one huume_steps row per
tool call, for the run timeline shown in the thread UI and for audit.

Distinct from onboarding_runs/onboarding_steps (services/onboarding/
onboarding_orchestrator.py), which model one provisioning attempt against
one external provider for one employee and feed the provisioning-retry
UI. A Huume run is an agent turn (tool calls, staged proposals, possible
force-finish) with no employee or provider at stake yet — it may go on to
*create* onboarding_runs rows via its google_workspace/slack plan steps,
linked loosely through huume_steps.result->>'run_id'. Overloading
onboarding_runs here would pollute its existing consumers and lose the
tool-call-level audit trail.

The staged plan/action a run proposes lives in mw_threads.current_state
(huume_plan / huume_action, applied via matcha_work_document doc_svc) —
these tables are the timeline, not the pending intent.

Revision ID: huume03
Revises: huume02
Create Date: 2026-07-26
"""

from alembic import op


revision = "huume03"
down_revision = "huume02"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS huume_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            thread_id UUID NOT NULL REFERENCES mw_threads(id) ON DELETE CASCADE,
            user_id UUID,
            trigger TEXT NOT NULL DEFAULT 'user_turn',
            status TEXT NOT NULL DEFAULT 'running',
            model_calls INTEGER NOT NULL DEFAULT 0,
            token_usage JSONB,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            error TEXT,
            CONSTRAINT huume_runs_trigger_check
                CHECK (trigger IN ('user_turn', 'plan_execution')),
            CONSTRAINT huume_runs_status_check
                CHECK (status IN ('running', 'completed', 'force_finished', 'failed'))
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_huume_runs_thread ON huume_runs(thread_id, started_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_huume_runs_company ON huume_runs(company_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS huume_steps (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL REFERENCES huume_runs(id) ON DELETE CASCADE,
            seq INTEGER NOT NULL,
            tool TEXT NOT NULL,
            kind TEXT NOT NULL,
            label TEXT NOT NULL,
            args JSONB,
            result JSONB,
            status TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT huume_steps_kind_check
                CHECK (kind IN ('read', 'staged', 'write', 'finish')),
            CONSTRAINT huume_steps_status_check
                CHECK (status IN ('ok', 'rejected', 'error', 'skipped'))
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_huume_steps_run_seq ON huume_steps(run_id, seq)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS huume_steps")
    op.execute("DROP TABLE IF EXISTS huume_runs")
