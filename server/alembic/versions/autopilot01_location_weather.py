"""Add location coordinates and persisted daily weather forecasts.

Revision ID: autopilot01
Revises: laborcost01
"""

from alembic import op


revision = "autopilot01"
down_revision = "laborcost01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE business_locations
          ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION,
          ADD COLUMN IF NOT EXISTS lng DOUBLE PRECISION,
          ADD COLUMN IF NOT EXISTS geocoded_at TIMESTAMPTZ,
          ADD COLUMN IF NOT EXISTS geocode_source VARCHAR(20)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_weather_days (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
          location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
          local_date DATE NOT NULL,
          condition VARCHAR(40),
          precip_probability SMALLINT,
          precip_qpf_mm NUMERIC(6,2),
          max_temp_c NUMERIC(5,2),
          min_temp_c NUMERIC(5,2),
          provider VARCHAR(20) NOT NULL DEFAULT 'google',
          fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          raw JSONB NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT schedule_weather_days_location_date_unique UNIQUE(location_id, local_date),
          CONSTRAINT schedule_weather_days_precip_check
            CHECK (precip_probability IS NULL OR precip_probability BETWEEN 0 AND 100)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedule_weather_days_company "
        "ON schedule_weather_days(company_id, location_id, local_date)"
    )
    op.execute("ALTER TABLE schedule_weather_days ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE schedule_weather_days FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$ BEGIN
          CREATE POLICY tenant_isolation ON schedule_weather_days
            USING (
              company_id::text = current_setting('app.current_tenant_id', true)
              OR current_setting('app.is_admin', true) = 'true'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
        """
    )
    op.execute(
        """
        INSERT INTO scheduler_settings(task_key, display_name, description, enabled, max_per_cycle)
        VALUES(
          'location_weather_refresh', 'Location weather refresh',
          'Fetch a 10-day daily forecast per Autopilot-enabled location (Google Weather)',
          FALSE, 50
        )
        ON CONFLICT (task_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM scheduler_settings WHERE task_key='location_weather_refresh'")
    op.execute("DROP TABLE IF EXISTS schedule_weather_days")
    op.execute(
        """
        ALTER TABLE business_locations
          DROP COLUMN IF EXISTS geocode_source,
          DROP COLUMN IF EXISTS geocoded_at,
          DROP COLUMN IF EXISTS lng,
          DROP COLUMN IF EXISTS lat
        """
    )
