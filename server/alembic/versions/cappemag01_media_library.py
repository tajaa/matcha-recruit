"""Cappe magazines, PR 1 — the image library knows where each picture came from.

`cappe_assets` was a bare list of URLs. A photo-journalism story prints a
credit under every picture and an AI illustration must always say so, so
each asset now carries:

  * where it came from: `source` (upload, generated, and the open archives
    the next PR imports from: openverse, smithsonian, met, nasa), `source_id`,
    `source_url` (the page we found it on, kept because Openverse does not
    guarantee its license data), `title`, `creator`, `creator_url`;
  * its license and the credit we print: `license` (own, cc0, pdm, by, by-sa,
    ai), `license_version`, `license_url`, `provider_label`, `credit_line`;
  * what a reader sees: `alt`, `caption`;
  * the file: `width`, `height`, `bytes`, `mime`, and `variants` (the
    responsive sizes, `{"webp": [{"w", "url"}], "share": {"w", "url"}}`);
  * `ai_generated`, `rights_attested_at` (the owner's "I took this or may use
    it" on upload), `moderation` (unchecked/ok/flagged/blocked; the showcase
    screening fills it later), `updated_at`.

`kind` gains `stock` (an imported archive image). A generated image is always
AI (`CHECK (kind <> 'generated' OR ai_generated)`), and the backfill labels
every generated row already in the table. One archive image is imported into
a site once: a partial unique index on `(site_id, source, source_id)`.

The original `kind` CHECK was inline and unnamed, so it is found by its
definition and replaced by named ones.

Additive. The downgrade deletes `stock` rows (the old CHECK can't hold them),
drops the named checks and the index, restores the old `kind` check and drops
the columns.

Revision ID: cappemag01
Revises: cappesocial03
Create Date: 2026-10-20
"""
from alembic import op

revision = "cappemag01"
down_revision = "cappesocial03"
branch_labels = None
depends_on = None


