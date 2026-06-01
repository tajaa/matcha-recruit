"""Add deal_flow_templates — persist admin Deal Flow editor templates.

The Deal Flow admin tool (/admin/deal-flow) was stateless: every edit to a
proposal template (prose blocks, discount/margin tiers, per-tier pricing) lived
only in browser state and was lost on reload. This table gives each editor tab a
single shared, admin-global saved template, keyed by a stable string
(book / full / broker / one_pager / lite). The payload is an opaque JSONB blob
whose shape each tab owns; the GET endpoint falls back to the hardcoded
``*-defaults`` constants when no row exists, so an unsaved tab behaves exactly as
before.

Idempotent (CREATE TABLE IF NOT EXISTS) so re-running against a partially
upgraded DB is safe.

Revision ID: dealflowtmpl01
Revises: chinvemail01
Create Date: 2026-06-01
"""
from alembic import op


revision = "dealflowtmpl01"
down_revision = "chinvemail01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS deal_flow_templates (
            template_key text PRIMARY KEY,
            payload      jsonb NOT NULL,
            updated_at   timestamptz NOT NULL DEFAULT now(),
            updated_by   text
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS deal_flow_templates")
