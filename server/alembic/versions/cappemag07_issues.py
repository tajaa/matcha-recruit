"""Cappe magazines — issues: a designed cover and contents per issue.

An issue gathers a magazine's stories into one numbered book: a cover the
writer designs, a contents page, then the stories in order. Stories still
publish on their own; an issue releases the drafts it holds.

  * `cappe_magazine_issues` — one row per issue: its `number` (the address,
    `/issues/<number>`, unique per magazine), title, `status` (draft or
    released), the `cover` and `contents` designs (JSON shaped by
    `services/magazine/issue_schema.py`), a `cover_image` snapshot for places
    outside the magazine's pages, and an admin takedown (`hidden_at`);
  * `cappe_magazine_issue_stories` — the stories in an issue, in order, each
    with its section and contents line. A story is in at most one issue;
  * `cappe_magazine_issue_assets` — the library pictures an issue's cover uses,
    so the library refuses to delete them (the issue side of
    `cappe_post_assets`).

The downgrade drops the three tables (and every issue with them).

Revision ID: cappemag07
Revises: cappemag06
Create Date: 2026-10-21
"""
from alembic import op

revision = "cappemag07"
down_revision = "cappemag06"
branch_labels = None
depends_on = None

_UPGRADE = [
    """
    CREATE TABLE IF NOT EXISTS cappe_magazine_issues (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        number INTEGER NOT NULL CHECK (number BETWEEN 1 AND 9999),
        title VARCHAR(120),
        status VARCHAR(10) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'released')),
        released_at TIMESTAMPTZ,
        cover JSONB NOT NULL DEFAULT '{}'::jsonb,
        contents JSONB NOT NULL DEFAULT '{}'::jsonb,
        cover_image JSONB,
        hidden_at TIMESTAMPTZ,
        hidden_reason VARCHAR(300),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_cappe_magazine_issues_number UNIQUE (site_id, number),
        CONSTRAINT ck_cappe_magazine_issues_released CHECK (status <> 'released' OR released_at IS NOT NULL)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_magazine_issues_live ON cappe_magazine_issues (site_id, released_at DESC) "
    "WHERE status = 'released' AND hidden_at IS NULL",
    """
    CREATE TABLE IF NOT EXISTS cappe_magazine_issue_stories (
        issue_id UUID NOT NULL REFERENCES cappe_magazine_issues(id) ON DELETE CASCADE,
        post_id UUID NOT NULL REFERENCES cappe_posts(id) ON DELETE CASCADE,
        site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        position SMALLINT NOT NULL CHECK (position BETWEEN 0 AND 39),
        section VARCHAR(40),
        contents_line VARCHAR(200),
        PRIMARY KEY (issue_id, post_id),
        CONSTRAINT uq_cappe_magazine_issue_stories_post UNIQUE (post_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_magazine_issue_stories_order "
    "ON cappe_magazine_issue_stories (issue_id, position)",
    """
    CREATE TABLE IF NOT EXISTS cappe_magazine_issue_assets (
        issue_id UUID NOT NULL REFERENCES cappe_magazine_issues(id) ON DELETE CASCADE,
        asset_id UUID NOT NULL REFERENCES cappe_assets(id),
        site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        PRIMARY KEY (issue_id, asset_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_magazine_issue_assets_asset ON cappe_magazine_issue_assets (asset_id)",
]

_DOWNGRADE = [
    "DROP TABLE IF EXISTS cappe_magazine_issue_assets",
    "DROP TABLE IF EXISTS cappe_magazine_issue_stories",
    "DROP TABLE IF EXISTS cappe_magazine_issues",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
