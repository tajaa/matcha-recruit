"""Heal mw_threads.task_type column + normalize its CHECK constraint.

No prior migration ever ran `ALTER TABLE mw_threads ADD COLUMN task_type` — the
column only appears inside `CREATE TABLE IF NOT EXISTS mw_threads`, which skips a
pre-existing table. DBs whose mw_threads predates task_type therefore lack the
column, and the constraint migrations (d6e7f8a9b0c1 / h9i0j1k2l3m4) assume it
exists. This adds it idempotently and sets the CHECK to the full value set.

Revision ID: zzzzbi2c3d4e5
Revises: zzzzah1b2c3d4
Create Date: 2026-05-21
"""
from alembic import op

revision = "zzzzbi2c3d4e5"
down_revision = "zzzzah1b2c3d4"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE mw_threads ADD COLUMN IF NOT EXISTS task_type "
        "VARCHAR(40) NOT NULL DEFAULT 'offer_letter'"
    )
    # Normalize the CHECK to the full value set regardless of which constraint
    # migrations already ran. Drop any existing task_type check, then re-add.
    op.execute("""
        DO $$
        DECLARE c RECORD;
        BEGIN
            FOR c IN SELECT conname FROM pg_constraint
                     WHERE conrelid = 'mw_threads'::regclass AND contype = 'c'
                       AND pg_get_constraintdef(oid) ILIKE '%task_type%'
            LOOP EXECUTE format('ALTER TABLE mw_threads DROP CONSTRAINT %I', c.conname); END LOOP;
            ALTER TABLE mw_threads ADD CONSTRAINT mw_threads_task_type_check
                CHECK (task_type IN ('offer_letter','review','workbook'));
        END $$;
    """)


def downgrade():
    # Additive heal; nothing to reverse safely.
    pass
