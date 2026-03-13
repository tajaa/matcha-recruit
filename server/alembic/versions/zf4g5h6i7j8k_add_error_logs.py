"""add error_logs table

Revision ID: zf4g5h6i7j8k
Revises: ze3f4g5h6i7j
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa

revision = "zf4g5h6i7j8k"
down_revision = "ze3f4g5h6i7j"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "error_logs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("status_code", sa.Integer, nullable=False),
        sa.Column("error_type", sa.String(255), nullable=False),
        sa.Column("error_message", sa.Text, nullable=False),
        sa.Column("traceback", sa.Text, nullable=True),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_role", sa.String(20), nullable=True),
        sa.Column("company_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("request_body", sa.Text, nullable=True),
        sa.Column("query_params", sa.Text, nullable=True),
    )
    op.create_index("ix_error_logs_timestamp", "error_logs", [sa.text("timestamp DESC")])
    op.create_index("ix_error_logs_path", "error_logs", ["path"])


def downgrade():
    op.drop_index("ix_error_logs_path")
    op.drop_index("ix_error_logs_timestamp")
    op.drop_table("error_logs")
