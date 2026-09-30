"""Espresso assistant: domain registrations.

Revision ID: assistdom01
Revises: assistbuy01
Create Date: 2026-09-30

One row per domain the assistant registered (or tried to) through our Porkbun
account, keyed on the confirmation the person said yes to: `prompt_id` is
UNIQUE, so a second run of the same yes finds this row instead of registering
again. `registering` means the Porkbun call may have been made and its outcome
is not written yet; the next attempt on that approval re-sends it under the
same idempotency key, which Porkbun replays for 24 hours.
"""
from alembic import op


revision = "assistdom01"
down_revision = "assistbuy01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_agent_domain_registrations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            run_id UUID REFERENCES mw_project_agent_runs(id) ON DELETE SET NULL,
            prompt_id UUID UNIQUE REFERENCES mw_agent_card_prompts(id) ON DELETE SET NULL,
            channel_id UUID REFERENCES channels(id) ON DELETE SET NULL,
            domain TEXT NOT NULL,
            cost_cents INTEGER NOT NULL CHECK (cost_cents > 0),
            status TEXT NOT NULL DEFAULT 'registering'
                CHECK (status IN ('registering', 'registered', 'failed')),
            error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_agent_domain_registrations_user
            ON mw_agent_domain_registrations (user_id, created_at DESC)
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS mw_agent_domain_registrations")
