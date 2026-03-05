"""add similar_cases to er_case_analysis analysis_type CHECK

Revision ID: b4c5d6e7f8g9
Revises: a3b4c5d6e7f8
Create Date: 2026-03-05
"""

from alembic import op


revision = "b4c5d6e7f8g9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE er_case_analysis
        DROP CONSTRAINT IF EXISTS er_case_analysis_analysis_type_check
    """)
    op.execute("""
        ALTER TABLE er_case_analysis
        ADD CONSTRAINT er_case_analysis_analysis_type_check
        CHECK (analysis_type IN ('timeline', 'discrepancies', 'policy_check', 'summary', 'determination', 'similar_cases'))
    """)


def downgrade():
    op.execute("""
        ALTER TABLE er_case_analysis
        DROP CONSTRAINT IF EXISTS er_case_analysis_analysis_type_check
    """)
    op.execute("""
        ALTER TABLE er_case_analysis
        ADD CONSTRAINT er_case_analysis_analysis_type_check
        CHECK (analysis_type IN ('timeline', 'discrepancies', 'policy_check', 'summary', 'determination'))
    """)
