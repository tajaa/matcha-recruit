"""add_gusto_webhook_tokens_table

Revision ID: gustowh0001
Revises: 927022276a45
Create Date: 2026-05-24 16:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'gustowh0001'
down_revision: Union[str, Sequence[str], None] = '927022276a45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS gusto_webhook_tokens (
            id BIGSERIAL PRIMARY KEY,
            verification_token TEXT NOT NULL,
            gusto_company_uuid TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_gusto_webhook_tokens_created_at ON gusto_webhook_tokens(created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gusto_webhook_tokens")
