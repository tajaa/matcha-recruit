"""seed matcha_work_model_mode platform setting

Revision ID: i5j6k7l8m9n1
Revises: h9i0j1k2l3m4
Create Date: 2026-02-24 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i5j6k7l8m9n1'
down_revision: Union[str, Sequence[str], None] = 'h9i0j1k2l3m4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Seed matcha_work_model_mode setting."""
    op.execute("""
        INSERT INTO platform_settings (key, value, updated_at)
        VALUES ('matcha_work_model_mode', '"light"', NOW())
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade() -> None:
    """Remove matcha_work_model_mode setting (optional, but keep for completeness)."""
    op.execute("DELETE FROM platform_settings WHERE key = 'matcha_work_model_mode'")
