"""Commercial property: deeper underwriting capture (COPE+, valuation, policy structure)

Revision ID: propd01
Revises: prop01
Create Date: 2026-06-23

Additive only — widens ``company_property_buildings`` with the underwriting inputs the
risk/exposure engines need to actually measure property risk (vs. the basic SOV):

  - valuation: valuation_basis (RCV/ACV), coinsurance_pct, ordinance_law, bi_months
  - policy structure: blanket, AOP + wind / named-storm / quake deductibles
  - COPE+: roof_type, wiring_year, central_station_alarm
  - occupancy hazards: cooking_nfpa96, hot_work, hazmat
  - policy_detail JSONB — the long tail (agreed value, inflation guard, flood sublimit,
    sprinkler coverage %, HVAC year, security alarm, water supply, distances to
    hydrant/fire-station/coast/brush, roof geometry, occupancy %, extra expense,
    contingent BI, tenant mix, …) — display/optional, no column sprawl.

``ADD COLUMN IF NOT EXISTS`` so it's safe to re-run / stacks cleanly on prop01.
"""

from alembic import op


revision = "propd01"
down_revision = "prop01"
branch_labels = None
depends_on = None

_COLUMNS = [
    "valuation_basis VARCHAR(4)",                 # RCV / ACV
    "coinsurance_pct NUMERIC(5,2)",               # e.g. 90.00
    "ordinance_law VARCHAR(8)",                    # none / A / B / C / ABC
    "bi_months INTEGER",                           # period of restoration
    "blanket BOOLEAN NOT NULL DEFAULT FALSE",      # blanket vs scheduled limit
    "aop_deductible NUMERIC(14,2)",                # all-other-perils flat $
    "wind_deductible_pct NUMERIC(5,2)",
    "named_storm_deductible_pct NUMERIC(5,2)",
    "quake_deductible_pct NUMERIC(5,2)",
    "roof_type VARCHAR(40)",                       # TPO / EPDM / BUR / metal / shingle / tile
    "wiring_year INTEGER",
    "central_station_alarm BOOLEAN NOT NULL DEFAULT FALSE",
    "cooking_nfpa96 BOOLEAN NOT NULL DEFAULT FALSE",
    "hot_work BOOLEAN NOT NULL DEFAULT FALSE",
    "hazmat BOOLEAN NOT NULL DEFAULT FALSE",
    "policy_detail JSONB",
]


def upgrade():
    for col in _COLUMNS:
        op.execute(f"ALTER TABLE company_property_buildings ADD COLUMN IF NOT EXISTS {col}")


def downgrade():
    for col in _COLUMNS:
        name = col.split()[0]
        op.execute(f"ALTER TABLE company_property_buildings DROP COLUMN IF EXISTS {name}")
