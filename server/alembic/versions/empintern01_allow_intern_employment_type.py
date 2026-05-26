"""allow 'intern' in employees.employment_type CHECK

Revision ID: empintern01
Revises: mwsub0001
Create Date: 2026-05-26

The live employees table carries an older inline CHECK
(employees_employment_type_check) allowing only
('full_time','part_time','contractor') — created pre-Alembic and never
reconciled with the CREATE TABLE migration (7c1de748641e), which already
intends 'intern'. The Finch HRIS importer emits employment_type='intern'
for workers whose Finch employment.subtype is "intern"; those rows were
rejected with a CheckViolationError (2/20 on the first Sea Cafe import).

'intern' is already a first-class concept elsewhere (risk_assessment_service
counts ('contractor','intern') as contingent workforce; offer-letter
multipliers), so this reconciles the constraint to the intended set rather
than collapsing interns into another bucket.

Name-tolerant: drops whatever CHECK constraint currently guards
employees.employment_type (the name may differ between dev and prod) and
re-adds the canonical 4-value constraint. Additive for existing rows.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "empintern01"
down_revision: Union[str, Sequence[str], None] = "mwsub0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE c text;
        BEGIN
            -- Drop any existing CHECK on employees referencing employment_type
            -- (live name is employees_employment_type_check; tolerate drift).
            FOR c IN
                SELECT con.conname
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                WHERE rel.relname = 'employees'
                  AND con.contype = 'c'
                  AND pg_get_constraintdef(con.oid) ILIKE '%employment_type%'
            LOOP
                EXECUTE format('ALTER TABLE employees DROP CONSTRAINT %I', c);
            END LOOP;

            ALTER TABLE employees
                ADD CONSTRAINT employees_employment_type_check
                CHECK (employment_type IN ('full_time', 'part_time', 'contractor', 'intern'));
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE employees DROP CONSTRAINT IF EXISTS employees_employment_type_check;
        ALTER TABLE employees
            ADD CONSTRAINT employees_employment_type_check
            CHECK (employment_type IN ('full_time', 'part_time', 'contractor'));
        """
    )
