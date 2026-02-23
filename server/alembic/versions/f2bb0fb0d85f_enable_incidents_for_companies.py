"""enable_incidents_for_companies

Revision ID: f2bb0fb0d85f
Revises: m3n4o5p6q7r8
Create Date: 2026-02-04 16:16:56.252060

"""
from typing import Sequence, Union

from alembic import op

revision = 'f2bb0fb0d85f'
down_revision = 'm3n4o5p6q7r8'
branch_labels = None
depends_on = None
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2bb0fb0d85f'
down_revision: Union[str, Sequence[str], None] = 'm3n4o5p6q7r8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enable incidents feature for all approved companies."""
    op.execute("""
        UPDATE companies
        SET enabled_features = jsonb_set(
            COALESCE(enabled_features, '{}'::jsonb),
            '{incidents}',
            'true'
        )
        WHERE status = 'approved' OR status IS NULL
    """)


def downgrade() -> None:
    """Remove incidents feature from companies."""
    op.execute("""
        UPDATE companies
        SET enabled_features = enabled_features - 'incidents'
        WHERE status = 'approved' OR status IS NULL
    """)
