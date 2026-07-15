"""FIPS anchors for jurisdictions + locations (deterministic resolution).

WHY THIS EXISTS
----------------
A business address resolves to its overlapping authorities by NAME today
(`_get_or_create_jurisdiction` matches on city/state strings + a reference-table
county lookup). Name-match silently mis-resolves the hard cases — an
unincorporated address that isn't really in any city, an annexation edge, two
towns sharing a name — and the worst failure mode in compliance is a silent
coverage gap that looks fine.

This adds a deterministic anchor: the US Census FIPS codes (county GEOID + place
GEOID), populated out-of-band by the `location_fips_backfill` worker (geocoding
is slow + flaky, so it must never sit in a request path). Each location also
records HOW it was resolved (`jurisdiction_resolution`) so a name-matched or
unresolved location is VISIBLE, not silently trusted.

No data is repointed here and none inline — the worker stamps FIPS and flags
mismatches (FIPS disagrees with the current name-matched jurisdiction) for admin
review. New locations default to 'name' so the next backfill pass picks them up.

Revision ID: jurfips01
Revises: jrver01
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa

revision = "jurfips01"
down_revision = "jrver01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jurisdictions", sa.Column("place_fips", sa.Text(), nullable=True))
    op.add_column("jurisdictions", sa.Column("county_fips", sa.Text(), nullable=True))
    # place_fips uniquely identifies an incorporated place nationally; partial so
    # the many rows without one (states, counties, unresolved cities) don't clash.
    op.execute(
        "CREATE UNIQUE INDEX uq_jurisdictions_place_fips ON jurisdictions (place_fips) "
        "WHERE place_fips IS NOT NULL"
    )

    op.add_column("business_locations", sa.Column("place_fips", sa.Text(), nullable=True))
    op.add_column("business_locations", sa.Column("county_fips", sa.Text(), nullable=True))
    # 'name' = resolved by string match (default, current behavior); 'fips' =
    # anchored by geocode; 'unresolved' = geocode found nothing. Backfills every
    # existing row to 'name' so all are candidates for the first backfill pass.
    op.add_column(
        "business_locations",
        sa.Column("jurisdiction_resolution", sa.Text(), nullable=False, server_default="name"),
    )
    op.create_index(
        "ix_business_locations_resolution", "business_locations", ["jurisdiction_resolution"],
    )

    # Scheduler row for the backfill worker — seeded DISABLED (makes live Census
    # calls; an admin enables it deliberately, same pattern as vertcov02).
    op.execute(
        """
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES ('location_fips_backfill', 'Location FIPS backfill',
                'Geocode business locations to Census FIPS anchors + flag name-match mismatches.',
                false, 100)
        ON CONFLICT (task_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'location_fips_backfill'")
    op.drop_index("ix_business_locations_resolution", table_name="business_locations")
    op.drop_column("business_locations", "jurisdiction_resolution")
    op.drop_column("business_locations", "county_fips")
    op.drop_column("business_locations", "place_fips")
    op.execute("DROP INDEX IF EXISTS uq_jurisdictions_place_fips")
    op.drop_column("jurisdictions", "county_fips")
    op.drop_column("jurisdictions", "place_fips")
