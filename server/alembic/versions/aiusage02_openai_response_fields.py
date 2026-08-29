"""Store provider response identity and execution fields in the AI ledger.

Revision ID: aiusage02
Revises: aiusage01
Create Date: 2026-08-29

OpenAI Responses returns an authoritative response id, actual model, provider
status, service tier, and token usage. The existing ledger already stores the
model and token counters; these nullable columns retain the remaining provider
facts without changing historical Gemini rows.
"""

from alembic import op


revision = "aiusage02"
down_revision = "aiusage01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE ai_usage_log ADD COLUMN IF NOT EXISTS provider_response_id TEXT")
    op.execute("ALTER TABLE ai_usage_log ADD COLUMN IF NOT EXISTS provider_status TEXT")
    op.execute("ALTER TABLE ai_usage_log ADD COLUMN IF NOT EXISTS service_tier TEXT")


def downgrade():
    op.execute("ALTER TABLE ai_usage_log DROP COLUMN IF EXISTS service_tier")
    op.execute("ALTER TABLE ai_usage_log DROP COLUMN IF EXISTS provider_status")
    op.execute("ALTER TABLE ai_usage_log DROP COLUMN IF EXISTS provider_response_id")
