"""Training provenance + assignment rules — connect training to the events
that should drive it (incidents, discipline, new hires, rule-based cadence)
instead of only manual admin action.

Adds:
- training_records: source_type / source_ref / source_note (why a record
  exists — mirrors the `risk_action_items.source_type`/`source_ref`
  convention) + waived_at/waived_by/waiver_reason (credential-requirement
  parity; `status='waived'` already existed but nothing recorded who/why).
- training_assignment_rules: replaces the CA/SB-1343 hardcode in
  workers/tasks/training_cadence.py with a per-company, per-trigger rule
  table (new_hire / incident / schedule).
- ir_corrective_actions.action_type: widen the CHECK to allow 'training',
  add training_requirement_id so a CAPA can point at what it assigned.
- progressive_discipline.remedial_requirement_id: the discipline issuance
  path can attach a remedial training requirement.

Revision ID: trainint01
Revises: reqcomp02
Create Date: 2026-07-25
"""

from alembic import op


revision = "trainint01"
down_revision = "reqcomp02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- training_records provenance -------------------------------------
    op.execute(
        """
        ALTER TABLE training_records
            ADD COLUMN IF NOT EXISTS source_type VARCHAR(30) NOT NULL DEFAULT 'manual',
            ADD COLUMN IF NOT EXISTS source_ref UUID,
            ADD COLUMN IF NOT EXISTS source_note TEXT,
            ADD COLUMN IF NOT EXISTS waived_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS waived_by UUID REFERENCES users(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS waiver_reason TEXT
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'chk_training_records_source_type'
            ) THEN
                ALTER TABLE training_records
                    ADD CONSTRAINT chk_training_records_source_type
                    CHECK (source_type IN
                        ('manual', 'bulk_assign', 'rule', 'new_hire', 'incident',
                         'discipline', 'credential', 'cadence'));
            END IF;
        END $$;
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_training_records_source "
        "ON training_records(source_type, source_ref)"
    )

    # -- training_assignment_rules -----------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS training_assignment_rules (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            requirement_id UUID NOT NULL REFERENCES training_requirements(id) ON DELETE CASCADE,
            trigger VARCHAR(20) NOT NULL
                CHECK (trigger IN ('new_hire', 'incident', 'schedule')),
            work_states TEXT[],
            applies_to VARCHAR(20) NOT NULL DEFAULT 'all'
                CHECK (applies_to IN ('all', 'supervisor', 'nonsupervisor')),
            departments TEXT[],
            due_days INTEGER,
            incident_types TEXT[],
            min_severity VARCHAR(20),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_training_assignment_rules_company_trigger "
        "ON training_assignment_rules(company_id, trigger) WHERE is_active"
    )

    # -- ir_corrective_actions: allow a 'training' CAPA ---------------------
    op.execute(
        """
        ALTER TABLE ir_corrective_actions
            ADD COLUMN IF NOT EXISTS training_requirement_id UUID
                REFERENCES training_requirements(id) ON DELETE SET NULL
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
            WHERE rel.relname = 'ir_corrective_actions'
              AND con.contype = 'c'
              AND pg_get_constraintdef(con.oid) LIKE '%action_type%';

            IF con_name IS NOT NULL THEN
                EXECUTE format('ALTER TABLE ir_corrective_actions DROP CONSTRAINT %I', con_name);
            END IF;

            ALTER TABLE ir_corrective_actions
                ADD CONSTRAINT chk_ir_corrective_actions_action_type
                CHECK (action_type IN ('corrective', 'preventive', 'training'));
        END $$;
        """
    )

    # -- progressive_discipline: optional remedial training -----------------
    op.execute(
        """
        ALTER TABLE progressive_discipline
            ADD COLUMN IF NOT EXISTS remedial_requirement_id UUID
                REFERENCES training_requirements(id) ON DELETE SET NULL
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE progressive_discipline DROP COLUMN IF EXISTS remedial_requirement_id"
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
            WHERE rel.relname = 'ir_corrective_actions'
              AND con.contype = 'c'
              AND pg_get_constraintdef(con.oid) LIKE '%action_type%';

            IF con_name IS NOT NULL THEN
                EXECUTE format('ALTER TABLE ir_corrective_actions DROP CONSTRAINT %I', con_name);
            END IF;

            ALTER TABLE ir_corrective_actions
                ADD CONSTRAINT chk_ir_corrective_actions_action_type
                CHECK (action_type IN ('corrective', 'preventive'));
        END $$;
        """
    )
    op.execute(
        "ALTER TABLE ir_corrective_actions DROP COLUMN IF EXISTS training_requirement_id"
    )
    op.execute("DROP TABLE IF EXISTS training_assignment_rules")
    op.execute(
        "ALTER TABLE training_records DROP CONSTRAINT IF EXISTS chk_training_records_source_type"
    )
    op.execute(
        """
        ALTER TABLE training_records
            DROP COLUMN IF EXISTS source_type,
            DROP COLUMN IF EXISTS source_ref,
            DROP COLUMN IF EXISTS source_note,
            DROP COLUMN IF EXISTS waived_at,
            DROP COLUMN IF EXISTS waived_by,
            DROP COLUMN IF EXISTS waiver_reason
        """
    )