_UPGRADE = [
    "ALTER TABLE cappe_assets "
    "ADD COLUMN IF NOT EXISTS source VARCHAR(16), "
    "ADD COLUMN IF NOT EXISTS source_id VARCHAR(200), "
    "ADD COLUMN IF NOT EXISTS source_url TEXT, "
    "ADD COLUMN IF NOT EXISTS title VARCHAR(500), "
    "ADD COLUMN IF NOT EXISTS creator VARCHAR(300), "
    "ADD COLUMN IF NOT EXISTS creator_url TEXT, "
    "ADD COLUMN IF NOT EXISTS license VARCHAR(16), "
    "ADD COLUMN IF NOT EXISTS license_version VARCHAR(8), "
    "ADD COLUMN IF NOT EXISTS license_url TEXT, "
    "ADD COLUMN IF NOT EXISTS provider_label VARCHAR(80), "
    "ADD COLUMN IF NOT EXISTS credit_line VARCHAR(500), "
    "ADD COLUMN IF NOT EXISTS alt TEXT, "
    "ADD COLUMN IF NOT EXISTS caption TEXT, "
    "ADD COLUMN IF NOT EXISTS width INTEGER, "
    "ADD COLUMN IF NOT EXISTS height INTEGER, "
    "ADD COLUMN IF NOT EXISTS bytes INTEGER, "
    "ADD COLUMN IF NOT EXISTS mime VARCHAR(40), "
    "ADD COLUMN IF NOT EXISTS variants JSONB NOT NULL DEFAULT '{}'::jsonb, "
    "ADD COLUMN IF NOT EXISTS ai_generated BOOLEAN NOT NULL DEFAULT false, "
    "ADD COLUMN IF NOT EXISTS rights_attested_at TIMESTAMPTZ, "
    "ADD COLUMN IF NOT EXISTS moderation VARCHAR(12) NOT NULL DEFAULT 'unchecked', "
    "ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
    # Every image generated so far is AI and says so.
    "UPDATE cappe_assets SET ai_generated = true, license = 'ai', credit_line = 'AI illustration', "
    "source = 'generated' WHERE kind = 'generated' AND NOT ai_generated",
    "UPDATE cappe_assets SET source = 'upload' WHERE kind = 'upload' AND source IS NULL",
    # The inline kind CHECK from zzzzcappe23 has no name we chose: drop it by
    # what it says. Our own named checks are left alone, so a re-run is safe.
    """
    DO $$ DECLARE c text; BEGIN
        FOR c IN SELECT conname FROM pg_constraint
                  WHERE conrelid = 'cappe_assets'::regclass AND contype = 'c'
                    AND conname NOT LIKE 'ck_cappe_assets_%'
                    AND pg_get_constraintdef(oid) LIKE '%kind%'
                    AND pg_get_constraintdef(oid) LIKE '%upload%'
        LOOP
            EXECUTE format('ALTER TABLE cappe_assets DROP CONSTRAINT %I', c);
        END LOOP;
    END $$
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cappe_assets_kind') THEN
            ALTER TABLE cappe_assets ADD CONSTRAINT ck_cappe_assets_kind
                CHECK (kind IN ('generated', 'upload', 'stock'));
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cappe_assets_ai') THEN
            ALTER TABLE cappe_assets ADD CONSTRAINT ck_cappe_assets_ai
                CHECK (kind <> 'generated' OR ai_generated);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cappe_assets_source') THEN
            ALTER TABLE cappe_assets ADD CONSTRAINT ck_cappe_assets_source
                CHECK (source IS NULL OR source IN
                       ('upload', 'generated', 'openverse', 'smithsonian', 'met', 'nasa'));
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cappe_assets_license') THEN
            ALTER TABLE cappe_assets ADD CONSTRAINT ck_cappe_assets_license
                CHECK (license IS NULL OR license IN ('own', 'cc0', 'pdm', 'by', 'by-sa', 'ai'));
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cappe_assets_moderation') THEN
            ALTER TABLE cappe_assets ADD CONSTRAINT ck_cappe_assets_moderation
                CHECK (moderation IN ('unchecked', 'ok', 'flagged', 'blocked'));
        END IF;
    END $$
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_cappe_assets_source ON cappe_assets (site_id, source, source_id) "
    "WHERE source_id IS NOT NULL",
]

_DOWNGRADE = [
    "DROP INDEX IF EXISTS uq_cappe_assets_source",
    "DELETE FROM cappe_assets WHERE kind = 'stock'",
    "ALTER TABLE cappe_assets DROP CONSTRAINT IF EXISTS ck_cappe_assets_kind, "
    "DROP CONSTRAINT IF EXISTS ck_cappe_assets_ai, "
    "DROP CONSTRAINT IF EXISTS ck_cappe_assets_source, "
    "DROP CONSTRAINT IF EXISTS ck_cappe_assets_license, "
    "DROP CONSTRAINT IF EXISTS ck_cappe_assets_moderation",
    """
    DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'cappe_assets_kind_check') THEN
            ALTER TABLE cappe_assets ADD CONSTRAINT cappe_assets_kind_check
                CHECK (kind IN ('generated', 'upload'));
        END IF;
    END $$
    """,
    "ALTER TABLE cappe_assets "
    "DROP COLUMN IF EXISTS updated_at, DROP COLUMN IF EXISTS moderation, "
    "DROP COLUMN IF EXISTS rights_attested_at, DROP COLUMN IF EXISTS ai_generated, "
    "DROP COLUMN IF EXISTS variants, DROP COLUMN IF EXISTS mime, DROP COLUMN IF EXISTS bytes, "
    "DROP COLUMN IF EXISTS height, DROP COLUMN IF EXISTS width, DROP COLUMN IF EXISTS caption, "
    "DROP COLUMN IF EXISTS alt, DROP COLUMN IF EXISTS credit_line, DROP COLUMN IF EXISTS provider_label, "
    "DROP COLUMN IF EXISTS license_url, DROP COLUMN IF EXISTS license_version, DROP COLUMN IF EXISTS license, "
    "DROP COLUMN IF EXISTS creator_url, DROP COLUMN IF EXISTS creator, DROP COLUMN IF EXISTS title, "
    "DROP COLUMN IF EXISTS source_url, DROP COLUMN IF EXISTS source_id, DROP COLUMN IF EXISTS source",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
