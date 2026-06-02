"""per-project last-scanned commit cursor (watermark)

Commit-scan was re-evaluating the last N commits on every scan → one Gemini call
per commit, every time. Remember the newest commit we've scanned so auto-scan
only evaluates NEW commits since then. Manual scan can force a bounded re-scan.

Revision ID: ghscan0001
Revises: ghconn0001
Create Date: 2026-06-02
"""

from alembic import op


revision = "ghscan0001"
down_revision = "ghconn0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE mw_projects ADD COLUMN IF NOT EXISTS github_last_scanned_sha TEXT"
    )


def downgrade():
    op.execute(
        "ALTER TABLE mw_projects DROP COLUMN IF EXISTS github_last_scanned_sha"
    )
