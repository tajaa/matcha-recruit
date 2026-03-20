"""Add company_sso_configs table for SAML SSO

Revision ID: zt8u9v0w1x2y
Revises: zs7t8u9v0w1x
Create Date: 2026-03-20
"""

from alembic import op
import sqlalchemy as sa

revision = "zt8u9v0w1x2y"
down_revision = "6e1e0c232a7f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "company_sso_configs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("company_id", sa.UUID(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("idp_entity_id", sa.Text(), nullable=False),
        sa.Column("idp_sso_url", sa.Text(), nullable=False),
        sa.Column("idp_x509_cert", sa.Text(), nullable=False),
        sa.Column("email_domain", sa.String(255), nullable=False),
        sa.Column("default_role", sa.String(20), server_default="employee", nullable=False),
        sa.Column("auto_provision", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index(
        "idx_company_sso_configs_domain",
        "company_sso_configs",
        ["email_domain"],
        postgresql_where=sa.text("enabled = true"),
    )


def downgrade():
    op.drop_index("idx_company_sso_configs_domain", table_name="company_sso_configs")
    op.drop_table("company_sso_configs")
