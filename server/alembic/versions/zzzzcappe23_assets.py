"""cappe: generated/uploaded image asset library

Every image a site owner generates (editor button, Merlin op, Merlin agent
tool) or uploads has been fire-and-forget — landed on the page, no record of
it existed anywhere else, so there was no way to reuse a past generation or
browse what had been made. This table is a lightweight index over the S3
objects that already exist under the `cappe`/`cappe/gen` prefixes; it does not
change where files are stored, only adds a per-site catalog of the URLs.

`account_id` is denormalized alongside `site_id` (both already on every other
cappe child table) so ownership checks don't need a join through
`cappe_sites` on the hot list-path.

Row deletion (`DELETE /sites/{id}/assets/{asset_id}`) never deletes the S3
blob — a page's `_design.bg.image` / block image field may still point at it,
and this table has no way to know. It is a catalog, not a reference-counted
store.

Revision ID: zzzzcappe23
Revises: zzzzcappe22
Create Date: 2026-07-22
"""
from alembic import op

revision = "zzzzcappe23"
down_revision = "zzzzcappe22"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_assets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID NOT NULL REFERENCES cappe_accounts(id) ON DELETE CASCADE,
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            kind VARCHAR(16) NOT NULL CHECK (kind IN ('generated', 'upload')),
            url TEXT NOT NULL,
            prompt TEXT,
            aspect VARCHAR(8),
            image_size VARCHAR(8),
            meta JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_assets_site "
        "ON cappe_assets(site_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cappe_assets")
