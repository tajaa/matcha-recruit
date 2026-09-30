"""Espresso assistant: a private conversation per person.

Revision ID: agentrt02
Revises: agentrt01
Create Date: 2026-09-29

A fourth channel scope, `assistant`: one private channel per person per
company, owned by `assistant_user_id`. Every message in it is addressed to
Espresso, so no mention is needed, and nobody else can be added. It is where
the abilities that touch a person's own data (email, calendar) are allowed to
run.

The downgrade deletes every private conversation and its messages.
"""
from alembic import op


revision = "agentrt02"
down_revision = "agentrt01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE channels
            ADD COLUMN IF NOT EXISTS assistant_user_id UUID REFERENCES users(id) ON DELETE CASCADE
    """)
    op.execute("ALTER TABLE channels DROP CONSTRAINT IF EXISTS channels_channel_scope_check")
    op.execute("""
        ALTER TABLE channels ADD CONSTRAINT channels_channel_scope_check
            CHECK (channel_scope IN ('operations', 'project_discussion', 'community', 'assistant'))
    """)
    op.execute("ALTER TABLE channels DROP CONSTRAINT IF EXISTS channels_assistant_owner")
    op.execute("""
        ALTER TABLE channels ADD CONSTRAINT channels_assistant_owner
            CHECK ((channel_scope = 'assistant') = (assistant_user_id IS NOT NULL))
    """)
    op.execute("ALTER TABLE channels DROP CONSTRAINT IF EXISTS channels_assistant_private")
    op.execute("""
        ALTER TABLE channels ADD CONSTRAINT channels_assistant_private
            CHECK (channel_scope <> 'assistant' OR visibility = 'private')
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_channels_assistant_user
            ON channels(company_id, assistant_user_id)
            WHERE channel_scope = 'assistant'
    """)


def downgrade():
    op.execute("DELETE FROM channels WHERE channel_scope = 'assistant'")
    op.execute("DROP INDEX IF EXISTS uq_channels_assistant_user")
    op.execute("ALTER TABLE channels DROP CONSTRAINT IF EXISTS channels_assistant_private")
    op.execute("ALTER TABLE channels DROP CONSTRAINT IF EXISTS channels_assistant_owner")
    op.execute("ALTER TABLE channels DROP CONSTRAINT IF EXISTS channels_channel_scope_check")
    op.execute("""
        ALTER TABLE channels ADD CONSTRAINT channels_channel_scope_check
            CHECK (channel_scope IN ('operations', 'project_discussion', 'community'))
    """)
    op.execute("ALTER TABLE channels DROP COLUMN IF EXISTS assistant_user_id")
