"""Hourly POS sales per location and business date, for Autopilot's intraday curve.

Daily sales imports carry no time of day, so Autopilot could only shape a day
from published history or spread it flat. Square's finalized orders carry a
closed_at; the POS sync now aggregates them by local hour into this table.

Written by the sync for every synced day whether its import commits, stays a
draft on unmapped items, or is a duplicate — so a re-run of an old range
backfills hours. Each day is replaced whole on re-sync (never accumulated).

Revision ID: autopilot03
Revises: autopilot02
"""

from alembic import op


revision = "autopilot03"
down_revision = "autopilot02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_sales_hourly (
          company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
          location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
          business_date DATE NOT NULL,
          hour SMALLINT NOT NULL,
          gross_sales NUMERIC(14,2) NOT NULL,
          order_count INT NOT NULL DEFAULT 0,
          source VARCHAR(20) NOT NULL,
          connection_id UUID REFERENCES inventory_pos_connections(id) ON DELETE SET NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (location_id, business_date, hour),
          CONSTRAINT inventory_sales_hourly_hour_check CHECK (hour BETWEEN 0 AND 23),
          CONSTRAINT inventory_sales_hourly_orders_check CHECK (order_count >= 0)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventory_sales_hourly_company "
        "ON inventory_sales_hourly(company_id, location_id, business_date)"
    )
    op.execute("ALTER TABLE inventory_sales_hourly ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE inventory_sales_hourly FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$ BEGIN
          CREATE POLICY tenant_isolation ON inventory_sales_hourly
            USING (
              company_id::text = current_setting('app.current_tenant_id', true)
              OR current_setting('app.is_admin', true) = 'true'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS inventory_sales_hourly")
