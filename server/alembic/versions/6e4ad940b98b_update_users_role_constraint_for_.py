"""update_users_role_constraint_for_employee

Revision ID: 6e4ad940b98b
Revises: 7c1de748641e
Create Date: 2026-01-13 21:50:48.784622

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6e4ad940b98b'
down_revision: Union[str, Sequence[str], None] = '7c1de748641e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Update users table role constraint to include 'employee'
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'users_role_check'
            ) THEN
                ALTER TABLE users DROP CONSTRAINT users_role_check;
                ALTER TABLE users ADD CONSTRAINT users_role_check
                    CHECK (role IN ('admin', 'client', 'candidate', 'employee'));
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Revert users table role constraint to exclude 'employee'
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'users_role_check'
            ) THEN
                ALTER TABLE users DROP CONSTRAINT users_role_check;
                ALTER TABLE users ADD CONSTRAINT users_role_check
                    CHECK (role IN ('admin', 'client', 'candidate'));
            END IF;
        END $$;
    """)
