"""Provider-general AI call usage ledger (/admin/ai-usage).

Revision ID: aiusage01
Revises: proddef01
Create Date: 2026-07-21

Every Gemini call in the codebase routes through get_genai_client()
(app/core/services/genai_client.py) — 100+ call sites, one factory. This adds
the table that factory's new instrumentation (app/core/services/ai_usage.py)
writes to: one row per generate_content/generate_content_stream/embed_content
call, with tokens, cost, latency, and outcome, tagged by which feature made
the call (via stack-frame inspection, not a param callers pass).

This is the LEDGER (what did we spend, where). api_rate_limits / rate_limiter.py
is the separate, pre-existing GUARD (are we about to spend too much) and is
untouched — the guard only ever needed a call count, this needs the full row.

`provider` defaults to 'gemini' but is a plain column, not an enum/FK — the
admin dashboard this feeds is explicitly meant to carry Claude etc. later
without a schema change.

Fully reversible.
"""

from alembic import op


revision = "aiusage01"
down_revision = "proddef01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_usage_log (
            id              BIGSERIAL PRIMARY KEY,
            provider        TEXT NOT NULL DEFAULT 'gemini',
            model           TEXT NOT NULL,
            feature         TEXT NOT NULL,
            method          TEXT NOT NULL,
            input_tokens    INTEGER,
            output_tokens   INTEGER,
            thinking_tokens INTEGER,
            cached_tokens   INTEGER,
            cost_usd        NUMERIC(12,6),
            latency_ms      INTEGER,
            status          TEXT NOT NULL DEFAULT 'ok',
            error           TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_usage_created ON ai_usage_log (created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_usage_feature ON ai_usage_log (feature, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_usage_model ON ai_usage_log (model, created_at)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS ai_usage_log")
