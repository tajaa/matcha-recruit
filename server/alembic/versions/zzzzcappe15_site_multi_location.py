"""cappe: per-site multi-location flag

Adds `cappe_sites.is_multi_location` so the onboarding wizard can record whether
a business runs one location or several. The flag drives UX shaping — single
sites hide the branch/location selectors (bookings, CSV import), multi sites
surface them. Backend query helpers already tolerate either case (location_id
is NULLABLE = shared/all), so this is purely an intent flag; no data backfill.

Existing sites default to false (single-location), preserving today's behavior.

Revision ID: zzzzcappe15
Revises: zzzzcappe14
Create Date: 2026-06-16
"""
from alembic import op

revision = "zzzzcappe15"
down_revision = "zzzzcappe14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE cappe_sites "
        "ADD COLUMN IF NOT EXISTS is_multi_location BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE cappe_sites DROP COLUMN IF EXISTS is_multi_location")
