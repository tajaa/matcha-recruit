"""add policy_mapping analysis type to ir_incident_analysis

Revision ID: zj8k9l0m1n2o
Revises: zi7j8k9l0m1n
Create Date: 2026-03-15
"""

from alembic import op


revision = "zj8k9l0m1n2o"
down_revision = "zi7j8k9l0m1n"
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
        CHECK (analysis_type IN ('categorization', 'severity', 'root_cause', 'recommendations', 'similar', 'consistency', 'company_consistency', 'policy_mapping'))
    """)


def downgrade():
    op.execute("""
        DELETE FROM ir_incident_analysis
        WHERE analysis_type = 'policy_mapping'
    """)
    op.execute("""
        ALTER TABLE ir_incident_analysis
        DROP CONSTRAINT IF EXISTS ir_incident_analysis_analysis_type_check
    """)
    op.execute("""
        ALTER TABLE ir_incident_analysis
        ADD CONSTRAINT ir_incident_analysis_analysis_type_check
        CHECK (analysis_type IN ('categorization', 'severity', 'root_cause', 'recommendations', 'similar', 'consistency', 'company_consistency'))
    """)
