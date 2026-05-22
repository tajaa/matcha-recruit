"""unify heads: matcha-work task_type/elements + onboarding-gap merge

Revision ID: 50268295866e
Revises: e58bd28fdfb1, zzzzbi2c3d4e5
Create Date: 2026-05-21 17:20:48.526568

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '50268295866e'
down_revision: Union[str, Sequence[str], None] = ('e58bd28fdfb1', 'zzzzbi2c3d4e5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
