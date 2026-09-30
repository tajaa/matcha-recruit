"""Espresso assistant: chat-invoked agent runs on the existing run tables.

Revision ID: agentrt01
Revises: agentchat02
Create Date: 2026-09-29

A new run kind, `assistant`, on `mw_project_agent_runs`: one run per chat
message, started from a person's private conversation with Espresso or from an
`@espresso` mention in a project chat. No new run or step tables.

  * runs: `project_id` becomes nullable for `assistant` only; such a run must
    say where it came from (`channel_id`, `trigger_message_id`, `surface`).
    One live assistant run per (conversation, person).
  * steps: the kinds and statuses an acting agent needs. A commit is written
    `claimed` before the action and resolved after; `unknown` is a commit whose
    outcome never came back, `held` and `denied` are policy decisions.
  * prompts: `ask_user` and `confirm_action` questions belong to a run, not a
    card, so `project_id` / `task_id` become nullable for those kinds only.

The downgrade deletes assistant runs, their steps and their questions: the
older constraints cannot hold them.
"""
from alembic import op


revision = "agentrt01"
down_revision = "agentchat02"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE mw_project_agent_runs
            ALTER COLUMN project_id DROP NOT NULL,
            ADD COLUMN IF NOT EXISTS surface TEXT,
            ADD COLUMN IF NOT EXISTS abilities TEXT[],
            ADD COLUMN IF NOT EXISTS resume_prompt_id UUID
                REFERENCES mw_agent_card_prompts(id) ON DELETE SET NULL
    """)
    op.execute("ALTER TABLE mw_project_agent_runs DROP CONSTRAINT IF EXISTS mw_project_agent_runs_kind_check")
    op.execute("""
        ALTER TABLE mw_project_agent_runs ADD CONSTRAINT mw_project_agent_runs_kind_check
            CHECK (kind IN ('repo_question', 'task_draft', 'card_agent', 'assistant'))
    """)
    op.execute("ALTER TABLE mw_project_agent_runs DROP CONSTRAINT IF EXISTS mw_project_agent_runs_project_required")
    op.execute("""
        ALTER TABLE mw_project_agent_runs ADD CONSTRAINT mw_project_agent_runs_project_required
            CHECK (kind = 'assistant' OR project_id IS NOT NULL)
    """)
    op.execute("ALTER TABLE mw_project_agent_runs DROP CONSTRAINT IF EXISTS mw_project_agent_runs_assistant_origin")
    op.execute("""
        ALTER TABLE mw_project_agent_runs ADD CONSTRAINT mw_project_agent_runs_assistant_origin
            CHECK (
                kind <> 'assistant'
                OR (channel_id IS NOT NULL AND trigger_message_id IS NOT NULL
                    AND surface IN ('assistant', 'project_chat'))
            )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mw_project_agent_runs_assistant_live
            ON mw_project_agent_runs(channel_id, requested_by)
            WHERE kind = 'assistant' AND status IN ('queued', 'running')
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_project_agent_runs_assistant_user_day
            ON mw_project_agent_runs(requested_by, created_at)
            WHERE kind = 'assistant'
    """)

    op.execute("ALTER TABLE mw_project_agent_steps DROP CONSTRAINT IF EXISTS mw_project_agent_steps_kind_check")
    op.execute("""
        ALTER TABLE mw_project_agent_steps ADD CONSTRAINT mw_project_agent_steps_kind_check
            CHECK (kind IN ('read', 'finish', 'search', 'fetch', 'image',
                            'draft', 'commit', 'ask', 'browse', 'policy'))
    """)
    op.execute("ALTER TABLE mw_project_agent_steps DROP CONSTRAINT IF EXISTS mw_project_agent_steps_status_check")
    op.execute("""
        ALTER TABLE mw_project_agent_steps ADD CONSTRAINT mw_project_agent_steps_status_check
            CHECK (status IN ('ok', 'error', 'skipped', 'claimed', 'unknown', 'denied', 'held'))
    """)
    op.execute("ALTER TABLE mw_project_agent_steps ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ")
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_project_agent_steps_commit
            ON mw_project_agent_steps(tool, created_at DESC)
            WHERE kind = 'commit'
    """)

    op.execute("""
        ALTER TABLE mw_agent_card_prompts
            ALTER COLUMN project_id DROP NOT NULL,
            ALTER COLUMN task_id DROP NOT NULL
    """)
    # Declared inline in agentchat01, so this is Postgres's own name for it. If
    # a database ever named it differently this DROP is a silent no-op and the
    # old CHECK keeps refusing the new kinds: after a rehearsal,
    # `\d mw_agent_card_prompts` must show exactly one CHECK on `kind`.
    op.execute("ALTER TABLE mw_agent_card_prompts DROP CONSTRAINT IF EXISTS mw_agent_card_prompts_kind_check")
    op.execute("""
        ALTER TABLE mw_agent_card_prompts ADD CONSTRAINT mw_agent_card_prompts_kind_check
            CHECK (kind IN ('show_result', 'purchase', 'pick_card', 'ask_user', 'confirm_action'))
    """)
    op.execute("ALTER TABLE mw_agent_card_prompts DROP CONSTRAINT IF EXISTS mw_agent_card_prompts_card_scope")
    op.execute("""
        ALTER TABLE mw_agent_card_prompts ADD CONSTRAINT mw_agent_card_prompts_card_scope
            CHECK (
                kind IN ('ask_user', 'confirm_action')
                OR (project_id IS NOT NULL AND task_id IS NOT NULL)
            )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_agent_card_prompts_owner_open
            ON mw_agent_card_prompts(channel_id, owner_user_id, created_at DESC)
            WHERE status = 'open' AND kind IN ('ask_user', 'confirm_action')
    """)


