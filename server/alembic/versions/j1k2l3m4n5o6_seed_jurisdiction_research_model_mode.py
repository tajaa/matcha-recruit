"""seed jurisdiction_research_model_mode platform setting

Revision ID: j1k2l3m4n5o6
Revises: i5j6k7l8m9n1
Create Date: 2026-02-24 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'j1k2l3m4n5o6'
down_revision: Union[str, Sequence[str], None] = 'i5j6k7l8m9n1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Seed jurisdiction_research_model_mode setting."""
    op.execute("""
        INSERT INTO platform_settings (key, value, updated_at)
        VALUES ('jurisdiction_research_model_mode', '"light"', NOW())
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade() -> None:
    """Remove jurisdiction_research_model_mode setting."""
    op.execute("DELETE FROM platform_settings WHERE key = 'jurisdiction_research_model_mode'")
