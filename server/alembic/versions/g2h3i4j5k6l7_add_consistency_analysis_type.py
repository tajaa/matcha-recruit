"""add consistency analysis types to ir_incident_analysis

Revision ID: g2h3i4j5k6l7
Revises: f1d6d19f0f3e
Create Date: 2026-03-07
"""

from alembic import op


revision = "g2h3i4j5k6l7"
down_revision = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE ir_incident_analysis
        DROP CONSTRAINT IF EXISTS ir_incident_analysis_analysis_type_check
    """)
    op.execute("""
        ALTER TABLE ir_incident_analysis
        ADD CONSTRAINT ir_incident_analysis_analysis_type_check
        CHECK (analysis_type IN ('categorization', 'severity', 'root_cause', 'recommendations', 'similar', 'consistency', 'company_consistency'))
    """)


def downgrade():
    op.execute("""
        DELETE FROM ir_incident_analysis
        WHERE analysis_type IN ('consistency', 'company_consistency')
    """)
    op.execute("""
        ALTER TABLE ir_incident_analysis
        DROP CONSTRAINT IF EXISTS ir_incident_analysis_analysis_type_check
    """)
    op.execute("""
        ALTER TABLE ir_incident_analysis
        ADD CONSTRAINT ir_incident_analysis_analysis_type_check
        CHECK (analysis_type IN ('categorization', 'severity', 'root_cause', 'recommendations', 'similar'))
    """)
