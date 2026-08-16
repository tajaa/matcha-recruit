"""tellus_app_24 — brand profile fields for Discover.

tellus_brands had only name/logo_url/slug/plan-billing columns — no way to
show a business off beyond its logo. Additive only, no backfill. See
TELLUS_DISCOVER_PLAN.md at the repo root for the full feature design.
"""
from alembic import op


revision = "tellus_app_24"
down_revision = "tellus_app_23"
branch_labels = None
depends_on = None


_COLUMNS = (
    ("tagline", "TEXT"),
    ("description", "TEXT"),
    ("cover_url", "TEXT"),
    ("category", "TEXT"),
    ("website", "TEXT"),
    ("hours", "JSONB"),
)


def upgrade() -> None:
    for col, ddl in _COLUMNS:
        op.execute(f"ALTER TABLE tellus_brands ADD COLUMN IF NOT EXISTS {col} {ddl}")


def downgrade() -> None:
    for col, _ in reversed(_COLUMNS):
        op.execute(f"ALTER TABLE tellus_brands DROP COLUMN IF EXISTS {col}")
