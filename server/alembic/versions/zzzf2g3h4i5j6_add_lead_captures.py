"""Add lead_captures table for resource hub downloads.

Revision ID: zzzf2g3h4i5j6
Revises: zzze1f2g3h4i5
Create Date: 2026-04-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "zzzf2g3h4i5j6"
down_revision = "zzze1f2g3h4i5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_captures",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("asset_slug", sa.String(100), nullable=False),
        sa.Column("source", sa.String(100), nullable=True, server_default="resources"),
        sa.Column("utm_source", sa.String(100), nullable=True),
        sa.Column("utm_medium", sa.String(100), nullable=True),
        sa.Column("utm_campaign", sa.String(100), nullable=True),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_lead_captures_email", "lead_captures", ["email"])
    op.create_index("idx_lead_captures_asset_slug", "lead_captures", ["asset_slug"])
    op.create_index("idx_lead_captures_created_at", "lead_captures", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_lead_captures_created_at", table_name="lead_captures")
    op.drop_index("idx_lead_captures_asset_slug", table_name="lead_captures")
    op.drop_index("idx_lead_captures_email", table_name="lead_captures")
    op.drop_table("lead_captures")
