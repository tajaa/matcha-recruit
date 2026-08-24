"""Guarded closed-loop predictive inventory pars."""

from alembic import op


revision = "invwaste04"
down_revision = "invwaste03"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS par_source VARCHAR(10) NOT NULL DEFAULT 'manual'")
    op.execute("ALTER TABLE inventory_items DROP CONSTRAINT IF EXISTS inventory_items_par_source_check")
    op.execute("ALTER TABLE inventory_items ADD CONSTRAINT inventory_items_par_source_check CHECK (par_source IN ('manual','auto'))")
    op.execute("ALTER TABLE inventory_forecast_settings ADD COLUMN IF NOT EXISTS par_auto_apply BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE inventory_forecast_settings ADD COLUMN IF NOT EXISTS par_max_drift_pct NUMERIC NOT NULL DEFAULT 0.5")
    op.execute("ALTER TABLE inventory_forecast_settings DROP CONSTRAINT IF EXISTS inventory_forecast_settings_par_max_drift_pct_check")
    op.execute("ALTER TABLE inventory_forecast_settings ADD CONSTRAINT inventory_forecast_settings_par_max_drift_pct_check CHECK (par_max_drift_pct > 0 AND par_max_drift_pct <= 5)")
    for column, sql_type in (("recommended_par", "NUMERIC"), ("par_basis", "VARCHAR(24)"),
                             ("current_par", "NUMERIC"), ("shelf_cap_quantity", "NUMERIC")):
        op.execute(f"ALTER TABLE inventory_forecast_lines ADD COLUMN IF NOT EXISTS {column} {sql_type}")
    op.execute("ALTER TABLE inventory_forecast_lines ADD COLUMN IF NOT EXISTS shelf_life_capped BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("""
        CREATE TABLE IF NOT EXISTS inventory_par_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            item_id UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
            run_id UUID REFERENCES inventory_forecast_runs(id) ON DELETE SET NULL,
            previous_par NUMERIC, new_par NUMERIC NOT NULL, par_basis VARCHAR(24), drift_pct NUMERIC,
            source VARCHAR(10) NOT NULL CHECK (source IN ('auto','manual','huume')),
            reason VARCHAR(200), changed_by UUID REFERENCES users(id) ON DELETE SET NULL,
            changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_inventory_par_history_item ON inventory_par_history (item_id, changed_at DESC)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_par_history_run_item ON inventory_par_history (run_id, item_id) WHERE run_id IS NOT NULL")


def downgrade():
    op.execute("DROP INDEX IF EXISTS uniq_inventory_par_history_run_item")
    op.execute("DROP INDEX IF EXISTS idx_inventory_par_history_item")
    op.execute("DROP TABLE IF EXISTS inventory_par_history")
    op.execute("ALTER TABLE inventory_forecast_lines DROP COLUMN IF EXISTS shelf_life_capped")
    for column in ("shelf_cap_quantity", "current_par", "par_basis", "recommended_par"):
        op.execute(f"ALTER TABLE inventory_forecast_lines DROP COLUMN IF EXISTS {column}")
    op.execute("ALTER TABLE inventory_forecast_settings DROP CONSTRAINT IF EXISTS inventory_forecast_settings_par_max_drift_pct_check")
    op.execute("ALTER TABLE inventory_forecast_settings DROP COLUMN IF EXISTS par_max_drift_pct")
    op.execute("ALTER TABLE inventory_forecast_settings DROP COLUMN IF EXISTS par_auto_apply")
    op.execute("ALTER TABLE inventory_items DROP CONSTRAINT IF EXISTS inventory_items_par_source_check")
    op.execute("ALTER TABLE inventory_items DROP COLUMN IF EXISTS par_source")
