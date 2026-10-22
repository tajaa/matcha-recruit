"""Cappe — social video: dropped clips cut to size for Reels, resumable publishing.

The owner drops a phone video next to their photos; it is uploaded straight
to S3 (nginx caps proxied bodies at 20 MB), cut to 1080x1920 with ffmpeg on
the worker (blurred background, never cropped) and posted as an Instagram
Reel and a Facebook Reel (a landscape clip also gets a 1920x1080 cut for a
regular Page video).

`cappe_social_assets`
  * one row per dropped video: where the original is (`source_path`, an
    `s3://` path under an unguessable key), what ffprobe found
    (duration, size, audio), three poster `frames` and the `renders`
    (`{"vertical": {...}, "landscape": {...}}`, public CloudFront URLs Meta
    fetches);
  * `status`: uploading → rendering → ready | failed; `deleted` once the
    sweep has removed the files (`expires_at`, and no post still waiting on
    them).

`cappe_social_posts.status` gains `rendering`: a scheduled post that waits
for its video. The render flips it to `scheduled`; the publisher never claims
a `rendering` post.

`cappe_social_post_targets`
  * `state` — where a multi-minute publish is (Instagram's container id while
    Meta processes the video, Facebook's video id), so the next sweep resumes
    instead of uploading again;
  * `claimed_at` — when the publisher took it, so a target left `publishing`
    by a killed worker is put back by the sweep;
  * `content` — per-network copy (filled by the chat composer; empty means
    "use the post's caption").

Plan feature `social_video` on the paid build tiers (the same as
`social_autoreply`). Sweep `cappe_social_media_sweep` seeded ON: it only
recovers stuck renders/targets and removes expired files.

Additive + idempotent. The downgrade returns rendering posts to drafts.

Revision ID: cappesocial02
Revises: cappesocial01
"""
from alembic import op

revision = "cappesocial02"
down_revision = "cappesocial01"
branch_labels = None
depends_on = None

_POST_STATUSES = "'draft', 'scheduled', 'publishing', 'published', 'partial', 'failed', 'cancelled'"

_UPGRADE = [
    """
    CREATE TABLE IF NOT EXISTS cappe_social_assets (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        account_id UUID NOT NULL REFERENCES cappe_accounts(id) ON DELETE CASCADE,
        kind VARCHAR(10) NOT NULL DEFAULT 'video' CHECK (kind IN ('video')),
        status VARCHAR(20) NOT NULL DEFAULT 'uploading'
            CHECK (status IN ('uploading', 'rendering', 'ready', 'failed', 'deleted')),
        filename VARCHAR(200),
        source_path TEXT NOT NULL,
        content_type VARCHAR(40) NOT NULL,
        bytes BIGINT NOT NULL,
        duration_ms INTEGER,
        width INTEGER,
        height INTEGER,
        has_audio BOOLEAN,
        trimmed BOOLEAN NOT NULL DEFAULT false,
        frames JSONB NOT NULL DEFAULT '[]'::jsonb,
        renders JSONB NOT NULL DEFAULT '{}'::jsonb,
        error TEXT,
        render_attempts INTEGER NOT NULL DEFAULT 0,
        render_started_at TIMESTAMPTZ,
        expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '30 days'),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_social_assets_site ON cappe_social_assets (site_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_cappe_social_assets_open "
    "ON cappe_social_assets (status, updated_at) WHERE status IN ('uploading', 'rendering')",
    "CREATE INDEX IF NOT EXISTS idx_cappe_social_assets_expiry "
    "ON cappe_social_assets (expires_at) WHERE status <> 'deleted'",
    "ALTER TABLE cappe_social_posts DROP CONSTRAINT IF EXISTS cappe_social_posts_status_check",
    f"ALTER TABLE cappe_social_posts ADD CONSTRAINT cappe_social_posts_status_check "
    f"CHECK (status IN ({_POST_STATUSES}, 'rendering'))",
    "ALTER TABLE cappe_social_post_targets ADD COLUMN IF NOT EXISTS content JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE cappe_social_post_targets ADD COLUMN IF NOT EXISTS state JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE cappe_social_post_targets ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ",
    "CREATE INDEX IF NOT EXISTS idx_cappe_social_targets_claimed "
    "ON cappe_social_post_targets (claimed_at) WHERE status = 'publishing'",
    # jsonb_build_object, not a JSON literal: op.execute wraps the string in
    # sqlalchemy.text(), which reads ":true" as a bind parameter.
    """
    UPDATE cappe_billing_products SET features = features || jsonb_build_object('social_video', true)
     WHERE code IN ('business', 'pro', 'creator')
    """,
    """
    INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
    VALUES ('cappe_social_media_sweep', 'Cappe Social Media Sweep',
            'Retry stuck video renders, put back posts a restarted worker left publishing, and remove expired video files.',
            true, 50)
    ON CONFLICT (task_key) DO NOTHING
    """,
]

_DOWNGRADE = [
    "DELETE FROM scheduler_settings WHERE task_key = 'cappe_social_media_sweep'",
    "UPDATE cappe_billing_products SET features = features - 'social_video'",
    "DROP INDEX IF EXISTS idx_cappe_social_targets_claimed",
    "ALTER TABLE cappe_social_post_targets DROP COLUMN IF EXISTS claimed_at",
    "ALTER TABLE cappe_social_post_targets DROP COLUMN IF EXISTS state",
    "ALTER TABLE cappe_social_post_targets DROP COLUMN IF EXISTS content",
    "UPDATE cappe_social_posts SET status = 'draft', scheduled_at = NULL WHERE status = 'rendering'",
    "ALTER TABLE cappe_social_posts DROP CONSTRAINT IF EXISTS cappe_social_posts_status_check",
    f"ALTER TABLE cappe_social_posts ADD CONSTRAINT cappe_social_posts_status_check CHECK (status IN ({_POST_STATUSES}))",
    "DROP TABLE IF EXISTS cappe_social_assets",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
