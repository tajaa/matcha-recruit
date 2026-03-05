"""merge_heads_for_rls

Revision ID: db9963457338
Revises: 611ea22c50f8, f7g8h9i0j1k2
Create Date: 2026-03-04 19:07:28.681132

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'db9963457338'
down_revision: Union[str, Sequence[str], None] = ('611ea22c50f8', 'f7g8h9i0j1k2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
