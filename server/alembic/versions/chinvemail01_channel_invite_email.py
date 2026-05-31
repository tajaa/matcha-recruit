"""Add channel_invites.email — targeted email invites for non-users.

Channel owners/moderators can now invite people who don't have an account
yet by email. Each such invite gets a `channel_invites` row with `email`
set (vs. NULL for the existing shareable-link invites). The email binds the
invite to a recipient: the signup-and-join accept flow prefills/locks the
address and the invite is single-use (max_uses=1 set by the route, not here).

Nullable + idempotent so it composes with the existing link-invite rows and
re-running against a partially-upgraded DB is safe.

Revision ID: chinvemail01
Revises: jrimplsteps01
Create Date: 2026-05-31
"""
from alembic import op


revision = "chinvemail01"
down_revision = "jrimplsteps01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE channel_invites ADD COLUMN IF NOT EXISTS email text")
    # Partial index: targeted email invites are looked up by (channel_id, email)
    # to dedupe re-invites; link invites (email IS NULL) are excluded.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_channel_invites_channel_email
        ON channel_invites (channel_id, lower(email))
        WHERE email IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_channel_invites_channel_email")
    op.execute("ALTER TABLE channel_invites DROP COLUMN IF EXISTS email")
