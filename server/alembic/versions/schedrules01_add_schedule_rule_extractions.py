"""add schedule_rule_extraction_runs, schedule_rule_extractions

Revision ID: schedrules01
Revises: brokerpilot03
Create Date: 2026-07-23
"""

from alembic import op


revision = "schedrules01"
down_revision = "brokerpilot03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── schedule_rule_extraction_runs: one row per state per sweep ─────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS schedule_rule_extraction_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            state VARCHAR(2) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'running',
            requirement_count INT DEFAULT 0,
            extracted_count INT DEFAULT 0,
            ai_model VARCHAR(60),
            error_message TEXT,
            triggered_by UUID REFERENCES users(id),
            started_at TIMESTAMP NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMP
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sre_runs_state
            ON schedule_rule_extraction_runs(state, started_at DESC)
    """)

    # ── schedule_rule_extractions: per-(state, rule_key) reviewed threshold ─
    #
    # Platform-level law, like the catalog itself — no company_id. `rule_value`
    # is nullable because `no_rule=true` (the law affirmatively imposes no such
    # limit, the NO_CAP sentinel's DB-backed twin) carries no number.
    # `source_requirement_id` is ON DELETE SET NULL rather than CASCADE: if the
    # backing catalog row is later deleted, the extracted threshold and its
    # human approval must not vanish silently — `source_snapshot` preserves
    # what the row said at extraction time regardless.
    op.execute("""
        CREATE TABLE IF NOT EXISTS schedule_rule_extractions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            state VARCHAR(2) NOT NULL,
            rule_key VARCHAR(50) NOT NULL,
            rule_value DECIMAL(6,2),
            no_rule BOOLEAN NOT NULL DEFAULT false,
            citation TEXT NOT NULL,
            source_requirement_id UUID REFERENCES jurisdiction_requirements(id) ON DELETE SET NULL,
            source_snapshot JSONB,
            extraction_run_id UUID REFERENCES schedule_rule_extraction_runs(id) ON DELETE SET NULL,
            ai_confidence DECIMAL(3,2),
            ai_rationale TEXT,
            review_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            block_grade BOOLEAN NOT NULL DEFAULT false,
            proposed JSONB,
            stale_since TIMESTAMP,
            reviewed_by UUID REFERENCES users(id),
            reviewed_at TIMESTAMP,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(state, rule_key)
        )
    """)
    # The one query the write-path gate runs, on every shift create/update/
    # assign — a state's approved, active rows.
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sre_gate_lookup
            ON schedule_rule_extractions(state)
            WHERE review_status = 'approved' AND is_active = true
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sre_review_queue
            ON schedule_rule_extractions(state, review_status)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS schedule_rule_extractions")
    op.execute("DROP TABLE IF EXISTS schedule_rule_extraction_runs")
