"""Cappe magazines — edited pictures (Gummfit Studio's Picture Editor).

  * `cappe_assets.kind` gains `edit`: a picture made in the Picture Editor from
    another library picture (a look, adjustments, a crop, a cut-out). Its file
    is new; the picture it came from is never changed.
  * `parent_asset_id` is that picture (an edit of an edit points at the first
    one, so editing again always starts from the original pixels); it goes to
    NULL if the original is deleted, and the edit keeps its own copy of the
    original's provenance and licence.
  * `recipe` is what was done (services/magazine/studio/recipe.py), so the
    editor can open it again with every slider where it was left;
    `recipe_version` is the recipe's format.
  * `adapted` says the pixels were changed from the source's: a CC BY / BY-SA
    picture's credit then says "(adapted)".

Revision ID: cappemag10
Revises: cappemag09
Create Date: 2026-10-22
"""
from alembic import op

revision = "cappemag10"
down_revision = "cappemag09"
branch_labels = None
depends_on = None

_UPGRADE = [
    "ALTER TABLE cappe_assets DROP CONSTRAINT IF EXISTS ck_cappe_assets_kind",
    "ALTER TABLE cappe_assets ADD CONSTRAINT ck_cappe_assets_kind CHECK (kind IN ('generated', 'upload', 'stock', 'edit'))",
    "ALTER TABLE cappe_assets ADD COLUMN IF NOT EXISTS parent_asset_id UUID REFERENCES cappe_assets(id) ON DELETE SET NULL",
    "ALTER TABLE cappe_assets ADD COLUMN IF NOT EXISTS recipe JSONB",
    "ALTER TABLE cappe_assets ADD COLUMN IF NOT EXISTS recipe_version SMALLINT",
    "ALTER TABLE cappe_assets ADD COLUMN IF NOT EXISTS adapted BOOLEAN NOT NULL DEFAULT FALSE",
    "CREATE INDEX IF NOT EXISTS idx_cappe_assets_parent ON cappe_assets (parent_asset_id) WHERE parent_asset_id IS NOT NULL",
]

_DOWNGRADE = [
    # An edited picture can't be any older kind: refuse rather than relabel it.
    """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM cappe_assets WHERE kind = 'edit') THEN
            RAISE EXCEPTION 'cappe_assets holds edited pictures; delete them before downgrading';
        END IF;
    END $$
    """,
    "DROP INDEX IF EXISTS idx_cappe_assets_parent",
    "ALTER TABLE cappe_assets DROP COLUMN IF EXISTS adapted",
    "ALTER TABLE cappe_assets DROP COLUMN IF EXISTS recipe_version",
    "ALTER TABLE cappe_assets DROP COLUMN IF EXISTS recipe",
    "ALTER TABLE cappe_assets DROP COLUMN IF EXISTS parent_asset_id",
    "ALTER TABLE cappe_assets DROP CONSTRAINT IF EXISTS ck_cappe_assets_kind",
    "ALTER TABLE cappe_assets ADD CONSTRAINT ck_cappe_assets_kind CHECK (kind IN ('generated', 'upload', 'stock'))",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
