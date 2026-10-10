"""Cappe — booking controls: notice, horizon, cutoff, time off, owner bookings.

`cappe_booking_types`
  * `min_notice_minutes` — the soonest a customer can book (0 = any future time).
  * `max_advance_days` — the furthest ahead (NULL = no limit beyond the widget's).
  * `cancel_cutoff_hours` — customers can cancel or move a booking themselves
    until this long before it starts; after that they contact the store.

`cappe_time_off` — closed periods: the whole business, one location or one
staff member. Slots inside one aren't offered and can't be booked.

`cappe_bookings.created_by_owner` — the owner booked it (a phone call, a walk
in). Owner bookings skip the notice, horizon and opening-hours rules; they
still can't double-book.

Additive + idempotent.

Revision ID: zzzzcappe48
Revises: zzzzcappe47
"""
from alembic import op

revision = "zzzzcappe48"
down_revision = "zzzzcappe47"
branch_labels = None
depends_on = None

_UPGRADE = [
    """
    ALTER TABLE cappe_booking_types
        ADD COLUMN IF NOT EXISTS min_notice_minutes  INTEGER NOT NULL DEFAULT 0
            CHECK (min_notice_minutes BETWEEN 0 AND 43200),
        ADD COLUMN IF NOT EXISTS max_advance_days    INTEGER
            CHECK (max_advance_days BETWEEN 1 AND 730),
        ADD COLUMN IF NOT EXISTS cancel_cutoff_hours INTEGER NOT NULL DEFAULT 0
            CHECK (cancel_cutoff_hours BETWEEN 0 AND 720)
    """,
    """
    CREATE TABLE IF NOT EXISTS cappe_time_off (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        site_id     UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        staff_id    UUID REFERENCES cappe_staff(id) ON DELETE CASCADE,
        location_id UUID REFERENCES cappe_locations(id) ON DELETE CASCADE,
        starts_at   TIMESTAMPTZ NOT NULL,
        ends_at     TIMESTAMPTZ NOT NULL,
        reason      VARCHAR(200),
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CHECK (ends_at > starts_at)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_time_off_site ON cappe_time_off (site_id, ends_at)",
    "ALTER TABLE cappe_bookings ADD COLUMN IF NOT EXISTS created_by_owner BOOLEAN NOT NULL DEFAULT FALSE",
]

_DOWNGRADE = [
    "ALTER TABLE cappe_bookings DROP COLUMN IF EXISTS created_by_owner",
    "DROP TABLE IF EXISTS cappe_time_off",
    """
    ALTER TABLE cappe_booking_types
        DROP COLUMN IF EXISTS cancel_cutoff_hours, DROP COLUMN IF EXISTS max_advance_days,
        DROP COLUMN IF EXISTS min_notice_minutes
    """,
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
