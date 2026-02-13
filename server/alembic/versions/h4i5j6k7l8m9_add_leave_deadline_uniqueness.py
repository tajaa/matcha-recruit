"""add_leave_deadline_uniqueness

Revision ID: h4i5j6k7l8m9
Revises: g3h4i5j6k7l8
Create Date: 2026-02-13

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "h4i5j6k7l8m9"
down_revision: Union[str, Sequence[str]] = "g3h4i5j6k7l8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Deduplicate leave deadlines and enforce one row per type per leave request."""
    op.execute(
        """
        DELETE FROM leave_deadlines a
        USING leave_deadlines b
        WHERE a.id > b.id
          AND a.leave_request_id = b.leave_request_id
          AND a.deadline_type = b.deadline_type
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_leave_deadlines_leave_request_type
            ON leave_deadlines(leave_request_id, deadline_type)
        """
    )


def downgrade() -> None:
    """Remove leave deadline uniqueness index."""
    op.execute("DROP INDEX IF EXISTS uq_leave_deadlines_leave_request_type")
