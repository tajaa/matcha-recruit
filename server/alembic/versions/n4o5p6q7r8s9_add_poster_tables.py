"""add poster tables

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-02-05
"""
from alembic import op
import sqlalchemy as sa

revision = "n4o5p6q7r8s9"
down_revision = "m3n4o5p6q7r8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Poster templates — one per jurisdiction, auto-generated PDF
    op.create_table(
        "poster_templates",
        sa.Column("id", sa.dialects.postgresql.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("jurisdiction_id", sa.dialects.postgresql.UUID(), sa.ForeignKey("jurisdictions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("pdf_url", sa.Text()),
        sa.Column("pdf_generated_at", sa.DateTime()),
        sa.Column("categories_included", sa.dialects.postgresql.ARRAY(sa.Text())),
        sa.Column("requirement_count", sa.Integer(), server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )
    op.create_check_constraint(
        "ck_poster_templates_status",
        "poster_templates",
        "status IN ('pending', 'generated', 'failed')",
    )

    # Poster orders — company requests for printed posters
    op.create_table(
        "poster_orders",
        sa.Column("id", sa.dialects.postgresql.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("company_id", sa.dialects.postgresql.UUID(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", sa.dialects.postgresql.UUID(), sa.ForeignKey("business_locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="requested"),
        sa.Column("requested_by", sa.dialects.postgresql.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("admin_notes", sa.Text()),
        sa.Column("quote_amount", sa.Numeric(10, 2)),
        sa.Column("shipping_address", sa.Text()),
        sa.Column("tracking_number", sa.String(100)),
        sa.Column("shipped_at", sa.DateTime()),
        sa.Column("delivered_at", sa.DateTime()),
        sa.Column("metadata", sa.dialects.postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )
    op.create_check_constraint(
        "ck_poster_orders_status",
        "poster_orders",
        "status IN ('requested', 'quoted', 'processing', 'shipped', 'delivered', 'cancelled')",
    )
    op.create_index("idx_poster_orders_company_id", "poster_orders", ["company_id"])
    op.create_index("idx_poster_orders_status", "poster_orders", ["status"])

    # Poster order items — links orders to templates
    op.create_table(
        "poster_order_items",
        sa.Column("id", sa.dialects.postgresql.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("order_id", sa.dialects.postgresql.UUID(), sa.ForeignKey("poster_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", sa.dialects.postgresql.UUID(), sa.ForeignKey("poster_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_poster_order_items_order_id", "poster_order_items", ["order_id"])


def downgrade() -> None:
    op.drop_table("poster_order_items")
    op.drop_table("poster_orders")
    op.drop_table("poster_templates")
