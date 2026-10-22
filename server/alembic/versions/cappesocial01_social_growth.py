"""Cappe — social growth: connected accounts, scheduled posts, the reply inbox.

A store owner connects the Instagram business account and Facebook Page they
already run (one Meta login, `services/social/providers/meta.py`), drops photos
into a composer, and either publishes now or schedules. Comments and DMs on
those accounts arrive through Meta's webhook into an inbox, and Claude Haiku
drafts replies grounded on the store's own catalog and the owner's notes;
whether a draft goes out by itself is the owner's setting, never the model's.

`cappe_social_connections`
  * one row per connected account (an Instagram account and the Page it hangs
    off are two rows: they publish and receive separately);
  * `access_token_enc` — the Page token, Fernet-encrypted at rest
    (`core.services.secret_crypto`); never returned by any endpoint;
  * `external_id` — the Graph id webhooks name, so an inbound event finds its
    row without a token.

`cappe_social_posts` / `cappe_social_post_targets`
  * a post is the caption + ordered media + optional product; a target is that
    post on one connection, with its own status, attempts and permalink. The
    publisher claims due targets with `FOR UPDATE SKIP LOCKED`, so two sweeps
    never publish the same one twice; the post's status is rolled up from its
    targets (`published` / `partial` / `failed`).

`cappe_social_inbox` / `cappe_social_replies`
  * `(connection_id, external_id)` is unique: Meta re-delivers, and a comment
    counted twice would be answered twice;
  * a reply row is written BEFORE anything is sent (`draft` → `sending` →
    `sent`), with the model and the facts it was grounded on, so what went out
    under the owner's name is always on record.

`cappe_social_settings` — one row per site (`autoreply_mode` off / review /
auto, the owner's notes, tone, hourly cap, words that always escalate).

Plan features: `social` (publishing + scheduling) on every plan; the AI
inbox `social_autoreply` on the paid build tiers. The publisher sweep is seeded
ON (it is idle without a connected account and a due post); metrics seeded off.

Additive + idempotent. The downgrade drops the tables and both features.

Revision ID: cappesocial01
Revises: zzzzcappe54
"""
from alembic import op

revision = "cappesocial01"
down_revision = "zzzzcappe54"
branch_labels = None
depends_on = None

