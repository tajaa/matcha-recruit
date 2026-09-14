"""Add explicit custom-product S&C onboarding state.

Revision ID: sconboard01
Revises: prodloc01
Create Date: 2026-09-13
"""

from alembic import op
import sqlalchemy as sa


revision = "sconboard01"
down_revision = "prodloc01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_definitions",
        sa.Column("onboarding_kind", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        op.f("product_definitions_onboarding_kind_check"),
        "product_definitions",
        "onboarding_kind IS NULL OR onboarding_kind IN ('sc')",
    )
    op.add_column(
        "companies",
        sa.Column("sc_onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("companies", "sc_onboarding_completed_at")
    op.drop_constraint(
        op.f("product_definitions_onboarding_kind_check"),
        "product_definitions",
        type_="check",
    )
    op.drop_column("product_definitions", "onboarding_kind")
