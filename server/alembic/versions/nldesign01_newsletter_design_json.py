"""newsletter block designs (design_json)

Adds a structured ``design_json`` (JSONB) to newsletters + templates. When
present it is the source of truth for the "website-in-the-inbox" block builder;
``content_html`` is kept as a rendered snapshot (for view-in-browser and any
non-design consumer). Send/preview re-render from ``design_json`` so recipients
never see a stale snapshot.

Revision ID: nldesign01
Revises: nlideas01
Create Date: 2026-07-13
"""

from alembic import op


revision = "nldesign01"
down_revision = "nlideas01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE newsletters ADD COLUMN IF NOT EXISTS design_json JSONB")
    op.execute("ALTER TABLE newsletter_templates ADD COLUMN IF NOT EXISTS design_json JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE newsletter_templates DROP COLUMN IF EXISTS design_json")
    op.execute("ALTER TABLE newsletters DROP COLUMN IF EXISTS design_json")
