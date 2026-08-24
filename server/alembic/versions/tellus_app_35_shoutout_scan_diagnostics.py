"""Persist Tell-Us shoutout scan rejection diagnostics."""
from alembic import op


revision = "tellus_app_35"
down_revision = "tellus_app_34"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE tellus_shoutout_scan_runs
        ADD COLUMN IF NOT EXISTS source_mismatch_rejected INT NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS invalid_candidates_rejected INT NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS below_confidence_rejected INT NOT NULL DEFAULT 0""")


def downgrade() -> None:
    op.execute("""ALTER TABLE tellus_shoutout_scan_runs
        DROP COLUMN IF EXISTS source_mismatch_rejected,
        DROP COLUMN IF EXISTS invalid_candidates_rejected,
        DROP COLUMN IF EXISTS below_confidence_rejected""")
