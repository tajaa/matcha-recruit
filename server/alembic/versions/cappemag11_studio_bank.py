"""Cappe magazines — the Gummfit-curated bank in Gummfit Studio's side panel.

  * `cappe_studio_bank`: photos and graphics a Matcha admin puts in every
    site's Studio (hey-matcha.com/admin/cappe, "Studio bank").
      - A photo is stored once with its responsive sizes (`url`, `variants`).
        Placing it gives the site a library row (`cappe_assets`, kind `stock`,
        source `gummfit`, `source_id` the bank row's id) that points at the
        same files and prints the photo's credit. Deleting a bank photo leaves
        those rows, and the files, alone.
      - A graphic is a cleaned SVG stored by its sha256 beside the built-in
        bank's (`cappe/graphics/<sha>.svg`). Pages name it by `sha`, so a
        graphic is hidden (`status`), never deleted.
  * `cappe_assets.source` gains `gummfit`, and `license` gains `gummfit`: a
    photo Gummfit provides for use on Gummfit sites.

Revision ID: cappemag11
Revises: cappemag10
Create Date: 2026-10-22
"""
from alembic import op

revision = "cappemag11"
down_revision = "cappemag10"
branch_labels = None
depends_on = None

_SOURCES = "'upload', 'generated', 'openverse', 'smithsonian', 'met', 'nasa'"
_LICENSES = "'own', 'cc0', 'pdm', 'by', 'by-sa', 'ai'"

_UPGRADE = [
    """
    CREATE TABLE IF NOT EXISTS cappe_studio_bank (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        kind VARCHAR(8) NOT NULL CHECK (kind IN ('photo', 'graphic')),
        name VARCHAR(120) NOT NULL,
        tags TEXT[] NOT NULL DEFAULT '{}',
        collection VARCHAR(60),
        status VARCHAR(8) NOT NULL DEFAULT 'live' CHECK (status IN ('live', 'hidden')),
        sort_order INTEGER NOT NULL DEFAULT 0,
        url TEXT,
        variants JSONB,
        width INTEGER,
        height INTEGER,
        bytes INTEGER,
        mime VARCHAR(32),
        creator VARCHAR(200),
        credit_line VARCHAR(500),
        license VARCHAR(16),
        source_url TEXT,
        sha TEXT UNIQUE CHECK (sha ~ '^[0-9a-f]{64}$'),
        mono BOOLEAN,
        fit VARCHAR(8),
        graphic_group VARCHAR(12),
        w REAL,
        h REAL,
        created_by_email VARCHAR(320),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT ck_cappe_studio_bank_photo CHECK (kind <> 'photo' OR (
            url IS NOT NULL AND width IS NOT NULL AND height IS NOT NULL
            AND license IN ('gummfit', 'cc0', 'pdm', 'by', 'by-sa'))),
        CONSTRAINT ck_cappe_studio_bank_graphic CHECK (kind <> 'graphic' OR (
            sha IS NOT NULL AND mono IS NOT NULL AND fit IN ('contain', 'stretch', 'tile')
            AND graphic_group IN ('shapes', 'lines', 'badges', 'icons', 'stickers', 'patterns')))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_studio_bank_browse "
    "ON cappe_studio_bank (kind, status, sort_order, created_at DESC)",
    "ALTER TABLE cappe_assets DROP CONSTRAINT IF EXISTS ck_cappe_assets_source",
    f"ALTER TABLE cappe_assets ADD CONSTRAINT ck_cappe_assets_source CHECK (source IS NULL OR source IN ({_SOURCES}, 'gummfit'))",
    "ALTER TABLE cappe_assets DROP CONSTRAINT IF EXISTS ck_cappe_assets_license",
    f"ALTER TABLE cappe_assets ADD CONSTRAINT ck_cappe_assets_license CHECK (license IS NULL OR license IN ({_LICENSES}, 'gummfit'))",
]

_DOWNGRADE = [
    # A library picture from the bank can't be relabelled as any older source,
    # and the bank's graphics are the only record of the shas pages may name
    # (in a story, its working copy or a revision): without them, older code
    # refuses those pages and serves those graphics as 404s.
    """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM cappe_assets WHERE source = 'gummfit' OR license = 'gummfit') THEN
            RAISE EXCEPTION 'cappe_assets holds pictures from the Studio bank; delete them before downgrading';
        END IF;
        IF EXISTS (SELECT 1 FROM cappe_studio_bank WHERE kind = 'graphic') THEN
            RAISE EXCEPTION 'cappe_studio_bank holds graphics pages may name; downgrading would drop them';
        END IF;
    END $$
    """,
    "ALTER TABLE cappe_assets DROP CONSTRAINT IF EXISTS ck_cappe_assets_license",
    f"ALTER TABLE cappe_assets ADD CONSTRAINT ck_cappe_assets_license CHECK (license IS NULL OR license IN ({_LICENSES}))",
    "ALTER TABLE cappe_assets DROP CONSTRAINT IF EXISTS ck_cappe_assets_source",
    f"ALTER TABLE cappe_assets ADD CONSTRAINT ck_cappe_assets_source CHECK (source IS NULL OR source IN ({_SOURCES}))",
    "DROP TABLE IF EXISTS cappe_studio_bank",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
