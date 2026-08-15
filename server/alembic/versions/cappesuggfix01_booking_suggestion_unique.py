"""Repair missing UNIQUE (site_id, client_email) on Cappe suggestion tables.

cappeaiaccess01 declared these inline in CREATE TABLE IF NOT EXISTS, so any DB
whose tables predated the final version of that migration never got them, and
the ON CONFLICT (site_id, client_email) upserts fail with 42P10.

Revision ID: cappesuggfix01
Revises: cappeaiaccess01
"""
from alembic import op

revision = "cappesuggfix01"
down_revision = "cappeaiaccess01"
branch_labels = None
depends_on = None

_TABLES = ("cappe_booking_suggestion_links", "cappe_booking_suggestion_sessions")


def upgrade() -> None:
    for table in _TABLES:
        # Set-based dedupe so ADD CONSTRAINT cannot fail mid-migration.
        # Rows are 15/30-minute capabilities, so this is near-certainly a no-op.
        op.execute(
            f"""
            DELETE FROM {table} t
            USING (
                SELECT ctid, ROW_NUMBER() OVER (
                    PARTITION BY site_id, client_email
                    ORDER BY created_at DESC, ctid DESC
                ) AS rn
                FROM {table}
            ) ranked
            WHERE t.ctid = ranked.ctid AND ranked.rn > 1
            """
        )
        op.execute(
            f"""
            DO $$ BEGIN
                ALTER TABLE {table}
                    ADD CONSTRAINT {table}_site_id_client_email_key
                    UNIQUE (site_id, client_email);
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$
            """
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(
            f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS "
            f"{table}_site_id_client_email_key"
        )
