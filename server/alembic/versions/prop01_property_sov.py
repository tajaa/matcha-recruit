"""Commercial property: Statement of Values + cat perils + external snapshot

Revision ID: prop01
Revises: wcmodsrc01
Create Date: 2026-06-22

Adds the PROPERTY side at casualty parity. Four tables + one coarse cat-reference
seed + a scheduler row. All created now (even columns/tables only populated by
later phases) so the cat subsystem (Phase 3) and broker parity (Phase 4) are
code-only — no further migration churn.

- ``company_property_buildings`` — per-building Statement of Values: COPE
  (construction / occupancy / protection / exposure) + values (building / contents
  / business-interruption / replacement-cost / insured-value) + geocode columns
  (filled by the Phase-3 cat task) for insurance-to-value + catastrophe scoring.
- ``property_building_perils`` — one row per (building, peril) with the geocoded
  hazard tier + provenance. Child table (not JSONB) so a broker book rolls up in
  one query and partial fetch success / per-source errors model cleanly.
- ``coastal_wind_tier`` — coarse state/county hurricane-wind tiers (there is no
  free per-address wind API), modelled on ``venue_severity``: directional,
  sourced, editable. Seeded with hurricane-exposed coastal geographies.
- ``broker_external_property`` — broker-keyed property summary for off-platform
  (Broker Pro) clients, mirroring ``broker_external_wc``.

No CHECK constraint exists on any ``line`` column, so the new ``'property'`` line
key (limits via company_coverage_lines, loss runs via wc_loss_runs) needs no DDL
here — only the Python whitelists widen.
"""

from alembic import op


revision = "prop01"
down_revision = "wcmodsrc01"
branch_labels = None
depends_on = None


