"""Add company_feature_grants — WHY an admin-granted feature was given,
distinct from WHERE it came from (feature_provenance/company_feature_audit_log
answer the latter; this answers "did we bill for it").

A feature enabled outside a company's plan/bundle/add-on/product (the
'unknown'-turned-'Admin' provenance bucket) carries no record of whether it
was comped, invoiced separately, a time-boxed trial, or purely internal
(demo/QA). This table lets an admin record that classification + a free-text
note per (company, feature) via /admin/company-features/{id}/grants/{feature}.

Revision ID: featgrant01
Revises: feataudit01
Create Date: 2026-07-28
"""
from alembic import op

revision = "featgrant01"
down_revision = "feataudit01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS company_feature_grants (
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            feature TEXT NOT NULL,
            grant_type TEXT NOT NULL CHECK (grant_type IN ('comped', 'invoiced', 'trial', 'internal')),
            note TEXT,
            updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (company_id, feature)
        )
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS company_feature_grants")
