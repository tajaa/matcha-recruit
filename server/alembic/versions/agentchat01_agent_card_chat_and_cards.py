"""Matcha Work: agent-card chat questions, payment-card vault, purchase handoffs.

Revision ID: agentchat01
Revises: agentcard01
Create Date: 2026-09-28

When an agent card finishes, Espresso asks in the project chat whether to
show the result, and can then offer to buy the top pick. Each question is one
`mw_agent_card_prompts` row; replying (threaded or a plain "yes") claims it
exactly once.

`mw_payment_cards` holds a user's saved card: only the card number is kept,
AES-GCM encrypted by the app with a key that is never stored in the database,
bound to its row id and owner. There is deliberately NO CVV column. Card
numbers never go through chat or the model.

`mw_agent_purchase_requests` records each approved purchase: the exact item,
retailer, checkout link and total the user said yes to, and which card (last 4
digits kept as a snapshot). v1 is a handoff only: nothing is charged.
"""
from alembic import op


revision = "agentchat01"
down_revision = "agentcard01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_payment_cards (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            label TEXT NOT NULL,
            brand TEXT NOT NULL,
            last4 TEXT NOT NULL CHECK (last4 ~ '^[0-9]{4}$'),
            exp_month SMALLINT NOT NULL CHECK (exp_month BETWEEN 1 AND 12),
            exp_year SMALLINT NOT NULL CHECK (exp_year BETWEEN 2000 AND 2100),
            pan_ciphertext BYTEA NOT NULL,
            key_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_payment_cards_user
            ON mw_payment_cards(user_id, created_at)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_agent_card_prompts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            project_id UUID NOT NULL REFERENCES mw_projects(id) ON DELETE CASCADE,
            task_id UUID NOT NULL REFERENCES mw_tasks(id) ON DELETE CASCADE,
            run_id UUID NOT NULL REFERENCES mw_project_agent_runs(id) ON DELETE CASCADE,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            kind TEXT NOT NULL CHECK (kind IN ('show_result', 'purchase', 'pick_card')),
            status TEXT NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'answered', 'superseded')),
            owner_user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            answer TEXT,
            answered_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL,
            answered_at TIMESTAMPTZ,
            CONSTRAINT mw_agent_card_prompts_owner
                CHECK (kind = 'show_result' OR owner_user_id IS NOT NULL)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_agent_card_prompts_open
            ON mw_agent_card_prompts(channel_id, created_at DESC)
            WHERE status = 'open'
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_agent_card_prompts_task
            ON mw_agent_card_prompts(task_id)
            WHERE status = 'open'
    """)
    # One "want to see it?" per finished run, so a retried worker never asks twice.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_mw_agent_card_prompts_offer
            ON mw_agent_card_prompts(run_id)
            WHERE kind = 'show_result'
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_agent_purchase_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            project_id UUID NOT NULL REFERENCES mw_projects(id) ON DELETE CASCADE,
            task_id UUID NOT NULL REFERENCES mw_tasks(id) ON DELETE CASCADE,
            run_id UUID REFERENCES mw_project_agent_runs(id) ON DELETE SET NULL,
            prompt_id UUID UNIQUE REFERENCES mw_agent_card_prompts(id) ON DELETE SET NULL,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            card_id UUID REFERENCES mw_payment_cards(id) ON DELETE SET NULL,
            card_last4 TEXT NOT NULL CHECK (card_last4 ~ '^[0-9]{4}$'),
            item_name TEXT NOT NULL,
            retailer TEXT,
            checkout_url TEXT NOT NULL,
            amount NUMERIC(12, 2),
            currency TEXT,
            status TEXT NOT NULL DEFAULT 'handoff' CHECK (status IN ('handoff', 'cancelled')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_agent_purchase_requests_task
            ON mw_agent_purchase_requests(task_id, created_at DESC)
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS mw_agent_purchase_requests")
    op.execute("DROP TABLE IF EXISTS mw_agent_card_prompts")
    op.execute("DROP TABLE IF EXISTS mw_payment_cards")
