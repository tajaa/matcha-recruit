"""Price OpenAI Luna calls and retain cache-write token usage.

Revision ID: aiusage03
Revises: aiusage02
Create Date: 2026-09-01

Responses already persisted exact input, output, reasoning, and cached-read
tokens. GPT-5.6 also reports cache-write tokens, which have a distinct 1.25x
input rate. Add that counter and backfill historical default-tier Luna rows
from the published token rates so /admin/ai-usage no longer shows them as
unpriced.
"""

from alembic import op


revision = "aiusage03"
down_revision = "aiusage02"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE ai_usage_log "
        "ADD COLUMN IF NOT EXISTS cache_write_tokens INTEGER"
    )
    op.execute(
        """
        WITH raw_parts AS (
            SELECT id,
                   GREATEST(COALESCE(input_tokens, 0), 0)::numeric AS input_count,
                   GREATEST(COALESCE(output_tokens, 0), 0)::numeric AS output_count,
                   LEAST(
                       GREATEST(COALESCE(cached_tokens, 0), 0),
                       GREATEST(COALESCE(input_tokens, 0), 0)
                   )::numeric AS cached_count,
                   GREATEST(COALESCE(cache_write_tokens, 0), 0)::numeric
                       AS raw_cache_write_count
            FROM ai_usage_log
            WHERE provider = 'openai'
              AND model LIKE 'gpt-5.6-luna%'
              AND cost_usd IS NULL
              AND (service_tier IS NULL OR service_tier = 'default')
              AND (input_tokens IS NOT NULL OR output_tokens IS NOT NULL)
        ), token_parts AS (
            SELECT id,
                   input_count,
                   output_count,
                   cached_count,
                   LEAST(
                       raw_cache_write_count,
                       GREATEST(input_count - cached_count, 0)
                   )::numeric AS cache_write_count
            FROM raw_parts
        )
        UPDATE ai_usage_log AS usage
        SET cost_usd = ROUND((
            (
                (parts.input_count - parts.cached_count - parts.cache_write_count) * 0.20
                + parts.cached_count * 0.02
                + parts.cache_write_count * 0.25
            ) * CASE WHEN parts.input_count > 272000 THEN 2.0 ELSE 1.0 END
            + parts.output_count * 1.20
              * CASE WHEN parts.input_count > 272000 THEN 1.5 ELSE 1.0 END
        ) / 1000000, 6)
        FROM token_parts AS parts
        WHERE usage.id = parts.id
        """
    )


def downgrade():
    op.execute(
        """UPDATE ai_usage_log
           SET cost_usd = NULL
           WHERE provider = 'openai' AND model LIKE 'gpt-5.6-luna%'"""
    )
    op.execute(
        "ALTER TABLE ai_usage_log "
        "DROP COLUMN IF EXISTS cache_write_tokens"
    )
