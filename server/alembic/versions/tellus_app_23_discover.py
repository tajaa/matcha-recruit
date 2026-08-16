"""tellus_app_23 — indexes for Discover (nearby + city browse).

No new tables — tellus_brand_follows and tellus_stores.lat/lng already exist.
tellus_stores has only ix_tellus_stores_brand today, so neither the geo nor
the city-fallback Discover query is plannable without these. See
TELLUS_DISCOVER_PLAN.md at the repo root for the full feature design.
"""
from alembic import op


revision = "tellus_app_23"
down_revision = "tellus_app_22"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_tellus_stores_geo
             ON tellus_stores (lat, lng)
            WHERE lat IS NOT NULL AND lng IS NOT NULL"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_tellus_stores_city
             ON tellus_stores (lower(city), lower(state))"""
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tellus_stores_city")
    op.execute("DROP INDEX IF EXISTS ix_tellus_stores_geo")
