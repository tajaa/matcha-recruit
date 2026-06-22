"""Widen wc_class_codes.base_rate to NUMERIC(8,3)

Revision ID: wcrate3dp01
Revises: driverrisk01
Create Date: 2026-06-22

WCIRB advisory pure-premium rates are published to 3 decimals (e.g. 5.140,
4.513, 12.836). The original column was NUMERIC(8,2) (a demo-seed precision),
so both load paths (seed_ca_wc_class_codes.py and the admin CSV importer in
wc_rates_admin.py) silently round real rates to 2dp — losing the 3rd decimal
the data carries and the README claims to preserve.

This widens the scale to 3dp so future loads keep full precision. It does NOT
recover already-truncated rows: after applying, re-run the CA seed loader
(server/scripts/wc_data/seed_ca_wc_class_codes.py) to repopulate at 3dp.
"""

from alembic import op


revision = "wcrate3dp01"
down_revision = "driverrisk01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE wc_class_codes ALTER COLUMN base_rate TYPE NUMERIC(8,3)")


def downgrade():
    # narrows back to 2dp (re-truncates stored rates)
    op.execute("ALTER TABLE wc_class_codes ALTER COLUMN base_rate TYPE NUMERIC(8,2)")
