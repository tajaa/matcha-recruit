"""Mark rows created by Oceanlab label defaults.

Revision ID: oceanlab_app_03
Revises: oceanlab_app_02
"""

from alembic import op


revision = "oceanlab_app_03"
down_revision = "oceanlab_app_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE oceanlab_master_splits "
        "ADD COLUMN IF NOT EXISTS auto_created BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE oceanlab_works "
        "ADD COLUMN IF NOT EXISTS auto_created BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE oceanlab_work_writers "
        "ADD COLUMN IF NOT EXISTS auto_created BOOLEAN NOT NULL DEFAULT FALSE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE oceanlab_work_writers DROP COLUMN IF EXISTS auto_created")
    op.execute("ALTER TABLE oceanlab_works DROP COLUMN IF EXISTS auto_created")
    op.execute("ALTER TABLE oceanlab_master_splits DROP COLUMN IF EXISTS auto_created")
