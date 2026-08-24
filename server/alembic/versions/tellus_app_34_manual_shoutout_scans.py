"""Allow brand-initiated Tell-Us shoutout scans."""
from alembic import op


revision = "tellus_app_34"
down_revision = "tellus_app_33"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE tellus_shoutout_scan_runs DROP CONSTRAINT IF EXISTS tellus_shoutout_scan_runs_trigger_check")
    op.execute("""ALTER TABLE tellus_shoutout_scan_runs ADD CONSTRAINT tellus_shoutout_scan_runs_trigger_check
        CHECK (trigger IN ('scheduled','admin','test','manual'))""")


def downgrade() -> None:
    op.execute("DELETE FROM tellus_shoutout_scan_runs WHERE trigger = 'manual'")
    op.execute("ALTER TABLE tellus_shoutout_scan_runs DROP CONSTRAINT IF EXISTS tellus_shoutout_scan_runs_trigger_check")
    op.execute("""ALTER TABLE tellus_shoutout_scan_runs ADD CONSTRAINT tellus_shoutout_scan_runs_trigger_check
        CHECK (trigger IN ('scheduled','admin','test'))""")
