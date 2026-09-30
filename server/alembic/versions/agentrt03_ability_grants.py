"""Espresso assistant: which abilities a person has switched on.

Revision ID: agentrt03
Revises: agentrt02
Create Date: 2026-09-29

One row per (person, ability). An ability that sends a person's data somewhere
new (email content to the model provider) carries the version of the
disclosure they agreed to; when the disclosure changes, the stored version no
longer matches and the ability reads as off until they agree again.

`ability_key` has no CHECK on purpose: the registry validates it, so adding an
ability never needs a migration.
"""
from alembic import op


revision = "agentrt03"
down_revision = "agentrt02"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_agent_ability_grants (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            ability_key TEXT NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            consent_version TEXT,
            consented_at TIMESTAMPTZ,
            settings JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT mw_agent_ability_grants_consent
                CHECK (consent_version IS NULL OR consented_at IS NOT NULL)
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_mw_agent_ability_grants_user_key
            ON mw_agent_ability_grants(user_id, ability_key)
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS mw_agent_ability_grants")
