"""merge heads

Revision ID: 2c12cf3aaab4
Revises: t5u6v7w8x9y0, zu9v0w1x2y3z
Create Date: 2026-03-25 22:19:03.119653

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2c12cf3aaab4'
down_revision: Union[str, Sequence[str], None] = ('t5u6v7w8x9y0', 'zu9v0w1x2y3z')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
