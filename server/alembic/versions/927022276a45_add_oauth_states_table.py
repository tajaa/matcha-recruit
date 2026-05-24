"""add_oauth_states_table

Revision ID: 927022276a45
Revises: zzzzdi4e5f6g7
Create Date: 2026-05-24 15:52:46.699493

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '927022276a45'
down_revision: Union[str, Sequence[str], None] = 'zzzzdi4e5f6g7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS oauth_states (
            state TEXT PRIMARY KEY,
            company_id UUID NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_oauth_states_company_id ON oauth_states(company_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_oauth_states_created_at ON oauth_states(created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS oauth_states")
