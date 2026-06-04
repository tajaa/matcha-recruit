"""broker milestones + outreach cache: positive safety milestones for the Action Center

Revision ID: brokermile01
Revises: mrgheads01
Create Date: 2026-06-04

Adds two tables backing the broker Action Center's net-new surfaces:

- ``broker_milestones`` — positive client safety achievements (incident-free
  streak tiers, DART-free year, TRIR below sector benchmark). One row per
  (broker, company, milestone_key) via a UNIQUE constraint = the de-dup key the
  periodic ``broker_milestones`` Celery task upserts into, and the read source
  for the Milestones tab. ``superseded_at`` is set when a higher tier of the
  same family fires (90 → 180 → 365) or when the underlying streak breaks, so
  only the current achievement shows.

- ``broker_outreach_cache`` — 24h TTL cache for the on-demand AI consultative
  outreach prompts, keyed (broker, company). The Gemini call only runs on a
  cache miss / explicit refresh.

The ``broker_milestones`` scheduler row is seeded DISABLED. Enable explicitly
post-deploy after dev verification:
``UPDATE scheduler_settings SET enabled=true WHERE task_key='broker_milestones'``.
"""

from alembic import op


revision = "brokermile01"
down_revision = "mrgheads01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_milestones (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            broker_id         UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
            company_id        UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            milestone_key     VARCHAR(48) NOT NULL,
            milestone_family  VARCHAR(32) NOT NULL,
            tier              INTEGER,
            title             TEXT NOT NULL,
            detail            TEXT,
            current_value     NUMERIC,
            benchmark_value   NUMERIC,
            metadata          JSONB NOT NULL DEFAULT '{}'::jsonb,
            achieved_at       TIMESTAMP NOT NULL DEFAULT NOW(),
            last_evaluated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            superseded_at     TIMESTAMP,
            is_read           BOOLEAN NOT NULL DEFAULT FALSE,
            CONSTRAINT uq_broker_milestone UNIQUE (broker_id, company_id, milestone_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broker_milestones_broker
            ON broker_milestones(broker_id, achieved_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broker_milestones_active
            ON broker_milestones(broker_id) WHERE superseded_at IS NULL
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_outreach_cache (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            broker_id    UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
            company_id   UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            payload      JSONB NOT NULL,
            generated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            expires_at   TIMESTAMP NOT NULL,
            CONSTRAINT uq_broker_outreach_cache UNIQUE (broker_id, company_id)
        )
        """
    )

    op.execute(
        """
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES (
            'broker_milestones',
            'Broker Milestones',
            'Detects positive client safety milestones (incident-free streaks, DART-free year, TRIR below benchmark) for the broker Action Center.',
            false,
            200
        )
        ON CONFLICT (task_key) DO NOTHING
        """
    )


def downgrade():
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'broker_milestones'")
    op.execute("DROP TABLE IF EXISTS broker_outreach_cache")
    op.execute("DROP INDEX IF EXISTS idx_broker_milestones_active")
    op.execute("DROP INDEX IF EXISTS idx_broker_milestones_broker")
    op.execute("DROP TABLE IF EXISTS broker_milestones")
