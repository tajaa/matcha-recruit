"""Cappe magazines — stories made of pages (Gummfit Studio).

  * `cappe_posts.format` gains `pages`: a story designed in the Studio as
    exact pages, kept as one document in `content` (`{"doc": {...}}`,
    services/magazine/studio/).
  * `cappe_posts.rev` counts every save of a story's content, so two tabs (or
    two people) can't silently overwrite each other: a save names the
    revision it started from and is refused (409) when another came first.
  * `cappe_posts.draft` is a published paged story's working copy: the
    Studio autosaves there, and readers keep the live pages until the owner
    updates them.
  * `cappe_post_revisions` keeps earlier versions of a paged story to go back
    to (each save, each update of the live story, each restore).

Revision ID: cappemag09
Revises: cappemag08
Create Date: 2026-10-22
"""
from alembic import op

revision = "cappemag09"
down_revision = "cappemag08"
branch_labels = None
depends_on = None

_UPGRADE = [
    "ALTER TABLE cappe_posts DROP CONSTRAINT IF EXISTS ck_cappe_posts_format",
    "ALTER TABLE cappe_posts ADD CONSTRAINT ck_cappe_posts_format CHECK (format IN ('markdown', 'blocks', 'pages'))",
    "ALTER TABLE cappe_posts ADD COLUMN IF NOT EXISTS rev INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE cappe_posts ADD COLUMN IF NOT EXISTS draft JSONB",
    """
    CREATE TABLE IF NOT EXISTS cappe_post_revisions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        post_id UUID NOT NULL REFERENCES cappe_posts(id) ON DELETE CASCADE,
        site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        rev INTEGER NOT NULL,
        kind VARCHAR(12) NOT NULL CHECK (kind IN ('save', 'publish', 'restore', 'convert')),
        title VARCHAR(255),
        content JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_post_revisions_post ON cappe_post_revisions (post_id, created_at DESC)",
]

_DOWNGRADE = [
    # A paged story can't be kept as either older format: refuse rather than lose it.
    """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM cappe_posts WHERE format = 'pages') THEN
            RAISE EXCEPTION 'cappe_posts holds paged stories; delete or convert them before downgrading';
        END IF;
    END $$
    """,
    "DROP TABLE IF EXISTS cappe_post_revisions",
    "ALTER TABLE cappe_posts DROP COLUMN IF EXISTS draft",
    "ALTER TABLE cappe_posts DROP COLUMN IF EXISTS rev",
    "ALTER TABLE cappe_posts DROP CONSTRAINT IF EXISTS ck_cappe_posts_format",
    "ALTER TABLE cappe_posts ADD CONSTRAINT ck_cappe_posts_format CHECK (format IN ('markdown', 'blocks'))",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
