"""Cappe multi-location support.

A business can run several locations (e.g. an LA shop and a San Diego shop) under
one site. A new `cappe_locations` table holds each location's name / address /
hours / timezone, and the booking tables gain a NULLABLE `location_id`
(NULL = "all locations / main"), so a single-location site is unchanged.

The double-book guard and the availability uniqueness index are rebuilt to
include location_id (COALESCE'd to a sentinel for the partial guard, same lesson
as staff_id in zzzzcappe12 — NULLs are otherwise distinct in a unique index).
This lets two locations hold identical windows and the same staff member be
booked at two locations at the same instant, while same-location/same-staff/
same-time stays guarded.

Revision ID: zzzzcappe13
Revises: nlsuppress01
"""
from alembic import op

revision = "zzzzcappe13"
down_revision = "nlsuppress01"
branch_labels = None
depends_on = None

_SENTINEL = "00000000-0000-0000-0000-000000000000"

# Booking tables that gain a nullable location_id (riders stay site-global).
_LOC_TABLES = (
    "cappe_booking_types",
    "cappe_availability",
    "cappe_bookings",
    "cappe_staff",
    "cappe_rate_rules",
    "cappe_discounts",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_locations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            address TEXT,
            lat DOUBLE PRECISION,
            lng DOUBLE PRECISION,
            timezone VARCHAR(64),
            hours JSONB NOT NULL DEFAULT '[]'::jsonb,
            contact_phone VARCHAR(64),
            contact_email VARCHAR(255),
            is_default BOOLEAN NOT NULL DEFAULT false,
            active BOOLEAN NOT NULL DEFAULT true,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT cappe_locations_site_name_unique UNIQUE (site_id, name)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_locations_site ON cappe_locations(site_id, active, sort_order)")

    # NULLABLE location_id everywhere — NULL = "all locations / main" (zero
    # backfill, single-location sites unchanged). ON DELETE SET NULL preserves
    # booking history when a location is hard-deleted (soft-delete via active).
    for tbl in _LOC_TABLES:
        op.execute(
            f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS location_id UUID "
            "REFERENCES cappe_locations(id) ON DELETE SET NULL"
        )
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_bookings_location ON cappe_bookings(location_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_availability_location ON cappe_availability(location_id)")

    # Rebuild the double-book guard to be location-aware (sentinel-COALESCE so a
    # NULL location still shares ONE key, like staff_id).
    op.execute("DROP INDEX IF EXISTS idx_cappe_bookings_no_doublebook")
    op.execute(
        "CREATE UNIQUE INDEX idx_cappe_bookings_no_doublebook "
        "ON cappe_bookings(site_id, booking_type_id, "
        "COALESCE(staff_id, '%s'::uuid), COALESCE(location_id, '%s'::uuid), starts_at) "
        "WHERE status IN ('pending', 'confirmed')" % (_SENTINEL, _SENTINEL)
    )

    # Extend availability uniqueness to include location_id (two locations may
    # hold the same window for the same service + staff).
    op.execute("DROP INDEX IF EXISTS idx_cappe_availability_unique")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cappe_availability_unique "
        "ON cappe_availability(site_id, weekday, start_time, end_time, booking_type_id, staff_id, location_id)"
    )


def downgrade() -> None:
    # Restore the zzzzcappe12 (staff-aware, no location) versions of both indexes.
    op.execute("DROP INDEX IF EXISTS idx_cappe_availability_unique")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cappe_availability_unique "
        "ON cappe_availability(site_id, weekday, start_time, end_time, booking_type_id, staff_id)"
    )
    op.execute("DROP INDEX IF EXISTS idx_cappe_bookings_no_doublebook")
    op.execute(
        "CREATE UNIQUE INDEX idx_cappe_bookings_no_doublebook "
        "ON cappe_bookings(site_id, booking_type_id, COALESCE(staff_id, '%s'::uuid), starts_at) "
        "WHERE status IN ('pending', 'confirmed')" % _SENTINEL
    )

    op.execute("DROP INDEX IF EXISTS idx_cappe_availability_location")
    op.execute("DROP INDEX IF EXISTS idx_cappe_bookings_location")
    for tbl in _LOC_TABLES:
        op.execute(f"ALTER TABLE {tbl} DROP COLUMN IF EXISTS location_id")
    op.execute("DROP TABLE IF EXISTS cappe_locations")
