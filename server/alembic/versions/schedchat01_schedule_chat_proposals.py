"""schedule chat: @huume channel-scheduling proposals

Backs the @huume channel-scheduling flow (`services/scheduling/
schedule_chat.py`): a manager says "@huume I need an opener and a closer for
our La Jolla store next week" in a werk channel, Huume parses the request
(one Gemini call, PARSE ONLY — every compliance verdict comes from the
codified `services/scheduling/schedule_compliance.py` engine, never from
Gemini), resolves locations/templates/dates/candidates deterministically,
and posts a proposal pill. This table is the proposal's persisted state
between that pill and the manager's reply.

`confirm_message_id` mirrors `ems_events.clarify_message_id` from `ems01`:
the atomic-claim arming column. `channels_ws.py:_bg_schedule_reply` does
`UPDATE schedule_chat_proposals SET confirm_message_id = NULL WHERE
confirm_message_id = $reply_uuid AND status IN ('proposed','clarifying')` —
the partial unique index below is what makes that a single indexed probe and
what guarantees at most one proposal is ever waiting on a given pill. First
reply to a pill wins; a later reply to the same (now-disarmed) pill misses
the claim and falls through to the normal @huume mention fork, same as a
stale EMS clarify pill.

`status='clarifying'` is this table's OWN clarify loop (ambiguous location,
no times, ambiguous employee name) — a separate concept from EMS's
`clarify_message_id` question-in-pill-text mechanism (the `\n🤔 ` marker):
a schedule clarify question round-trips through `proposal.clarify_question`
on this row, never through pill-text parsing, so it needs no marker of its
own. `clarify_rounds` caps that loop (2, same as EMS) before bailing the
manager to the schedule page.

There is no bootstrap mirror for this table, matching `schedule_shifts` and
its siblings — the whole `employee_schedule` family is Alembic-only.

Revision ID: schedchat01
Revises: ems01
Create Date: 2026-07-31
"""

from alembic import op


revision = "schedchat01"
down_revision = "ems01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_chat_proposals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            channel_id UUID REFERENCES channels(id) ON DELETE SET NULL,
            source_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'proposed'
                CHECK (status IN ('clarifying', 'proposed', 'confirmed', 'cancelled', 'expired')),
            proposal JSONB NOT NULL DEFAULT '{}'::jsonb,
            parse JSONB,
            clarify_rounds SMALLINT NOT NULL DEFAULT 0,
            confirm_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            created_shift_ids UUID[],
            confirmed_by UUID REFERENCES users(id) ON DELETE SET NULL,
            confirmed_at TIMESTAMPTZ,
            token_usage JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uniq_schedule_chat_proposal_confirm "
        "ON schedule_chat_proposals(confirm_message_id) WHERE confirm_message_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedule_chat_proposals_company "
        "ON schedule_chat_proposals(company_id, created_at DESC)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS schedule_chat_proposals")
