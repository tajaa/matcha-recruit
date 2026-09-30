"""Matcha Drive: per-user Google Drive connection (read-only import).

users.gdrive_token JSONB — encrypted access/refresh tokens (secret_crypto),
expiry, and the connected Google account email. Separate from
users.gmail_token on purpose: that column is Gmail-specific (its refresh
path validates against a Gmail endpoint) and carries a different scope set.

Revision ID: mdrive02
Revises: mdrive01
Create Date: 2026-09-29
"""

from alembic import op


revision = "mdrive02"
down_revision = "mdrive01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS gdrive_token JSONB")


def downgrade():
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS gdrive_token")
