"""Cappe magazines, PR 3 — pictures imported from open archives.

A writer searches Openverse (Creative Commons and public-domain photos),
Smithsonian Open Access, The Met's open collection and NASA's image library
from the magazine's Library, and imports what they choose. An import is a row
here, worked by `workers/tasks/cappe_media_import.py`: the picture is looked up
again at the source (its license is re-checked then, not trusted from the
search), downloaded through the SSRF-guarded fetcher, re-encoded, and stored as
a `cappe_assets` row with `kind='stock'` and its credit.

`cappe_asset_imports`
  * `source`, `source_id` — the picture at its archive; one import per site
    and picture (`UNIQUE(site_id, source, source_id)`), so importing it again
    returns the one already in the library;
  * `status` — pending → working → ready, or failed / refused (the source no
    longer offers it under a license we accept);
  * `attempts`, `claimed_at` — a claim older than ten minutes is picked up
    again, at most three times;
  * `asset_id` — the library picture once it is in; `post_id` — the story it
    was found for, if any.

Plan feature `stock_imports_per_day`: 300 on business, pro and creator, 25 on
free (counted per account over 24 hours).

Additive. The downgrade drops the table and the feature.

Revision ID: cappemag03
Revises: cappemag02
Create Date: 2026-10-21
"""
from alembic import op

revision = "cappemag03"
down_revision = "cappemag02"
branch_labels = None
depends_on = None

_UPGRADE = [
    """
    CREATE TABLE IF NOT EXISTS cappe_asset_imports (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        account_id UUID NOT NULL REFERENCES cappe_accounts(id) ON DELETE CASCADE,
        source VARCHAR(16) NOT NULL CHECK (source IN ('openverse', 'smithsonian', 'met', 'nasa')),
        source_id VARCHAR(200) NOT NULL,
        status VARCHAR(10) NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'working', 'ready', 'failed', 'refused')),
        attempts SMALLINT NOT NULL DEFAULT 0,
        claimed_at TIMESTAMPTZ,
        error VARCHAR(300),
        asset_id UUID REFERENCES cappe_assets(id) ON DELETE SET NULL,
        post_id UUID REFERENCES cappe_posts(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (site_id, source, source_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_asset_imports_open ON cappe_asset_imports (site_id, created_at) "
    "WHERE status IN ('pending', 'working')",
    "CREATE INDEX IF NOT EXISTS idx_cappe_asset_imports_account ON cappe_asset_imports (account_id, created_at)",
    "UPDATE cappe_billing_products SET features = features || jsonb_build_object('stock_imports_per_day', 300) "
    "WHERE code IN ('business', 'pro', 'creator')",
    "UPDATE cappe_billing_products SET features = features || jsonb_build_object('stock_imports_per_day', 25) "
    "WHERE code = 'free'",
]

_DOWNGRADE = [
    "UPDATE cappe_billing_products SET features = features - 'stock_imports_per_day' "
    "WHERE features ->> 'stock_imports_per_day' IS NOT NULL",
    "DROP TABLE IF EXISTS cappe_asset_imports",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