_UPGRADE = [
    """
    CREATE TABLE IF NOT EXISTS cappe_social_connections (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        account_id UUID NOT NULL REFERENCES cappe_accounts(id) ON DELETE CASCADE,
        platform VARCHAR(20) NOT NULL CHECK (platform IN ('instagram', 'facebook')),
        external_id VARCHAR(80) NOT NULL,
        handle VARCHAR(160),
        display_name VARCHAR(255),
        avatar_url TEXT,
        access_token_enc TEXT NOT NULL,
        token_expires_at TIMESTAMPTZ,
        scopes TEXT[] NOT NULL DEFAULT '{}',
        status VARCHAR(20) NOT NULL DEFAULT 'connected'
            CHECK (status IN ('connected', 'expired', 'revoked', 'error')),
        last_error TEXT,
        followers_count INTEGER,
        metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
        metrics_at TIMESTAMPTZ,
        connected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (site_id, platform, external_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_social_connections_site ON cappe_social_connections (site_id)",
    "CREATE INDEX IF NOT EXISTS idx_cappe_social_connections_external "
    "ON cappe_social_connections (platform, external_id)",
    """
    CREATE TABLE IF NOT EXISTS cappe_social_posts (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        caption TEXT NOT NULL DEFAULT '',
        media JSONB NOT NULL DEFAULT '[]'::jsonb,
        link_url TEXT,
        product_id UUID REFERENCES cappe_products(id) ON DELETE SET NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'draft'
            CHECK (status IN ('draft', 'scheduled', 'publishing', 'published', 'partial', 'failed', 'cancelled')),
        scheduled_at TIMESTAMPTZ,
        published_at TIMESTAMPTZ,
        ai_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_social_posts_site "
    "ON cappe_social_posts (site_id, status, scheduled_at)",
    """
    CREATE TABLE IF NOT EXISTS cappe_social_post_targets (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        post_id UUID NOT NULL REFERENCES cappe_social_posts(id) ON DELETE CASCADE,
        connection_id UUID NOT NULL REFERENCES cappe_social_connections(id) ON DELETE CASCADE,
        status VARCHAR(20) NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'publishing', 'published', 'failed', 'cancelled')),
        external_post_id VARCHAR(120),
        permalink TEXT,
        error TEXT,
        attempts INTEGER NOT NULL DEFAULT 0,
        next_attempt_at TIMESTAMPTZ,
        published_at TIMESTAMPTZ,
        metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
        metrics_at TIMESTAMPTZ,
        UNIQUE (post_id, connection_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_social_targets_due "
    "ON cappe_social_post_targets (next_attempt_at) WHERE status = 'pending'",
    """
    CREATE TABLE IF NOT EXISTS cappe_social_inbox (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        connection_id UUID NOT NULL REFERENCES cappe_social_connections(id) ON DELETE CASCADE,
        kind VARCHAR(20) NOT NULL CHECK (kind IN ('comment', 'message')),
        external_id VARCHAR(160) NOT NULL,
        external_parent_id VARCHAR(160),
        author_external_id VARCHAR(120),
        author_name VARCHAR(255),
        text TEXT NOT NULL DEFAULT '',
        received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        status VARCHAR(20) NOT NULL DEFAULT 'new'
            CHECK (status IN ('new', 'drafted', 'replied', 'skipped', 'escalated')),
        classification JSONB NOT NULL DEFAULT '{}'::jsonb,
        raw JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (connection_id, external_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_social_inbox_site "
    "ON cappe_social_inbox (site_id, status, received_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS cappe_social_replies (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        inbox_id UUID NOT NULL REFERENCES cappe_social_inbox(id) ON DELETE CASCADE,
        site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        body TEXT NOT NULL,
        mode VARCHAR(20) NOT NULL CHECK (mode IN ('auto', 'approved', 'manual')),
        status VARCHAR(20) NOT NULL DEFAULT 'draft'
            CHECK (status IN ('draft', 'sending', 'sent', 'failed', 'rejected')),
        model VARCHAR(80),
        grounding JSONB NOT NULL DEFAULT '{}'::jsonb,
        external_reply_id VARCHAR(160),
        error TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        sent_at TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_social_replies_inbox "
    "ON cappe_social_replies (inbox_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_cappe_social_replies_site_sent "
    "ON cappe_social_replies (site_id, sent_at) WHERE mode = 'auto'",
    """
    CREATE TABLE IF NOT EXISTS cappe_social_settings (
        site_id UUID PRIMARY KEY REFERENCES cappe_sites(id) ON DELETE CASCADE,
        autoreply_mode VARCHAR(10) NOT NULL DEFAULT 'off'
            CHECK (autoreply_mode IN ('off', 'review', 'auto')),
        reply_to_comments BOOLEAN NOT NULL DEFAULT TRUE,
        reply_to_messages BOOLEAN NOT NULL DEFAULT TRUE,
        tone VARCHAR(20) NOT NULL DEFAULT 'friendly',
        business_facts TEXT NOT NULL DEFAULT '',
        signature VARCHAR(120),
        default_hashtags TEXT[] NOT NULL DEFAULT '{}',
        max_auto_per_hour INTEGER NOT NULL DEFAULT 20,
        escalate_words TEXT[] NOT NULL DEFAULT '{}',
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    # jsonb_build_object, not a JSON literal: op.execute wraps the string in
    # sqlalchemy.text(), which reads ":true" as a bind parameter.
    """
    UPDATE cappe_billing_products SET features = features || jsonb_build_object('social', true)
     WHERE kind = 'plan'
    """,
    """
    UPDATE cappe_billing_products SET features = features || jsonb_build_object('social_autoreply', true)
     WHERE code IN ('business', 'pro', 'creator')
    """,
    """
    INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
    VALUES
    ('cappe_social_publisher', 'Cappe Social Publisher',
     'Publish scheduled social posts to their connected accounts (sweeps every minute).', true, 50),
    ('cappe_social_metrics', 'Cappe Social Metrics',
     'Refresh follower counts and per-post reach for connected social accounts.', false, 50)
    ON CONFLICT (task_key) DO NOTHING
    """,
]

_DOWNGRADE = [
    "DELETE FROM scheduler_settings WHERE task_key IN ('cappe_social_publisher', 'cappe_social_metrics')",
    "UPDATE cappe_billing_products SET features = features - 'social' - 'social_autoreply'",
    "DROP TABLE IF EXISTS cappe_social_settings",
    "DROP TABLE IF EXISTS cappe_social_replies",
    "DROP TABLE IF EXISTS cappe_social_inbox",
    "DROP TABLE IF EXISTS cappe_social_post_targets",
    "DROP TABLE IF EXISTS cappe_social_posts",
    "DROP TABLE IF EXISTS cappe_social_connections",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
