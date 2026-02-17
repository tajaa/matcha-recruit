"""add personal_email to employees for onboarding contact vs work identity

Revision ID: y5z6a7b8c9d
Revises: x4y5z6a7b8c
Create Date: 2026-02-17
"""

from alembic import op


revision = "y5z6a7b8c9d"
down_revision = "x4y5z6a7b8c"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('employees') IS NOT NULL THEN
                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'employees'
                      AND column_name = 'personal_email'
                ) THEN
                    ALTER TABLE employees ADD COLUMN personal_email VARCHAR(255);
                END IF;
            END IF;
        END$$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('employees') IS NOT NULL THEN
                EXECUTE 'CREATE INDEX IF NOT EXISTS idx_employees_personal_email ON employees(personal_email)';
            END IF;
        END$$;
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_employees_personal_email")
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('employees') IS NOT NULL THEN
                ALTER TABLE employees DROP COLUMN IF EXISTS personal_email;
            END IF;
        END$$;
        """
    )