def upgrade():
    # --- Statement of Values (per building) --------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS company_property_buildings (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id         UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id        UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            name               VARCHAR(255),
            address            VARCHAR(500),
            city               VARCHAR(120),
            state              VARCHAR(2),
            zipcode            VARCHAR(10),
            county             VARCHAR(120),
            occupancy          VARCHAR(120),
            -- COPE
            construction_type  VARCHAR(40),   -- ISO 1-6: frame / joisted_masonry / non_combustible /
                                              -- masonry_non_combustible / modified_fire_resistive / fire_resistive
            year_built         INTEGER,
            sq_ft              INTEGER,
            stories            INTEGER,
            roof_year          INTEGER,
            sprinklered        BOOLEAN NOT NULL DEFAULT FALSE,
            protection_class   VARCHAR(4),    -- ISO PPC 1-10 (text)
            -- values
            building_value     NUMERIC(14,2),
            contents_value     NUMERIC(14,2),
            bi_value           NUMERIC(14,2),
            replacement_cost   NUMERIC(14,2),
            insured_value      NUMERIC(14,2),
            -- geocode (filled by Phase-3 cat task)
            lat                NUMERIC(9,6),
            lng                NUMERIC(9,6),
            geocoded_at        TIMESTAMPTZ,
            geocode_source     VARCHAR(40),
            cat_refreshed_at   TIMESTAMPTZ,
            note               TEXT,
            created_by         UUID REFERENCES users(id) ON DELETE SET NULL,
            updated_by         UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_property_buildings_company "
        "ON company_property_buildings(company_id)"
    )

    # --- per-building catastrophe perils (written Phase 3) -----------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS property_building_perils (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            building_id  UUID NOT NULL REFERENCES company_property_buildings(id) ON DELETE CASCADE,
            peril        VARCHAR(20) NOT NULL,   -- flood / quake / wildfire / wind
            zone         VARCHAR(40),            -- FEMA zone / WHP class / SDS band
            score        INTEGER,                -- 0-100 normalized
            tier         VARCHAR(12),            -- severe/high/elevated/moderate/low (venue vocab)
            raw          JSONB,                  -- source's raw answer (provenance/debug)
            source       VARCHAR(80),
            fetched_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            error        TEXT,                   -- non-null when the fetch failed (best-effort)
            CONSTRAINT uq_building_peril UNIQUE (building_id, peril)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_property_perils_building "
        "ON property_building_perils(building_id)"
    )

    # --- coarse coastal-wind reference (mirror venue_severity) -------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS coastal_wind_tier (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            state       VARCHAR(2) NOT NULL,
            county      VARCHAR(120) NOT NULL DEFAULT '',   -- '' = state baseline
            tier        VARCHAR(12) NOT NULL CHECK (tier IN ('severe','high','elevated','moderate','low')),
            score       INTEGER NOT NULL,                    -- 0-100 (higher = worse wind exposure)
            source      VARCHAR(80),
            note        TEXT,
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_coastal_wind UNIQUE (state, county)
        )
        """
    )
    # Directional hurricane-wind tiers (Saffir-Simpson / FEMA wind-zone read).
    # State baselines for hurricane-exposed states + a few severe coastal counties.
    op.execute(
        """
        INSERT INTO coastal_wind_tier (state, county, tier, score, source, note) VALUES
            ('FL','',           'severe',  90, 'FEMA wind zone (coarse)', 'Statewide high hurricane exposure'),
            ('LA','',           'severe',  88, 'FEMA wind zone (coarse)', 'Gulf coast'),
            ('MS','',           'high',    78, 'FEMA wind zone (coarse)', 'Gulf coast'),
            ('AL','',           'high',    76, 'FEMA wind zone (coarse)', 'Gulf coast'),
            ('TX','',           'high',    72, 'FEMA wind zone (coarse)', 'Gulf coast (inland lower)'),
            ('SC','',           'high',    74, 'FEMA wind zone (coarse)', 'Atlantic coast'),
            ('NC','',           'high',    72, 'FEMA wind zone (coarse)', 'Atlantic coast'),
            ('GA','',           'elevated',60, 'FEMA wind zone (coarse)', 'Atlantic coast'),
            ('VA','',           'elevated',55, 'FEMA wind zone (coarse)', 'Mid-Atlantic'),
            ('NJ','',           'elevated',55, 'FEMA wind zone (coarse)', 'Mid-Atlantic'),
            ('NY','',           'elevated',50, 'FEMA wind zone (coarse)', 'Northeast coast'),
            ('MA','',           'moderate',48, 'FEMA wind zone (coarse)', 'Northeast coast'),
            ('HI','',           'elevated',55, 'FEMA wind zone (coarse)', 'Pacific cyclone exposure'),
            ('FL','Miami-Dade', 'severe',  96, 'FEMA wind zone (coarse)', 'High-velocity hurricane zone'),
            ('FL','Monroe',     'severe',  97, 'FEMA wind zone (coarse)', 'Florida Keys'),
            ('TX','Galveston',  'severe',  90, 'FEMA wind zone (coarse)', 'Gulf barrier island'),
            ('LA','Orleans',    'severe',  92, 'FEMA wind zone (coarse)', 'New Orleans'),
            ('NC','Dare',       'high',    82, 'FEMA wind zone (coarse)', 'Outer Banks')
        ON CONFLICT (state, county) DO NOTHING
        """
    )

    # --- off-platform (Broker Pro) property summary -----------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_external_property (
            external_client_id   UUID PRIMARY KEY REFERENCES broker_external_clients(id) ON DELETE CASCADE,
            period_label         VARCHAR(60),
            building_count       INTEGER NOT NULL DEFAULT 0,
            total_tiv            NUMERIC(16,2),
            worst_construction   VARCHAR(40),
            sprinklered_pct      INTEGER,            -- 0-100
            worst_cat_tier       VARCHAR(12),        -- severe/high/elevated/moderate/low
            insured_to_value_pct INTEGER,            -- 0-100+ (ITV)
            carrier              VARCHAR(255),
            annual_premium       NUMERIC(14,2),
            note                 TEXT,
            updated_by           UUID REFERENCES users(id) ON DELETE SET NULL,
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    # --- scheduler row for the Phase-3 cat refresh task (default OFF) ------
    op.execute(
        """
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES (
            'property_cat_refresh',
            'Property Catastrophe Refresh',
            'Geocodes property buildings and refreshes per-peril catastrophe hazard (flood/quake/wildfire/wind) from FEMA/USGS/USFS. Best-effort; default off.',
            false,
            20
        )
        ON CONFLICT (task_key) DO NOTHING
        """
    )


def downgrade():
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'property_cat_refresh'")
    op.execute("DROP TABLE IF EXISTS broker_external_property")
    op.execute("DROP TABLE IF EXISTS coastal_wind_tier")
    op.execute("DROP TABLE IF EXISTS property_building_perils")
    op.execute("DROP TABLE IF EXISTS company_property_buildings")
