"""Espresso Tasks: a form Espresso asks in chat, and the task it starts.

Revision ID: agenttask02
Revises: agenttask01

`ask_form` is a third kind of assistant question (after `ask_user` and
`confirm_action`): a short form built from a playbook's intake fields, posted
in the conversation. Submitting it starts the task with no model run; a typed
reply still answers it the way it answers `ask_user`. `agent_task_id` is the
task the form started (the prompt's id is that task's request id, so a retried
submit gets the same task).

The kind CHECK and the card-scope CHECK were last rewritten by `agentrt01`, an
ancestor of this revision, so dropping and re-adding them here is safe.

The downgrade deletes form prompts, then restores both CHECKs and the index.
"""
from alembic import op

revision = "agenttask02"
down_revision = "agenttask01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE mw_agent_card_prompts
            ADD COLUMN IF NOT EXISTS agent_task_id UUID
                REFERENCES mw_agent_tasks(id) ON DELETE SET NULL
    """)
    op.execute("ALTER TABLE mw_agent_card_prompts DROP CONSTRAINT IF EXISTS mw_agent_card_prompts_kind_check")
    op.execute("""
        ALTER TABLE mw_agent_card_prompts ADD CONSTRAINT mw_agent_card_prompts_kind_check
            CHECK (kind IN ('show_result', 'purchase', 'pick_card', 'ask_user', 'confirm_action', 'ask_form'))
    """)
    op.execute("ALTER TABLE mw_agent_card_prompts DROP CONSTRAINT IF EXISTS mw_agent_card_prompts_card_scope")
    op.execute("""
        ALTER TABLE mw_agent_card_prompts ADD CONSTRAINT mw_agent_card_prompts_card_scope
            CHECK (
                kind IN ('ask_user', 'confirm_action', 'ask_form')
                OR (project_id IS NOT NULL AND task_id IS NOT NULL)
            )
    """)
    op.execute("DROP INDEX IF EXISTS idx_mw_agent_card_prompts_owner_open")
    op.execute("""
        CREATE INDEX idx_mw_agent_card_prompts_owner_open
            ON mw_agent_card_prompts(channel_id, owner_user_id, created_at DESC)
            WHERE status = 'open' AND kind IN ('ask_user', 'confirm_action', 'ask_form')
    """)


def downgrade():
    op.execute("DELETE FROM mw_agent_card_prompts WHERE kind = 'ask_form'")
    op.execute("DROP INDEX IF EXISTS idx_mw_agent_card_prompts_owner_open")
    op.execute("""
        CREATE INDEX idx_mw_agent_card_prompts_owner_open
            ON mw_agent_card_prompts(channel_id, owner_user_id, created_at DESC)
            WHERE status = 'open' AND kind IN ('ask_user', 'confirm_action')
    """)
    op.execute("ALTER TABLE mw_agent_card_prompts DROP CONSTRAINT IF EXISTS mw_agent_card_prompts_card_scope")
    op.execute("""
        ALTER TABLE mw_agent_card_prompts ADD CONSTRAINT mw_agent_card_prompts_card_scope
            CHECK (
                kind IN ('ask_user', 'confirm_action')
                OR (project_id IS NOT NULL AND task_id IS NOT NULL)
            )
    """)
    op.execute("ALTER TABLE mw_agent_card_prompts DROP CONSTRAINT IF EXISTS mw_agent_card_prompts_kind_check")
    op.execute("""
        ALTER TABLE mw_agent_card_prompts ADD CONSTRAINT mw_agent_card_prompts_kind_check
            CHECK (kind IN ('show_result', 'purchase', 'pick_card', 'ask_user', 'confirm_action'))
    """)
    op.execute("ALTER TABLE mw_agent_card_prompts DROP COLUMN IF EXISTS agent_task_id")
