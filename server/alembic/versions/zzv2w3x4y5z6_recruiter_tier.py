"""Add users.recruiter_until for the Matcha Recruiter subscription tier.

Recruiter tier gates the ability to read parsed resume fields on channel
job applications. Webhook sets recruiter_until on checkout completion.

Revision ID: zzv2w3x4y5z6
Revises: zzu1v2w3x4y5
Create Date: 2026-04-15
"""
from alembic import op

revision = "zzv2w3x4y5z6"
down_revision = "zzu1v2w3x4y5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE users
          ADD COLUMN IF NOT EXISTS recruiter_until timestamptz
    """)
    # Partial predicates must be IMMUTABLE — can't use NOW(). Plain
    # partial index on NOT NULL is enough to keep lookups cheap; the
    # > NOW() check happens at read time.
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_recruiter_until
        ON users(recruiter_until) WHERE recruiter_until IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_recruiter_until")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS recruiter_until")
