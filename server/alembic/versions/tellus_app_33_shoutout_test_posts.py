"""Allow explicitly labeled manual test runs for the Tell-Us shoutout radar."""
from alembic import op


revision = "tellus_app_33"
down_revision = "tellus_app_32"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE tellus_shoutout_scan_runs DROP CONSTRAINT IF EXISTS tellus_shoutout_scan_runs_trigger_check")
    op.execute("""ALTER TABLE tellus_shoutout_scan_runs ADD CONSTRAINT tellus_shoutout_scan_runs_trigger_check
        CHECK (trigger IN ('scheduled','admin','test'))""")


def downgrade() -> None:
    op.execute("DELETE FROM tellus_shoutout_scan_runs WHERE trigger = 'test'")
    op.execute("ALTER TABLE tellus_shoutout_scan_runs DROP CONSTRAINT IF EXISTS tellus_shoutout_scan_runs_trigger_check")
    op.execute("""ALTER TABLE tellus_shoutout_scan_runs ADD CONSTRAINT tellus_shoutout_scan_runs_trigger_check
        CHECK (trigger IN ('scheduled','admin'))""")
