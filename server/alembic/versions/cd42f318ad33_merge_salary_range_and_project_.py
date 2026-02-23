"""merge salary range and project applications heads

Revision ID: cd42f318ad33
Revises: c0d1e2f3a4b5, c9d0e1f2a3b4
Create Date: 2026-02-22 20:07:59.887256

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cd42f318ad33'
down_revision: Union[str, Sequence[str], None] = ('c0d1e2f3a4b5', 'c9d0e1f2a3b4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
