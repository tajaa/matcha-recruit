"""add employee_onboarding_drafts table

Revision ID: f4e5d6c7b8a9
Revises: e2f3a4b5c6d7
Create Date: 2026-02-23 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4e5d6c7b8a9'
down_revision: Union[str, Sequence[str], None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE employee_onboarding_drafts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            draft_state JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(company_id, user_id)
        )
    """)
    op.execute("""
        CREATE INDEX idx_employee_onboarding_drafts_company_user
        ON employee_onboarding_drafts(company_id, user_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_employee_onboarding_drafts_company_user")
    op.execute("DROP TABLE IF EXISTS employee_onboarding_drafts")
