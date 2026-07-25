"""add training_mapping analysis type to ir_incident_analysis

`_auto_map_training_topics` (routes/ir_incidents/ai_analysis.py) writes
analysis_type='training_mapping' but the CHECK constraint never allowed it —
every insert violated the constraint and was silently swallowed by the
function's broad except, so the deterministic assign_training Copilot card
never had a `matches` row to read.

Revision ID: trainmap01
Revises: trainsched01
Create Date: 2026-07-25
"""

from alembic import op


revision = "trainmap01"
down_revision = "trainsched01"
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
        CHECK (analysis_type IN ('categorization', 'severity', 'root_cause', 'recommendations', 'similar', 'consistency', 'company_consistency', 'policy_mapping', 'training_mapping'))
    """)


def downgrade():
    op.execute("""
        DELETE FROM ir_incident_analysis
        WHERE analysis_type = 'training_mapping'
    """)
    op.execute("""
        ALTER TABLE ir_incident_analysis
        DROP CONSTRAINT IF EXISTS ir_incident_analysis_analysis_type_check
    """)
    op.execute("""
        ALTER TABLE ir_incident_analysis
        ADD CONSTRAINT ir_incident_analysis_analysis_type_check
        CHECK (analysis_type IN ('categorization', 'severity', 'root_cause', 'recommendations', 'similar', 'consistency', 'company_consistency', 'policy_mapping'))
    """)
