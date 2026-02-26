"""Add work_location_id FK to employees table (Phase 2 compliance impact prep)

Adds a nullable FK from employees.work_location_id → business_locations.id so
that Phase 2 of the compliance impact dashboard can map employees to exact
locations rather than using the state-estimate heuristic.

The column is intentionally nullable (no default, no backfill) so existing rows
keep working. The impact logic in compliance_service.get_compliance_dashboard()
will prefer exact FK when populated and fall back to state_estimate otherwise.

Revision ID: m4n5o6p7q8r9
Revises: l2m3n4o5p6q7
Create Date: 2026-02-26

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "m4n5o6p7q8r9"
down_revision: Union[str, None] = "l2m3n4o5p6q7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable FK column — no backfill, no default.
    # Populate via employee create/edit/import flows in Phase 2.
    op.add_column(
        "employees",
        sa.Column(
            "work_location_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("business_locations.id", ondelete="SET NULL"),
            nullable=True,
            comment="FK to business_locations; drives exact compliance impact mapping (Phase 2). "
            "NULL = fall back to state-estimate via work_state.",
        ),
    )
    op.create_index(
        "idx_employees_work_location_id",
        "employees",
        ["work_location_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_employees_work_location_id", table_name="employees")
    op.drop_column("employees", "work_location_id")
