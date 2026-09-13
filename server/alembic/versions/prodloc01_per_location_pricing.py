"""Add per-location pricing support to custom products.

Revision ID: prodloc01
Revises: autoprrun02
Create Date: 2026-09-12
"""

from alembic import op
import sqlalchemy as sa


revision = "prodloc01"
down_revision = "autoprrun02"
branch_labels = None
depends_on = ("proddef01", "l7m8n9o0p1q2")


def upgrade():
    op.drop_constraint(
        "product_definitions_pricing_model_check",
        "product_definitions",
        type_="check",
    )
    op.create_check_constraint(
        "product_definitions_pricing_model_check",
        "product_definitions",
        "pricing_model IN ('per_seat', 'per_location', 'block', 'flat', 'free', 'contact_sales')",
    )
    op.add_column(
        "company_handbook_profiles",
        sa.Column("custom_product_location_count", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "company_handbook_profiles_custom_product_location_count_check",
        "company_handbook_profiles",
        "custom_product_location_count IS NULL OR custom_product_location_count > 0",
    )


def downgrade():
    # A per-location unit price cannot be losslessly converted to a flat price:
    # each tenant may have a different persisted quantity. Fail before changing
    # the schema so rollback requires those definitions to be migrated or
    # archived deliberately instead of silently changing what tenants owe.
    bind = op.get_bind()
    if bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM product_definitions "
            "WHERE pricing_model = 'per_location')"
        )
    ).scalar():
        raise RuntimeError(
            "Cannot downgrade prodloc01 while per-location product definitions exist"
        )
    op.drop_constraint(
        "company_handbook_profiles_custom_product_location_count_check",
        "company_handbook_profiles",
        type_="check",
    )
    op.drop_column("company_handbook_profiles", "custom_product_location_count")
    op.drop_constraint(
        "product_definitions_pricing_model_check",
        "product_definitions",
        type_="check",
    )
    op.create_check_constraint(
        "product_definitions_pricing_model_check",
        "product_definitions",
        "pricing_model IN ('per_seat', 'block', 'flat', 'free', 'contact_sales')",
    )
