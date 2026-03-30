"""Add 'individual' role and is_personal flag on companies.

Revision ID: zw1x2y3z4a5b
Revises: zv0w1x2y3z4a
Create Date: 2026-03-30
"""
from alembic import op

revision = "zw1x2y3z4a5b"
down_revision = "zv0w1x2y3z4a"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
        ALTER TABLE users ADD CONSTRAINT users_role_check
            CHECK (role IN ('admin', 'client', 'candidate', 'employee', 'broker', 'creator', 'agency', 'gumfit_admin', 'individual'));
    """)
    op.execute("""
        ALTER TABLE companies ADD COLUMN IF NOT EXISTS is_personal BOOLEAN DEFAULT false;
    """)


def downgrade():
    op.execute("""
        ALTER TABLE companies DROP COLUMN IF EXISTS is_personal;
    """)
    op.execute("""
        ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
        ALTER TABLE users ADD CONSTRAINT users_role_check
            CHECK (role IN ('admin', 'client', 'candidate', 'employee', 'broker', 'creator', 'agency', 'gumfit_admin'));
    """)
