"""Cappe sites remember which code-registry template they were cloned from.

The template catalog moved out of the `cappe_templates` table into a code
registry (`app/cappe/services/site_templates/`), so a site can no longer point
at a template ROW. `template_slug` records the registry key instead — read by
"reset my design to the template's original look" and shown in the dashboard.

`template_id` and `cappe_templates` are left untouched: still-valid rows for
existing sites, nothing writes them any more, and dropping them is a separate
migration to approve on its own.

Additive + idempotent.

Revision ID: zzzzcappe37
Revises: zzzzcappe36
"""
from alembic import op

revision = "zzzzcappe37"
down_revision = "zzzzcappe36"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE cappe_sites
            ADD COLUMN IF NOT EXISTS template_slug VARCHAR(160)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE cappe_sites
            DROP COLUMN IF EXISTS template_slug
        """
    )
