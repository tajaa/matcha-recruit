"""add ranked_results table for multi-signal candidate scoring

Revision ID: a7b8c9d0e1f
Revises: z6a7b8c9d0e
Create Date: 2026-02-17
"""

from alembic import op


revision = "a7b8c9d0e1f"
down_revision = "z6a7b8c9d0e"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ranked_results (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
            candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
            overall_rank_score FLOAT,
            screening_score FLOAT,
            conversation_score FLOAT,
            culture_alignment_score FLOAT,
            signal_breakdown JSONB,
            has_interview_data BOOLEAN DEFAULT false,
            interview_ids JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(company_id, candidate_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ranked_results_company_id ON ranked_results(company_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ranked_results_candidate_id ON ranked_results(candidate_id)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_ranked_results_candidate_id")
    op.execute("DROP INDEX IF EXISTS idx_ranked_results_company_id")
    op.execute("DROP TABLE IF EXISTS ranked_results")
