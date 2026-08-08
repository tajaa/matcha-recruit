"""tellus_app_14 — Google sign-in: nullable password_hash + google_sub identity.

tellus_accounts.password_hash has been NOT NULL since tellus_app_01, and every
insert has supplied one. A Google-only account has no password, so the column
must become nullable — and `password_hash IS NULL` becomes the marker that
distinguishes a Google-only account from one that also has a password
(deliberately NOT a random unusable hash, unlike matcha core's /auth/google,
because that would make the marker useless for the login() guard added in the
same PR).

The CHECK constraint keeps "every account has at least one way in" true —
password_hash and google_sub can't both be null.

Revision ID: tellus_app_14
Revises: tellus_app_13
"""
from alembic import op

revision = "tellus_app_14"
down_revision = "tellus_app_13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE tellus_accounts ADD COLUMN IF NOT EXISTS google_sub TEXT")
    op.execute("ALTER TABLE tellus_accounts ALTER COLUMN password_hash DROP NOT NULL")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_accounts_google_sub "
        "ON tellus_accounts (google_sub) WHERE google_sub IS NOT NULL"
    )
    op.execute(
        """DO $$ BEGIN
            ALTER TABLE tellus_accounts ADD CONSTRAINT ck_tellus_accounts_credential
                CHECK (password_hash IS NOT NULL OR google_sub IS NOT NULL);
        EXCEPTION WHEN duplicate_object THEN NULL; END $$"""
    )


def downgrade() -> None:
    # Backfill first — re-adding NOT NULL on a column with Google-only (NULL)
    # rows would fail. gen_random_uuid() as a stand-in password_hash is
    # unusable for login (never matches bcrypt), same as it would have been
    # had upgrade() chosen that approach instead of nullable + CHECK.
    op.execute(
        "UPDATE tellus_accounts SET password_hash = gen_random_uuid()::text "
        "WHERE password_hash IS NULL"
    )
    op.execute("ALTER TABLE tellus_accounts DROP CONSTRAINT IF EXISTS ck_tellus_accounts_credential")
    op.execute("DROP INDEX IF EXISTS ux_tellus_accounts_google_sub")
    op.execute("ALTER TABLE tellus_accounts ALTER COLUMN password_hash SET NOT NULL")
    op.execute("ALTER TABLE tellus_accounts DROP COLUMN IF EXISTS google_sub")
