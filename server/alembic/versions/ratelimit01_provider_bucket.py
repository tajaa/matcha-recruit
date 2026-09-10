"""Give api_rate_limits a provider, so one provider's traffic cannot spend another's budget.

`rate_limiter.check_limit` counted `api_rate_limits` with NO filter at all and
compared the total against `settings.gemini_hourly_limit`. Since 2026-08-25 the
Huume and Espresso agent loops have run on OpenAI while still recording through
that limiter, so:

  - OpenAI traffic consumed the Gemini allowance, and
  - a Gemini-heavy compliance sweep could 429 a Huume turn, and vice versa.

One column fixes both directions. Everything already written is Gemini, which
is exactly what the DEFAULT backfills it to — no data migration, no window
where a row is unattributed.

Additive and re-runnable. The index is the one the hot path needs: every
`check_limit` is a COUNT over `(provider, called_at)`, and the existing
`idx_rate_limits_called_at` can no longer serve it alone.

Revision ID: ratelimit01
Revises: aiusage03
"""

from alembic import op


revision = "ratelimit01"
down_revision = "aiusage03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE api_rate_limits
        ADD COLUMN IF NOT EXISTS provider VARCHAR(20) NOT NULL DEFAULT 'gemini'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_rate_limits_provider_called_at
        ON api_rate_limits (provider, called_at)
        """
    )


def downgrade() -> None:
    # Reversible without loss: dropping the column returns every row to the
    # single undifferentiated bucket it was counted in before.
    op.execute("DROP INDEX IF EXISTS idx_rate_limits_provider_called_at")
    op.execute("ALTER TABLE api_rate_limits DROP COLUMN IF EXISTS provider")
