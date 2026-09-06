"""Record whether a location requires a shift lead on every shift.

`leader_job_id IS NULL` could not be told apart from "nobody has been asked
yet", so the setup interview had no way to record "no lead needed" and no way
to know it was finished. That mattered once the week builder started refusing
to plan a week for a location whose rules are not established: without this
column a store that genuinely needs no lead could never satisfy the gate.

NULL = never asked, false = no lead required, true = a lead is required (and
the CHECK guarantees the job is named).

Revision ID: schedloc03
Revises: huumesched02
"""

from alembic import op


revision = "schedloc03"
down_revision = "huumesched02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE schedule_location_profiles
        ADD COLUMN IF NOT EXISTS leader_required BOOLEAN
        """
    )
    # A location that already names a leader job answered the question by
    # naming it — without this backfill every configured store would be sent
    # back through the interview for an answer it already gave.
    op.execute(
        """
        UPDATE schedule_location_profiles
        SET leader_required = true
        WHERE leader_job_id IS NOT NULL AND leader_required IS NULL
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'schedule_location_profiles_leader_ck'
            ) THEN
                ALTER TABLE schedule_location_profiles
                ADD CONSTRAINT schedule_location_profiles_leader_ck
                CHECK (leader_required IS NOT TRUE OR leader_job_id IS NOT NULL);
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE schedule_location_profiles "
        "DROP CONSTRAINT IF EXISTS schedule_location_profiles_leader_ck"
    )
    op.execute(
        "ALTER TABLE schedule_location_profiles DROP COLUMN IF EXISTS leader_required"
    )