def downgrade():
    op.execute("DELETE FROM mw_project_agent_runs WHERE kind = 'assistant'")
    op.execute("DELETE FROM mw_agent_card_prompts WHERE kind IN ('ask_user', 'confirm_action')")
    op.execute("""
        DELETE FROM mw_project_agent_steps
        WHERE kind NOT IN ('read', 'finish', 'search', 'fetch', 'image')
           OR status NOT IN ('ok', 'error', 'skipped')
    """)
    op.execute("DROP INDEX IF EXISTS idx_mw_agent_card_prompts_owner_open")
    op.execute("ALTER TABLE mw_agent_card_prompts DROP CONSTRAINT IF EXISTS mw_agent_card_prompts_card_scope")
    op.execute("ALTER TABLE mw_agent_card_prompts DROP CONSTRAINT IF EXISTS mw_agent_card_prompts_kind_check")
    op.execute("""
        ALTER TABLE mw_agent_card_prompts ADD CONSTRAINT mw_agent_card_prompts_kind_check
            CHECK (kind IN ('show_result', 'purchase', 'pick_card'))
    """)
    op.execute("""
        ALTER TABLE mw_agent_card_prompts
            ALTER COLUMN project_id SET NOT NULL,
            ALTER COLUMN task_id SET NOT NULL
    """)
    op.execute("DROP INDEX IF EXISTS idx_mw_project_agent_steps_commit")
    op.execute("ALTER TABLE mw_project_agent_steps DROP COLUMN IF EXISTS resolved_at")
    op.execute("ALTER TABLE mw_project_agent_steps DROP CONSTRAINT IF EXISTS mw_project_agent_steps_status_check")
    op.execute("""
        ALTER TABLE mw_project_agent_steps ADD CONSTRAINT mw_project_agent_steps_status_check
            CHECK (status IN ('ok', 'error', 'skipped'))
    """)
    op.execute("ALTER TABLE mw_project_agent_steps DROP CONSTRAINT IF EXISTS mw_project_agent_steps_kind_check")
    op.execute("""
        ALTER TABLE mw_project_agent_steps ADD CONSTRAINT mw_project_agent_steps_kind_check
            CHECK (kind IN ('read', 'finish', 'search', 'fetch', 'image'))
    """)
    op.execute("DROP INDEX IF EXISTS idx_mw_project_agent_runs_assistant_user_day")
    op.execute("DROP INDEX IF EXISTS idx_mw_project_agent_runs_assistant_live")
    op.execute("ALTER TABLE mw_project_agent_runs DROP CONSTRAINT IF EXISTS mw_project_agent_runs_assistant_origin")
    op.execute("ALTER TABLE mw_project_agent_runs DROP CONSTRAINT IF EXISTS mw_project_agent_runs_project_required")
    op.execute("ALTER TABLE mw_project_agent_runs DROP CONSTRAINT IF EXISTS mw_project_agent_runs_kind_check")
    op.execute("""
        ALTER TABLE mw_project_agent_runs ADD CONSTRAINT mw_project_agent_runs_kind_check
            CHECK (kind IN ('repo_question', 'task_draft', 'card_agent'))
    """)
    op.execute("""
        ALTER TABLE mw_project_agent_runs
            ALTER COLUMN project_id SET NOT NULL,
            DROP COLUMN IF EXISTS resume_prompt_id,
            DROP COLUMN IF EXISTS abilities,
            DROP COLUMN IF EXISTS surface
    """)
