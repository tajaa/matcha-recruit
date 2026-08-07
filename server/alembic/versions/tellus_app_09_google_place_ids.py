"""tellus_app_09 — Google Place IDs on brands + stores.

Revision ID: tellus_app_09
Revises: tellus_app_08
"""
from alembic import op

revision = "tellus_app_09"
down_revision = "tellus_app_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE tellus_brands ADD COLUMN IF NOT EXISTS google_place_id TEXT")
    # Partial unique: one brand per Google place. NULLs (manual/free-text places) exempt.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_brands_google_place_id "
        "ON tellus_brands (google_place_id) WHERE google_place_id IS NOT NULL"
    )
    op.execute("ALTER TABLE tellus_stores ADD COLUMN IF NOT EXISTS google_place_id TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE tellus_stores DROP COLUMN IF EXISTS google_place_id")
    op.execute("DROP INDEX IF EXISTS ux_tellus_brands_google_place_id")
    op.execute("ALTER TABLE tellus_brands DROP COLUMN IF EXISTS google_place_id")
