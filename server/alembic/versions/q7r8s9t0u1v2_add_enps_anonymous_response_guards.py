"""add enps anonymous response guards

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
Create Date: 2026-02-09
"""
from alembic import op
import sqlalchemy as sa

revision = "q7r8s9t0u1v2"
down_revision = "p6q7r8s9t0u1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "enps_anonymous_response_guards",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("survey_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["survey_id"], ["enps_surveys.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("survey_id", "employee_id", name="unique_enps_anonymous_survey_employee"),
    )
    op.create_index(
        "idx_enps_anonymous_guards_survey",
        "enps_anonymous_response_guards",
        ["survey_id"],
    )
    op.create_index(
        "idx_enps_anonymous_guards_employee",
        "enps_anonymous_response_guards",
        ["employee_id"],
    )


def downgrade():
    op.drop_index("idx_enps_anonymous_guards_employee", table_name="enps_anonymous_response_guards")
    op.drop_index("idx_enps_anonymous_guards_survey", table_name="enps_anonymous_response_guards")
    op.drop_table("enps_anonymous_response_guards")
