"""Cappe magazines, PR 2 — stories laid out like a print magazine, and the
magazine that holds them.

`cappe_posts` becomes the story. A post was a title and a Markdown body that
nothing ever rendered; a story is a list of blocks (a cover photo with the
headline over it, text with a drop cap, full-bleed photos, photo pairs and
grids, pull quotes, a sidebar, an interview's Q&A) that the site renders at
`/stories/<slug>`. The columns are all optional or defaulted, because the iOS
app reads and writes posts with the old fields:

  * `format` — `markdown` (every post so far, rendered as one text block) or
    `blocks`; `content` — `{"blocks": [...]}`;
  * `kicker` (the small line over a headline), `topic`, `layout` (standard,
    cover_story, photo_essay, interview, dispatch, lookbook), `byline`;
  * `access` — free or paid (paid readers arrive in PR 6);
  * `cover_asset_id` — the library picture on the cover;
  * `word_count`, `reading_minutes` — kept on save;
  * `hidden_at`, `hidden_reason` — a story an admin took down (PR 7).

`cappe_post_assets` — every library picture a story uses, rebuilt on each
save, so the library can say where a picture is used and refuse to delete it.
The asset FK is NO ACTION (checked at the end of the statement), so deleting a
whole site still cascades cleanly.

`cappe_magazines` — one per site: its name and masthead, tagline, about text,
masthead style, accent colour, up to five topics, whether its front page is the
site's home (`front_at_root`, a writer's magazine-only site), the nav label,
the cover story, and whether readers may follow it.

The `magazine` plan feature goes on business, pro and creator (the writer plan
arrives in PR 5).

Additive. The downgrade drops the tables, the columns and the feature.

Revision ID: cappemag02
Revises: cappemag01
Create Date: 2026-10-20
"""
from alembic import op

revision = "cappemag02"
down_revision = "cappemag01"
branch_labels = None
depends_on = None

_LAYOUTS = "'standard', 'cover_story', 'photo_essay', 'interview', 'dispatch', 'lookbook'"
_MASTHEADS = "'classic', 'literary', 'modern', 'elegant', 'display'"

_UPGRADE = [
    "ALTER TABLE cappe_posts "
    "ADD COLUMN IF NOT EXISTS format VARCHAR(8) NOT NULL DEFAULT 'markdown', "
    "ADD COLUMN IF NOT EXISTS content JSONB NOT NULL DEFAULT '{}'::jsonb, "
    "ADD COLUMN IF NOT EXISTS kicker VARCHAR(60), "
    "ADD COLUMN IF NOT EXISTS topic VARCHAR(40), "
    "ADD COLUMN IF NOT EXISTS layout VARCHAR(20) NOT NULL DEFAULT 'standard', "
    "ADD COLUMN IF NOT EXISTS access VARCHAR(8) NOT NULL DEFAULT 'free', "
    "ADD COLUMN IF NOT EXISTS cover_asset_id UUID REFERENCES cappe_assets(id) ON DELETE SET NULL, "
    "ADD COLUMN IF NOT EXISTS byline VARCHAR(160), "
    "ADD COLUMN IF NOT EXISTS word_count INTEGER NOT NULL DEFAULT 0, "
    "ADD COLUMN IF NOT EXISTS reading_minutes SMALLINT NOT NULL DEFAULT 0, "
    "ADD COLUMN IF NOT EXISTS hidden_at TIMESTAMPTZ, "
    "ADD COLUMN IF NOT EXISTS hidden_reason VARCHAR(300)",
    f"""
    DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cappe_posts_format') THEN
            ALTER TABLE cappe_posts ADD CONSTRAINT ck_cappe_posts_format CHECK (format IN ('markdown', 'blocks'));
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cappe_posts_layout') THEN
            ALTER TABLE cappe_posts ADD CONSTRAINT ck_cappe_posts_layout CHECK (layout IN ({_LAYOUTS}));
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cappe_posts_access') THEN
            ALTER TABLE cappe_posts ADD CONSTRAINT ck_cappe_posts_access CHECK (access IN ('free', 'paid'));
        END IF;
    END $$
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_posts_live ON cappe_posts (site_id, published_at DESC) "
    "WHERE status = 'published' AND hidden_at IS NULL",
    "CREATE INDEX IF NOT EXISTS idx_cappe_posts_topic ON cappe_posts (site_id, topic, published_at DESC) "
    "WHERE status = 'published' AND hidden_at IS NULL",
    """
    CREATE TABLE IF NOT EXISTS cappe_post_assets (
        post_id UUID NOT NULL REFERENCES cappe_posts(id) ON DELETE CASCADE,
        asset_id UUID NOT NULL REFERENCES cappe_assets(id),
        site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        PRIMARY KEY (post_id, asset_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_post_assets_asset ON cappe_post_assets (asset_id)",
    f"""
    CREATE TABLE IF NOT EXISTS cappe_magazines (
        site_id UUID PRIMARY KEY REFERENCES cappe_sites(id) ON DELETE CASCADE,
        enabled BOOLEAN NOT NULL DEFAULT false,
        name VARCHAR(120) NOT NULL,
        tagline VARCHAR(200),
        about TEXT,
        masthead_style VARCHAR(16) NOT NULL DEFAULT 'classic' CHECK (masthead_style IN ({_MASTHEADS})),
        accent VARCHAR(7) CHECK (accent IS NULL OR accent ~ '^#[0-9a-fA-F]{{6}}$'),
        topics TEXT[] NOT NULL DEFAULT '{{}}'::text[] CHECK (cardinality(topics) <= 5),
        front_at_root BOOLEAN NOT NULL DEFAULT false,
        nav_label VARCHAR(40) NOT NULL DEFAULT 'Magazine',
        cover_post_id UUID REFERENCES cappe_posts(id) ON DELETE SET NULL,
        follow_enabled BOOLEAN NOT NULL DEFAULT true,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "UPDATE cappe_billing_products SET features = features || jsonb_build_object('magazine', true) "
    "WHERE code IN ('business', 'pro', 'creator')",
]

_DOWNGRADE = [
    "UPDATE cappe_billing_products SET features = features - 'magazine' WHERE features ->> 'magazine' IS NOT NULL",
    "DROP TABLE IF EXISTS cappe_magazines",
    "DROP TABLE IF EXISTS cappe_post_assets",
    "DROP INDEX IF EXISTS idx_cappe_posts_topic",
    "DROP INDEX IF EXISTS idx_cappe_posts_live",
    "ALTER TABLE cappe_posts DROP CONSTRAINT IF EXISTS ck_cappe_posts_format, "
    "DROP CONSTRAINT IF EXISTS ck_cappe_posts_layout, DROP CONSTRAINT IF EXISTS ck_cappe_posts_access",
    "ALTER TABLE cappe_posts "
    "DROP COLUMN IF EXISTS hidden_reason, DROP COLUMN IF EXISTS hidden_at, "
    "DROP COLUMN IF EXISTS reading_minutes, DROP COLUMN IF EXISTS word_count, DROP COLUMN IF EXISTS byline, "
    "DROP COLUMN IF EXISTS cover_asset_id, DROP COLUMN IF EXISTS access, DROP COLUMN IF EXISTS layout, "
    "DROP COLUMN IF EXISTS topic, DROP COLUMN IF EXISTS kicker, DROP COLUMN IF EXISTS content, "
    "DROP COLUMN IF EXISTS format",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
