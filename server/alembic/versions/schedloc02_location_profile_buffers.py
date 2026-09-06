"""Opening/closing prep buffers on a location's scheduling profile.

`operating_hours` says when the doors are open. Real stores need somebody on
the floor before that (prep, count, open the till) and after it (clean down,
cash out), and a week that staffs exactly the open window reads as fully
covered while nobody is scheduled for either. These two columns are what the
coverage evaluator widens the day's required window by.

Minutes, not a time-of-day: a buffer is relative to whatever that weekday's
open/close happens to be. 0 (today's behavior) means "no buffer required".

Revision ID: schedloc02
Revises: schedloc01
"""

from alembic import op


revision = "schedloc02"
down_revision = "schedloc01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE schedule_location_profiles
            ADD COLUMN IF NOT EXISTS open_buffer_minutes  SMALLINT NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS close_buffer_minutes SMALLINT NOT NULL DEFAULT 0
        """
    )
    # Named separately from the ADD COLUMN so a re-run of a partially applied
    # upgrade does not fail on a constraint that is already there.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                 WHERE conname = 'ck_schedule_location_profiles_open_buffer'
            ) THEN
                ALTER TABLE schedule_location_profiles
                    ADD CONSTRAINT ck_schedule_location_profiles_open_buffer
                    CHECK (open_buffer_minutes BETWEEN 0 AND 240);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                 WHERE conname = 'ck_schedule_location_profiles_close_buffer'
            ) THEN
                ALTER TABLE schedule_location_profiles
                    ADD CONSTRAINT ck_schedule_location_profiles_close_buffer
                    CHECK (close_buffer_minutes BETWEEN 0 AND 240);
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE schedule_location_profiles
            DROP COLUMN IF EXISTS open_buffer_minutes,
            DROP COLUMN IF EXISTS close_buffer_minutes
        """
    )
