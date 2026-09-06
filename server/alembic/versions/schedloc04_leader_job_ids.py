"""More than one job can lead a shift.

`leader_job_id` named THE job whose presence counts as lead coverage. Real
stores have several — a shift lead or an assistant manager can both open the
till — and forcing one meant either under-reporting coverage (the AM's open
read as "no lead") or lying about the rule.

`leader_job_ids` is the set; any ONE of them on shift satisfies the rule.
`leader_job_id` stays as a derived mirror of the first element so an image
that predates this migration keeps reading a sensible value across the
deploy, and so the FK's `ON DELETE SET NULL` keeps its meaning. The service
writes both in the same statement; the CHECK accepts EITHER spelling, which
is what also keeps the old image's writes legal for the length of a deploy.

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
    # Either spelling satisfies the rule, which is exactly what
    # `profile_leader_job_ids` reads: the set when it has entries, else the
    # mirror. Demanding the ARRAY specifically would break the pre-swap image
    # for the length of a deploy — it writes only `leader_job_id` and leaves
    # the array at '{}', so a manager naming a lead between `migrate-prod.sh`
    # and the blue/green swap gets a CHECK violation surfaced as "Name at
    # least one job that leads every shift" on a PUT that named one.
    op.execute(
        """
        ALTER TABLE schedule_location_profiles
        ADD CONSTRAINT schedule_location_profiles_leader_ck
        CHECK (
            leader_required IS NOT TRUE
            OR cardinality(leader_job_ids) > 0
            OR leader_job_id IS NOT NULL
        )
        """
    )


def downgrade() -> None:
    # The mirror column already holds the first leader, so nothing is lost
    # for single-role stores; extra roles are dropped with the column.
    op.execute(
        "ALTER TABLE schedule_location_profiles "
        "DROP CONSTRAINT IF EXISTS schedule_location_profiles_leader_ck"
    )
    # The scalar can be NULL while the set is not: the FK nulls it when its
    # job is deleted, and nothing inside the array follows. Re-adding the old
    # scalar-only CHECK over such a row aborts the downgrade mid-migration, so
    # the mirror is re-derived first — from a leader that still RESOLVES, since
    # the column is a live FK and a dangling id would fail differently.
    op.execute(
        """
        UPDATE schedule_location_profiles p
        SET leader_job_id = (
            SELECT j.id FROM schedule_jobs j
            WHERE j.id = ANY(p.leader_job_ids) AND j.company_id = p.company_id
            ORDER BY array_position(p.leader_job_ids, j.id), j.id
            LIMIT 1
        )
        WHERE p.leader_job_id IS NULL AND cardinality(p.leader_job_ids) > 0
        """
    )
    # Whatever is still required with nothing nameable goes back to "nobody has
    # answered" — the same un-answering the service does when a leader set is
    # cleared, and the only state left that the old CHECK refuses.
    op.execute(
        """
        UPDATE schedule_location_profiles
        SET leader_required = NULL
        WHERE leader_required IS TRUE AND leader_job_id IS NULL
        """
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
