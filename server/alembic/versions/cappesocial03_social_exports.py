"""Cappe — social exports: a dropped video cut for each platform to download.

TikTok and YouTube can't be posted to through their APIs until their app
audits pass, so the owner downloads a file made for each (and for Instagram)
and uploads it by hand: "prepare this for all platforms", optionally with the
spoken words burned in as captions.

`cappe_social_exports`
  * one row per video per request: which `platforms`, whether `captions`;
  * `targets` — `{platform: recipe key}` (the three vertical apps share one
    1080x1920 file; YouTube gets 1920x1080 for a clearly landscape clip);
  * `outputs` — `{recipe key: {url, key, width, height, duration_ms, bytes,
    trimmed, shared}}` or `{error}`, filled one cut at a time, so a worker
    restarted mid-export resumes; `srt` — the captions file for YouTube;
  * `texts` — the words to paste per platform (TikTok caption + hashtags,
    YouTube title/description/tags, Instagram caption);
  * `step` — what the running task is doing, so a timeout fails only that
    step; `attempts` — task runs so far (one step each);
  * `status`: queued → working → ready | partial | failed; `deleted` once
    the sweep removes the files (`expires_at`).

`cappe_social_assets.transcript` — the clip's timed words, kept with the
video so any number of exports transcribe it once.

No feature row (the plan feature is `social_video`, from cappesocial02) and
no scheduler row (the existing `cappe_social_media_sweep` recovers exports).

Additive + idempotent; the downgrade drops both.

Revision ID: cappesocial03
Revises: cappesocial02
"""
from alembic import op

revision = "cappesocial03"
down_revision = "cappesocial02"
branch_labels = None
depends_on = None

_UPGRADE = [
    """
    CREATE TABLE IF NOT EXISTS cappe_social_exports (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        account_id UUID NOT NULL REFERENCES cappe_accounts(id) ON DELETE CASCADE,
        asset_id UUID NOT NULL REFERENCES cappe_social_assets(id) ON DELETE CASCADE,
        status VARCHAR(10) NOT NULL DEFAULT 'queued'
            CHECK (status IN ('queued', 'working', 'ready', 'partial', 'failed', 'deleted')),
        platforms TEXT[] NOT NULL,
        captions BOOLEAN NOT NULL DEFAULT false,
        facts JSONB,
        targets JSONB NOT NULL DEFAULT '{}'::jsonb,
        outputs JSONB NOT NULL DEFAULT '{}'::jsonb,
        srt JSONB,
        texts JSONB NOT NULL DEFAULT '{}'::jsonb,
        warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
        step JSONB,
        provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
        error TEXT,
        attempts INTEGER NOT NULL DEFAULT 0,
        started_at TIMESTAMPTZ,
        expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '30 days'),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_social_exports_site ON cappe_social_exports (site_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_cappe_social_exports_asset ON cappe_social_exports (asset_id)",
    "CREATE INDEX IF NOT EXISTS idx_cappe_social_exports_open "
    "ON cappe_social_exports (status, updated_at) WHERE status IN ('queued', 'working')",
    "CREATE INDEX IF NOT EXISTS idx_cappe_social_exports_expiry "
    "ON cappe_social_exports (expires_at) WHERE status <> 'deleted'",
    "ALTER TABLE cappe_social_assets ADD COLUMN IF NOT EXISTS transcript JSONB",
]

_DOWNGRADE = [
    "ALTER TABLE cappe_social_assets DROP COLUMN IF EXISTS transcript",
    "DROP TABLE IF EXISTS cappe_social_exports",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
