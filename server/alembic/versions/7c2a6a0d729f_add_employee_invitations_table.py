"""add_employee_invitations_table

Revision ID: 7c2a6a0d729f
Revises: 6e4ad940b98b
Create Date: 2026-01-13 22:03:11.134923

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c2a6a0d729f'
down_revision: Union[str, Sequence[str], None] = '6e4ad940b98b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create employee_invitations table for tracking onboarding invitations
    op.execute("""
        CREATE TABLE IF NOT EXISTS employee_invitations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            invited_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token VARCHAR(64) NOT NULL UNIQUE,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            expires_at TIMESTAMP NOT NULL,
            accepted_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT check_invitation_status CHECK (
                status IN ('pending', 'accepted', 'expired', 'cancelled')
            )
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_employee_invitations_token ON employee_invitations(token)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_employee_invitations_employee_id ON employee_invitations(employee_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_employee_invitations_org_id ON employee_invitations(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_employee_invitations_status ON employee_invitations(status)")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS employee_invitations CASCADE")
