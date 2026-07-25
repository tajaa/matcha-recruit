"""Link training to scheduling — role-triggered auto-assign + training-as-shift.

Adds:
- training_assignment_rules: `roles` TEXT[] (role matcher for the new
  `scheduled_role` trigger) + widened `trigger` CHECK.
- training_records: widened `source_type` CHECK (adds 'schedule' — a record
  created by a scheduled-role rule or a training-kind shift assignment).
- schedule_shifts: `kind` ('work'/'training') + `training_requirement_id` —
  a training-kind shift is tied to the requirement it satisfies; assigning
  an employee to it creates/accelerates their training record.

Revision ID: trainsched01
Revises: trainint01
Create Date: 2026-07-25
"""

from alembic import op


revision = "trainsched01"
down_revision = "trainint01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- training_assignment_rules: role matcher + scheduled_role trigger ----
    op.execute(
        "ALTER TABLE training_assignment_rules ADD COLUMN IF NOT EXISTS roles TEXT[]"
    )
    op.execute(
        """
        DO $$
        DECLARE
            con_name text;
        BEGIN
            SELECT con.conname INTO con_name
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            WHERE rel.relname = 'training_assignment_rules'
              AND con.contype = 'c'
              AND pg_get_constraintdef(con.oid) LIKE '%trigger%';

            IF con_name IS NOT NULL THEN
                EXECUTE format('ALTER TABLE training_assignment_rules DROP CONSTRAINT %I', con_name);
            END IF;

            ALTER TABLE training_assignment_rules
                ADD CONSTRAINT chk_training_assignment_rules_trigger
                CHECK (trigger IN ('new_hire', 'incident', 'schedule', 'scheduled_role'));
        END $$;
        """
    )

    # -- training_records: widen source_type to include 'schedule' -----------
    op.execute(
        "ALTER TABLE training_records DROP CONSTRAINT IF EXISTS chk_training_records_source_type"
    )
    op.execute(
        """
        ALTER TABLE training_records
            ADD CONSTRAINT chk_training_records_source_type
            CHECK (source_type IN
                ('manual', 'bulk_assign', 'rule', 'new_hire', 'incident',
                 'discipline', 'credential', 'cadence', 'schedule'))
        """
    )

    # -- schedule_shifts: training-kind shifts --------------------------------
    op.execute(
        """
        ALTER TABLE schedule_shifts
            ADD COLUMN IF NOT EXISTS kind VARCHAR(20) NOT NULL DEFAULT 'work',
            ADD COLUMN IF NOT EXISTS training_requirement_id UUID
                REFERENCES training_requirements(id) ON DELETE SET NULL
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'chk_schedule_shifts_kind'
            ) THEN
                ALTER TABLE schedule_shifts
                    ADD CONSTRAINT chk_schedule_shifts_kind
                    CHECK (kind IN ('work', 'training'));
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE schedule_shifts DROP CONSTRAINT IF EXISTS chk_schedule_shifts_kind")
    op.execute(
        """
        ALTER TABLE schedule_shifts
            DROP COLUMN IF EXISTS kind,
            DROP COLUMN IF EXISTS training_requirement_id
        """
    )

    op.execute(
        "ALTER TABLE training_records DROP CONSTRAINT IF EXISTS chk_training_records_source_type"
    )
    op.execute(
        """
        ALTER TABLE training_records
            ADD CONSTRAINT chk_training_records_source_type
            CHECK (source_type IN
                ('manual', 'bulk_assign', 'rule', 'new_hire', 'incident',
                 'discipline', 'credential', 'cadence'))
        """
    )

    op.execute(
        """
        DO $$
        DECLARE
            con_name text;
        BEGIN
            SELECT con.conname INTO con_name
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            WHERE rel.relname = 'training_assignment_rules'
              AND con.contype = 'c'
              AND pg_get_constraintdef(con.oid) LIKE '%trigger%';

            IF con_name IS NOT NULL THEN
                EXECUTE format('ALTER TABLE training_assignment_rules DROP CONSTRAINT %I', con_name);
            END IF;

            ALTER TABLE training_assignment_rules
                ADD CONSTRAINT chk_training_assignment_rules_trigger
                CHECK (trigger IN ('new_hire', 'incident', 'schedule'));
        END $$;
        """
    )
    op.execute("ALTER TABLE training_assignment_rules DROP COLUMN IF EXISTS roles")
