"""More than one job can lead a shift.

`leader_job_id` named THE job whose presence counts as lead coverage. Real
stores have several — a shift lead or an assistant manager can both open the
till — and forcing one meant either under-reporting coverage (the AM's open
read as "no lead") or lying about the rule.

`leader_job_ids` is the set; any ONE of them on shift satisfies the rule.
`leader_job_id` stays as a derived mirror of the first element so an image
that predates this migration keeps reading a sensible value across the
deploy, and so the FK's `ON DELETE SET NULL` keeps its meaning. The service
writes both in the same statement; the CHECK moves to the set.

Revision ID: schedloc04
Revises: schedloc03
"""

from alembic import op


revision = "schedloc04"
down_revision = "schedloc03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE schedule_location_profiles
        ADD COLUMN IF NOT EXISTS leader_job_ids UUID[] NOT NULL DEFAULT '{}'
        """
    )
    # Every already-configured store keeps its one leader as a one-element set.
    op.execute(
        """
        UPDATE schedule_location_profiles
        SET leader_job_ids = ARRAY[leader_job_id]
        WHERE leader_job_id IS NOT NULL AND cardinality(leader_job_ids) = 0
        """
    )
    op.execute(
        "ALTER TABLE schedule_location_profiles "
        "DROP CONSTRAINT IF EXISTS schedule_location_profiles_leader_ck"
    )
    op.execute(
        """
        ALTER TABLE schedule_location_profiles
        ADD CONSTRAINT schedule_location_profiles_leader_ck
        CHECK (leader_required IS NOT TRUE OR cardinality(leader_job_ids) > 0)
        """
    )


def downgrade() -> None:
    # The mirror column already holds the first leader, so nothing is lost
    # for single-role stores; extra roles are dropped with the column.
    op.execute(
        "ALTER TABLE schedule_location_profiles "
        "DROP CONSTRAINT IF EXISTS schedule_location_profiles_leader_ck"
    )
    op.execute(
        """
        ALTER TABLE schedule_location_profiles
        ADD CONSTRAINT schedule_location_profiles_leader_ck
        CHECK (leader_required IS NOT TRUE OR leader_job_id IS NOT NULL)
        """
    )
    op.execute(
        "ALTER TABLE schedule_location_profiles DROP COLUMN IF EXISTS leader_job_ids"
    )
