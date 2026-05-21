"""merge onboarding-gap and project-elements heads

Revision ID: e58bd28fdfb1
Revises: zzzz_b04_onb_gap, zzzzah1b2c3d4
Create Date: 2026-05-21 12:18:14.110935

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e58bd28fdfb1'
down_revision: Union[str, Sequence[str], None] = ('zzzz_b04_onb_gap', 'zzzzah1b2c3d4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
