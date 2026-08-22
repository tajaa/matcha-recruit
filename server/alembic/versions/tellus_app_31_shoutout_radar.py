"""Tell-Us shoutout radar detection queue and scheduler switch."""
from alembic import op


revision = "tellus_app_31"
down_revision = "tellus_app_30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS tellus_shoutout_handles (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        brand_id UUID NOT NULL REFERENCES tellus_brands(id) ON DELETE CASCADE,
        platform TEXT NOT NULL CHECK (platform IN ('instagram','tiktok','youtube','facebook','x')),
        handle TEXT NOT NULL CHECK (handle = lower(handle) AND handle !~ '^@'),
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (brand_id, platform, handle)
    )""")
    op.execute("""CREATE TABLE IF NOT EXISTS tellus_shoutout_configs (
        brand_id UUID PRIMARY KEY REFERENCES tellus_brands(id) ON DELETE CASCADE,
        is_enabled BOOLEAN NOT NULL DEFAULT FALSE,
        brand_terms TEXT[] NOT NULL DEFAULT '{}',
        exclude_terms TEXT[] NOT NULL DEFAULT '{}',
        default_store_id UUID,
        offer_title TEXT,
        offer_terms TEXT,
        offer_expiry_days INT NOT NULL DEFAULT 14 CHECK (offer_expiry_days BETWEEN 1 AND 365),
        min_confidence SMALLINT NOT NULL DEFAULT 60 CHECK (min_confidence BETWEEN 0 AND 100),
        lookback_days INT NOT NULL DEFAULT 14 CHECK (lookback_days BETWEEN 1 AND 90),
        last_scanned_at TIMESTAMPTZ,
        next_scan_after TIMESTAMPTZ,
        consecutive_failures INT NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        FOREIGN KEY (default_store_id, brand_id) REFERENCES tellus_stores(id, brand_id) ON DELETE SET NULL,
        CHECK (NOT is_enabled OR (default_store_id IS NOT NULL AND offer_title IS NOT NULL))
    )""")
    op.execute("""CREATE TABLE IF NOT EXISTS tellus_shoutout_scan_runs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        brand_id UUID NOT NULL REFERENCES tellus_brands(id) ON DELETE CASCADE,
        status TEXT NOT NULL CHECK (status IN ('running','completed','failed')),
        trigger TEXT NOT NULL CHECK (trigger IN ('scheduled','admin')),
        started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        finished_at TIMESTAMPTZ,
        gemini_calls INT NOT NULL DEFAULT 0,
        grounding_uris INT NOT NULL DEFAULT 0,
        grounding_resolved INT NOT NULL DEFAULT 0,
        candidates_returned INT NOT NULL DEFAULT 0,
        urls_rejected INT NOT NULL DEFAULT 0,
        mentions_new INT NOT NULL DEFAULT 0,
        mentions_duplicate INT NOT NULL DEFAULT 0,
        error TEXT
    )""")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_shoutout_one_running
        ON tellus_shoutout_scan_runs (brand_id) WHERE status = 'running'""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_tellus_shoutout_runs_brand
        ON tellus_shoutout_scan_runs (brand_id, started_at DESC)""")
    op.execute("""CREATE TABLE IF NOT EXISTS tellus_shoutout_mentions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        brand_id UUID NOT NULL REFERENCES tellus_brands(id) ON DELETE CASCADE,
        platform TEXT NOT NULL CHECK (platform IN ('instagram','tiktok','youtube','facebook','x')),
        post_url TEXT NOT NULL,
        canonical_url TEXT NOT NULL,
        url_fingerprint CHAR(64) NOT NULL,
        author_handle TEXT,
        excerpt TEXT,
        confidence SMALLINT NOT NULL CHECK (confidence BETWEEN 0 AND 100),
        matched_terms TEXT[] NOT NULL DEFAULT '{}',
        corroborated BOOLEAN NOT NULL DEFAULT FALSE,
        grounding_uri TEXT,
        url_verify_status TEXT NOT NULL DEFAULT 'grounded' CHECK (url_verify_status IN ('grounded','uncorroborated','rejected')),
        raw_payload JSONB,
        status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','expired')),
        seen_count INT NOT NULL DEFAULT 1,
        first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        decided_at TIMESTAMPTZ,
        decided_by UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
        offer_id UUID,
        offer_store_id UUID REFERENCES tellus_stores(id) ON DELETE SET NULL,
        consumer_submission_id UUID REFERENCES tellus_loyalty_social_submissions(id) ON DELETE SET NULL,
        UNIQUE (brand_id, url_fingerprint)
    )""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_tellus_shoutout_mentions_queue
        ON tellus_shoutout_mentions (brand_id, status, last_seen_at DESC)""")
    op.execute("ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS last_run_at TIMESTAMP")
    op.execute("""INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES ('tellus_shoutout_scan', 'Tell-Us Shoutout Radar',
                'Searches for corroborated brand shoutouts. Makes live Gemini calls; default off.', false, 10)
        ON CONFLICT (task_key) DO NOTHING""")


def downgrade() -> None:
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'tellus_shoutout_scan'")
    op.execute("DROP TABLE IF EXISTS tellus_shoutout_mentions")
    op.execute("DROP TABLE IF EXISTS tellus_shoutout_scan_runs")
    op.execute("DROP TABLE IF EXISTS tellus_shoutout_configs")
    op.execute("DROP TABLE IF EXISTS tellus_shoutout_handles")
