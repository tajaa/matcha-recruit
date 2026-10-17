"""Private Espresso task recap evidence, work leases and delivery ownership.

Revision ID: recap01
Revises: agenttask05
Additive; no historic requests are enrolled. Apply only through the approved
migration workflow. Downgrade removes recap metadata and requires storage cleanup
beforehand; it never deletes the underlying tasks.
"""
from alembic import op

revision = "recap01"
down_revision = "agenttask05"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE mw_job_searches ADD COLUMN recap_generation INTEGER NOT NULL DEFAULT 0 CHECK (recap_generation >= 0)")
    statements = (
        """CREATE TABLE mw_agent_recap_preferences (
            company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            enabled BOOLEAN NOT NULL DEFAULT FALSE, email_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY(company_id, user_id)
        )""",
        """CREATE TABLE mw_agent_recaps (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            root_key TEXT NOT NULL CHECK (octet_length(root_key) <= 200),
            title TEXT NOT NULL CHECK (char_length(title) <= 160),
            state TEXT NOT NULL DEFAULT 'collecting' CHECK (state IN
                ('collecting','waiting','queued','rendering','ready','failed','skipped','expired','deleted')),
            outcome TEXT NOT NULL DEFAULT 'observed',
            manifest JSONB CHECK (octet_length(manifest::text) <= 1048576), manifest_sha256 TEXT,
            output_manifest JSONB CHECK (octet_length(output_manifest::text) <= 32768),
            render_attempts INTEGER NOT NULL DEFAULT 0 CHECK (render_attempts BETWEEN 0 AND 4),
            render_token UUID, lease_until TIMESTAMPTZ, next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            manual_retry_request_id UUID, last_error_code TEXT,
            capture_windows_reserved INTEGER NOT NULL DEFAULT 0 CHECK (capture_windows_reserved BETWEEN 0 AND 10),
            capture_bytes_stored BIGINT NOT NULL DEFAULT 0 CHECK (capture_bytes_stored BETWEEN 0 AND 134217728),
            event_count INTEGER NOT NULL DEFAULT 0 CHECK (event_count BETWEEN 0 AND 128),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            source_completed_at TIMESTAMPTZ, finalize_after TIMESTAMPTZ, ready_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ, deleted_at TIMESTAMPTZ,
            UNIQUE(company_id, owner_user_id, root_key)
        )""",
        """CREATE INDEX idx_recap_owner ON mw_agent_recaps(company_id, owner_user_id, created_at DESC, id)""",
        """CREATE INDEX idx_recap_work ON mw_agent_recaps(state, next_attempt_at) WHERE state IN ('queued','rendering','collecting','waiting')""",
        """CREATE INDEX idx_recap_expiry ON mw_agent_recaps(expires_at) WHERE state = 'ready'""",
        """CREATE TABLE mw_agent_recap_sources (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(), recap_id UUID NOT NULL REFERENCES mw_agent_recaps(id) ON DELETE CASCADE,
            kind TEXT NOT NULL CHECK (kind IN ('run','research','jobs')),
            run_id UUID REFERENCES mw_project_agent_runs(id) ON DELETE CASCADE,
            task_round_id UUID REFERENCES mw_agent_task_rounds(id) ON DELETE CASCADE,
            job_search_id UUID REFERENCES mw_job_searches(id) ON DELETE CASCADE,
            generation INTEGER NOT NULL DEFAULT 0 CHECK (generation >= 0),
            role TEXT NOT NULL DEFAULT 'root' CHECK (role IN ('root','child','continuation','phase')),
            parent_source_id UUID REFERENCES mw_agent_recap_sources(id) ON DELETE SET NULL,
            execution_token UUID,
            semantic_state TEXT NOT NULL DEFAULT 'live' CHECK (semantic_state IN ('live','waiting','terminal')),
            completion_mail_owner TEXT NOT NULL CHECK (completion_mail_owner IN ('legacy','recap','none')),
            mail_payload JSONB CHECK (octet_length(mail_payload::text) <= 65536),
            CHECK ((kind = 'run' AND run_id IS NOT NULL AND task_round_id IS NULL AND job_search_id IS NULL)
                OR (kind = 'research' AND run_id IS NULL AND task_round_id IS NOT NULL AND job_search_id IS NULL)
                OR (kind = 'jobs' AND run_id IS NULL AND task_round_id IS NULL AND job_search_id IS NOT NULL))
        )""",
        """CREATE UNIQUE INDEX uq_recap_run ON mw_agent_recap_sources(run_id) WHERE kind = 'run'""",
        """CREATE UNIQUE INDEX uq_recap_round ON mw_agent_recap_sources(task_round_id) WHERE kind = 'research'""",
        """CREATE UNIQUE INDEX uq_recap_job ON mw_agent_recap_sources(job_search_id, generation) WHERE kind = 'jobs'""",
        """CREATE INDEX idx_recap_sources_root ON mw_agent_recap_sources(recap_id)""",
        """CREATE TABLE mw_agent_recap_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(), recap_id UUID NOT NULL REFERENCES mw_agent_recaps(id) ON DELETE CASCADE,
            source_id UUID NOT NULL REFERENCES mw_agent_recap_sources(id) ON DELETE CASCADE,
            event_key TEXT NOT NULL CHECK (octet_length(event_key) <= 240),
            snapshot JSONB NOT NULL CHECK (octet_length(snapshot::text) <= 16384),
            asset JSONB CHECK (octet_length(asset::text) <= 2048), capture_token UUID,
            occurred_at TIMESTAMPTZ NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(recap_id, event_key)
        )""",
        """CREATE INDEX idx_recap_events_order ON mw_agent_recap_events(recap_id, occurred_at, id)""",
        """CREATE TABLE mw_agent_recap_deliveries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(), recap_id UUID NOT NULL UNIQUE REFERENCES mw_agent_recaps(id) ON DELETE CASCADE,
            state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','sending','retry_wait','sent','unknown','suppressed','failed')),
            attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 3), claim_token UUID, lease_until TIMESTAMPTZ,
            not_before TIMESTAMPTZ NOT NULL DEFAULT NOW(), deadline_at TIMESTAMPTZ,
            provider TEXT, provider_message_id TEXT, sent_at TIMESTAMPTZ, last_error_code TEXT
        )""",
        """CREATE INDEX idx_recap_delivery_due ON mw_agent_recap_deliveries(state, not_before)""",
        """CREATE TABLE mw_agent_recap_cleanup_jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(), bucket TEXT NOT NULL, prefix TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','done')),
            not_before TIMESTAMPTZ NOT NULL DEFAULT NOW(), attempts INTEGER NOT NULL DEFAULT 0,
            UNIQUE(bucket, prefix), CHECK (prefix ~ '^espresso-recaps/[a-f0-9-]+/[a-f0-9-]+/[a-f0-9-]+/')
        )""",
    )
    for statement in statements:
        op.execute(statement)


def downgrade():
    for table in ("cleanup_jobs", "deliveries", "events", "sources", "preferences"):
        op.execute(f"DROP TABLE mw_agent_recap_{table}")
    op.execute("DROP TABLE mw_agent_recaps")
    op.execute("ALTER TABLE mw_job_searches DROP COLUMN recap_generation")
