"""fix stuck interviews with no transcript

Revision ID: zzza7b8c9d0e1
Revises: zzz6a7b8c9d0
Create Date: 2026-04-17

When a Gemini WS session started but produced no transcript (connection
failure, instant disconnect, API error), the WS handler was permanently
setting status='completed'. Candidates/users could never retry. This
migration resets those stuck records back to 'pending' across all
interview types (screening, tutor, investigation, etc).
"""

from alembic import op


revision = "zzza7b8c9d0e1"
down_revision = "zzz6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    # Reset only rows that show the stuck-pattern: completed with no transcript
    # AND no analysis artifact of any kind. Legit completed rows always have at
    # least one of transcript, screening_analysis, or investigation_analysis.
    op.execute("""
        UPDATE interviews
        SET status = 'pending', completed_at = NULL
        WHERE status = 'completed'
          AND screening_analysis IS NULL
          AND investigation_analysis IS NULL
          AND (transcript IS NULL OR transcript = '')
    """)


def downgrade():
    pass
