"""add users.tokens_valid_after for session revocation

Enables real logout / session revocation. Access + refresh tokens now carry an
`iat`; any token whose iat predates `users.tokens_valid_after` is rejected.
Logout and password change/reset bump this timestamp, invalidating all prior
sessions for that user (the old /logout was a no-op and refresh tokens were
non-revocable for their full 30-day life).

Revision ID: authsess01
Revises: mwjf0001
Create Date: 2026-06-06
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "authsess01"
down_revision = "mwjf0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS tokens_valid_after TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS tokens_valid_after")
