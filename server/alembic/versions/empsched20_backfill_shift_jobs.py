"""backfill schedule_jobs from existing shift role labels

`job_id` is now REQUIRED on manual shift creation. That rule assumes a company
has jobs to pick from, and nothing guaranteed it: `schedule_jobs` arrived in
empsched04 as an optional feature, so every tenant that has been scheduling
since empsched01 without ever opening the Jobs tab has zero rows — and would
have found every POST /employee-schedule/shifts rejected with
"Field required: job_id", unable to add a shift at all.

The labels are already in the data. `schedule_shifts.role` and
`schedule_shift_templates.role` are the free text those tenants have been
typing for months, so this derives one job per distinct label per location,
then points the rows that named it at the job it became.

Two deliberate choices:

- A company that schedules but whose shifts carry NO label at all gets a single
  company-wide "General" job. Inventing one name is the only alternative to
  leaving that tenant unable to create a shift; it is company-wide, so it is
  available at every location.
- Derived jobs get an empty qualified roster, and an empty roster means
  UNGATED (`check_job_qualification`) — so this backfill cannot start
  409-blocking assignments that used to go through.

Revision ID: empsched20
Revises: credvis01
Create Date: 2026-09-02
"""

from alembic import op

revision = "empsched20"
down_revision = "credvis01"
branch_labels = None
depends_on = None

DERIVED_NOTE = "Derived from existing shift role labels (empsched20)"


def upgrade() -> None:
    # 1. One job per distinct label per (company, location), from both the
    #    concrete shifts and the template blocks that generate them. Labels a
    #    company already has a job for — at that location or company-wide —
    #    are skipped, so re-running this is a no-op.
    for table in ("schedule_shifts", "schedule_shift_templates"):
        op.execute(
            f"""
            INSERT INTO schedule_jobs (company_id, location_id, name, notes)
            SELECT DISTINCT ON (r.company_id, r.location_id, lower(btrim(r.role)))
                   r.company_id, r.location_id, btrim(r.role), '{DERIVED_NOTE}'
            FROM {table} r
            WHERE r.role IS NOT NULL AND btrim(r.role) <> ''
              AND NOT EXISTS (
                  SELECT 1 FROM schedule_jobs j
                  WHERE j.company_id = r.company_id
                    AND lower(j.name) = lower(btrim(r.role))
                    AND (j.location_id IS NULL OR j.location_id = r.location_id)
              )
            ORDER BY r.company_id, r.location_id, lower(btrim(r.role)), btrim(r.role)
            """
        )

    # 2. Safety net: a company that schedules but has labelled nothing still
    #    needs something to pick. One company-wide job, available everywhere.
    op.execute(
        f"""
        INSERT INTO schedule_jobs (company_id, location_id, name, notes)
        SELECT DISTINCT s.company_id, NULL::uuid, 'General', '{DERIVED_NOTE}'
        FROM schedule_shifts s
        WHERE NOT EXISTS (
            SELECT 1 FROM schedule_jobs j WHERE j.company_id = s.company_id
        )
        """
    )

    # 3. Point every unlinked row at the job its own label became, and
    #    normalize the label to that job's name — the route now writes the
    #    job's name as the role, so the two must not disagree from day one.
    #    Location-scoped jobs win over company-wide ones, which is the same
    #    precedence shift_writes.resolve_job_by_name applies at runtime.
    for table in ("schedule_shifts", "schedule_shift_templates"):
        op.execute(
            f"""
            CREATE TEMP TABLE job_backfill_plan ON COMMIT DROP AS
            SELECT r.id AS row_id, j.id AS job_id, j.name AS job_name
            FROM {table} r
            JOIN LATERAL (
                SELECT j.id, j.name
                FROM schedule_jobs j
                WHERE j.company_id = r.company_id
                  AND lower(j.name) = lower(btrim(r.role))
                  AND (j.location_id IS NULL OR j.location_id = r.location_id)
                ORDER BY (j.location_id IS NULL), j.created_at, j.id
                LIMIT 1
            ) j ON TRUE
            WHERE r.job_id IS NULL
              AND r.role IS NOT NULL AND btrim(r.role) <> ''
            """
        )
        op.execute(
            f"""
            UPDATE {table} r
            SET job_id = p.job_id, role = p.job_name
            FROM job_backfill_plan p
            WHERE p.row_id = r.id
            """
        )
        op.execute("DROP TABLE job_backfill_plan")


def downgrade() -> None:
    # Only the jobs this migration minted, and only while nobody has qualified
    # anyone on them — a job with a roster is a decision somebody made, not
    # backfilled data. The FK is ON DELETE SET NULL, so the rows pointing at a
    # deleted job go back to job_id NULL on their own; the role text they
    # carry is the label they had before this ran.
    op.execute(
        f"""
        DELETE FROM schedule_jobs j
        WHERE j.notes = '{DERIVED_NOTE}'
          AND NOT EXISTS (
              SELECT 1 FROM schedule_job_employees je WHERE je.job_id = j.id
          )
        """
    )
