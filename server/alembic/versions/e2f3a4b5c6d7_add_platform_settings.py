"""add platform_settings table

Revision ID: e2f3a4b5c6d7
Revises: cd42f318ad33
Create Date: 2026-02-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, Sequence[str], None] = 'cd42f318ad33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create platform_settings table with seed data."""
    op.execute("""
        CREATE TABLE platform_settings (
            key VARCHAR(100) PRIMARY KEY,
            value JSONB NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        INSERT INTO platform_settings (key, value)
        VALUES ('visible_features', '["offer_letters","client_management","blog","policies","handbooks","er_copilot","onboarding","employees"]')
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade() -> None:
    """Drop platform_settings table."""
    op.execute("DROP TABLE IF EXISTS platform_settings")
