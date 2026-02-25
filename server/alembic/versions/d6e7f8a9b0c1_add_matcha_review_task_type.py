"""allow review task type for matcha work

Revision ID: d6e7f8a9b0c1
Revises: c4d5e6f7a8b9
Create Date: 2026-02-25
"""

from alembic import op


revision = "d6e7f8a9b0c1"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        DO $$
        DECLARE
            c RECORD;
        BEGIN
            FOR c IN
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = 'mw_threads'::regclass
                  AND contype = 'c'
                  AND pg_get_constraintdef(oid) ILIKE '%task_type%'
            LOOP
                EXECUTE format('ALTER TABLE mw_threads DROP CONSTRAINT %I', c.conname);
            END LOOP;

            ALTER TABLE mw_threads
            ADD CONSTRAINT mw_threads_task_type_check
            CHECK (task_type IN ('offer_letter', 'review'));
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        DECLARE
            c RECORD;
        BEGIN
            FOR c IN
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = 'mw_elements'::regclass
                  AND contype = 'c'
                  AND pg_get_constraintdef(oid) ILIKE '%element_type%'
            LOOP
                EXECUTE format('ALTER TABLE mw_elements DROP CONSTRAINT %I', c.conname);
            END LOOP;

            ALTER TABLE mw_elements
            ADD CONSTRAINT mw_elements_element_type_check
            CHECK (element_type IN ('offer_letter', 'review'));
        END $$;
        """
    )


def downgrade():
    op.execute(
        """
        UPDATE mw_threads
        SET task_type = 'offer_letter'
        WHERE task_type = 'review'
        """
    )
    op.execute(
        """
        UPDATE mw_elements
        SET element_type = 'offer_letter'
        WHERE element_type = 'review'
        """
    )

    op.execute(
        """
        ALTER TABLE mw_threads DROP CONSTRAINT IF EXISTS mw_threads_task_type_check;
        ALTER TABLE mw_threads
        ADD CONSTRAINT mw_threads_task_type_check
        CHECK (task_type IN ('offer_letter'));
        """
    )
    op.execute(
        """
        ALTER TABLE mw_elements DROP CONSTRAINT IF EXISTS mw_elements_element_type_check;
        ALTER TABLE mw_elements
        ADD CONSTRAINT mw_elements_element_type_check
        CHECK (element_type IN ('offer_letter'));
        """
    )
