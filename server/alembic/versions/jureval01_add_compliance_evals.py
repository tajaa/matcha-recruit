"""add compliance eval runs/results/findings

Measurement layer for the jurisdiction data catalog. Nothing here writes to
``jurisdiction_requirements`` — the eval suites read the catalog and record
verdicts in their own tables so the measurement can never become part of the
thing it measures.

Three tables:
  * compliance_eval_runs      — one row per triggered run
  * compliance_eval_results   — scorecard cells (jurisdiction × industry × suite)
  * compliance_eval_findings  — row-level defects, adjudicable by an admin

The ``judge_*`` and ``verification_outcome_id`` columns on findings are unused
in Phase 1/2; they are the landing spot for the Phase 3 LLM veracity judge,
which will also revive the (currently empty) ``verification_outcomes``
calibration table.

Revision ID: jureval01
Revises: hbshare01
Create Date: 2026-07-09

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'jureval01'
down_revision: Union[str, Sequence[str], None] = 'hbshare01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS compliance_eval_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            suites TEXT[] NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'running',
            trigger_source VARCHAR(20) NOT NULL DEFAULT 'manual',
            triggered_by UUID REFERENCES users(id) ON DELETE SET NULL,
            params JSONB,
            totals JSONB,
            error_text TEXT,
            started_at TIMESTAMP NOT NULL DEFAULT NOW(),
            finished_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_ceval_runs_started "
        "ON compliance_eval_runs(started_at DESC)"
    )

    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS compliance_eval_results (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL REFERENCES compliance_eval_runs(id) ON DELETE CASCADE,
            jurisdiction_id UUID NOT NULL REFERENCES jurisdictions(id) ON DELETE CASCADE,
            industry VARCHAR(50),
            suite VARCHAR(30) NOT NULL,
            score NUMERIC(5,2),
            detail JSONB,
            onboarding_ready BOOLEAN,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    # industry is NULL for industry-agnostic suites (authority, tagging); a plain
    # UNIQUE would let duplicate NULL-industry rows through, so key the uniqueness
    # on a sentinel-coalesced expression instead.
    conn.exec_driver_sql("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ceval_results_cell
        ON compliance_eval_results (run_id, jurisdiction_id, COALESCE(industry, ''), suite)
    """)
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_ceval_results_lookup "
        "ON compliance_eval_results(jurisdiction_id, industry, suite, created_at DESC)"
    )

    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS compliance_eval_findings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL REFERENCES compliance_eval_runs(id) ON DELETE CASCADE,
            suite VARCHAR(30) NOT NULL,
            finding_type VARCHAR(50) NOT NULL,
            severity VARCHAR(10) NOT NULL DEFAULT 'warn',
            jurisdiction_id UUID REFERENCES jurisdictions(id) ON DELETE CASCADE,
            requirement_id UUID REFERENCES jurisdiction_requirements(id) ON DELETE SET NULL,
            requirement_key TEXT,
            category VARCHAR(50),
            industry VARCHAR(50),
            expected JSONB,
            observed JSONB,
            judge_verdict VARCHAR(20),
            judge_confidence NUMERIC(3,2),
            judge_sources JSONB,
            verification_outcome_id INTEGER REFERENCES verification_outcomes(id) ON DELETE SET NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'open',
            resolved_by UUID REFERENCES users(id) ON DELETE SET NULL,
            resolved_at TIMESTAMP,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_ceval_findings_run ON compliance_eval_findings(run_id)"
    )
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_ceval_findings_jur_status "
        "ON compliance_eval_findings(jurisdiction_id, status)"
    )
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_ceval_findings_type ON compliance_eval_findings(finding_type)"
    )

    # Scheduler row — seeded DISABLED. The worker only dispatches when an admin
    # flips this on, matching every other scheduled task in this repo.
    conn.exec_driver_sql("""
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES (
            'compliance_evals',
            'Compliance Data Evals',
            'Weekly jurisdiction-data eval run (completeness, authority, tagging, golden).',
            false,
            1
        )
        ON CONFLICT (task_key) DO NOTHING
    """)


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql("DELETE FROM scheduler_settings WHERE task_key = 'compliance_evals'")
    conn.exec_driver_sql("DROP TABLE IF EXISTS compliance_eval_findings")
    conn.exec_driver_sql("DROP TABLE IF EXISTS compliance_eval_results")
    conn.exec_driver_sql("DROP TABLE IF EXISTS compliance_eval_runs")
