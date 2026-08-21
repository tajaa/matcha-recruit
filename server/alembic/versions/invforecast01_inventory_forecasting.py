"""Persist deterministic inventory demand forecasts and replenishment rules."""

from alembic import op


revision = "invforecast01"
down_revision = "safemeet01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS inventory_forecast_settings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            horizon_days INT NOT NULL DEFAULT 56 CHECK (horizon_days BETWEEN 14 AND 90),
            history_days INT NOT NULL DEFAULT 90 CHECK (history_days BETWEEN 28 AND 365),
            default_lead_time_days INT NOT NULL DEFAULT 7 CHECK (default_lead_time_days BETWEEN 0 AND 180),
            default_safety_stock_days INT NOT NULL DEFAULT 7 CHECK (default_safety_stock_days BETWEEN 0 AND 180),
            timezone VARCHAR(80) NOT NULL DEFAULT 'America/Los_Angeles',
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_forecast_settings_scope
        ON inventory_forecast_settings (company_id, location_id) NULLS NOT DISTINCT
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS inventory_forecast_replenishment_rules (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            item_id UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
            lead_time_days INT NOT NULL CHECK (lead_time_days BETWEEN 0 AND 180),
            safety_stock_days INT NOT NULL CHECK (safety_stock_days BETWEEN 0 AND 180),
            case_pack_quantity NUMERIC NOT NULL CHECK (case_pack_quantity > 0),
            minimum_order_quantity NUMERIC NOT NULL DEFAULT 0 CHECK (minimum_order_quantity >= 0),
            updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (company_id, item_id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS inventory_forecast_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            forecast_start DATE NOT NULL,
            forecast_end DATE NOT NULL,
            history_start DATE NOT NULL,
            settings_snapshot JSONB NOT NULL,
            override_count INT NOT NULL DEFAULT 0,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_inventory_forecast_runs_scope
        ON inventory_forecast_runs (company_id, location_id, created_at DESC)
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS inventory_forecast_overrides (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            run_id UUID NOT NULL REFERENCES inventory_forecast_runs(id) ON DELETE CASCADE,
            week_start DATE NOT NULL,
            demand_multiplier NUMERIC NOT NULL CHECK (demand_multiplier BETWEEN 0.5 AND 2.0),
            reason VARCHAR(500) NOT NULL,
            source VARCHAR(20) NOT NULL CHECK (source IN ('manual', 'ai_accepted')),
            confidence VARCHAR(20),
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS inventory_forecast_lines (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL REFERENCES inventory_forecast_runs(id) ON DELETE CASCADE,
            item_id UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
            status VARCHAR(30) NOT NULL CHECK (status IN ('ready', 'count_required', 'no_demand', 'insufficient_history')),
            confidence VARCHAR(20) NOT NULL,
            history_nonzero_days INT NOT NULL DEFAULT 0,
            current_quantity NUMERIC,
            on_order_quantity NUMERIC NOT NULL DEFAULT 0,
            projected_demand NUMERIC NOT NULL DEFAULT 0,
            average_daily_demand NUMERIC NOT NULL DEFAULT 0,
            lead_demand NUMERIC NOT NULL DEFAULT 0,
            safety_demand NUMERIC NOT NULL DEFAULT 0,
            target_quantity NUMERIC NOT NULL DEFAULT 0,
            suggested_quantity NUMERIC,
            runout_date DATE,
            order_by_date DATE,
            daily_demand JSONB NOT NULL DEFAULT '[]',
            calculation JSONB NOT NULL DEFAULT '{}',
            UNIQUE (run_id, item_id)
        )
    """)



def downgrade():
    op.execute("DROP TABLE IF EXISTS inventory_forecast_lines")
    op.execute("DROP TABLE IF EXISTS inventory_forecast_overrides")
    op.execute("DROP INDEX IF EXISTS idx_inventory_forecast_runs_scope")
    op.execute("DROP TABLE IF EXISTS inventory_forecast_runs")
    op.execute("DROP TABLE IF EXISTS inventory_forecast_replenishment_rules")
    op.execute("DROP INDEX IF EXISTS uniq_inventory_forecast_settings_scope")
    op.execute("DROP TABLE IF EXISTS inventory_forecast_settings")
