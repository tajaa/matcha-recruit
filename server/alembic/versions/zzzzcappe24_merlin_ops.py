"""cappe: persist Merlin's op log on the assistant message

An agent turn is expensive (several Gemini calls, screenshots) and, until
now, unrecoverable if the client disconnects mid-stream: `routes/merlin.py`
persists the assistant message (and any generated-image catalog entries)
from CODE THAT RUNS AFTER the SSE generator's `try` block, which a client
disconnect cancels before it ever runs — the ops the turn earned are gone,
and the transcript is left with a question and no answer.

This column is step one: store the validated `ops` alongside the message
that already stores `steps`/`results`, so a later fix can persist from a
`finally` the client's disconnect can't skip, and the panel can offer
"apply these changes" for a turn whose ops never reached the client that
asked for them.

Revision ID: zzzzcappe24
Revises: zzzzcappe23
Create Date: 2026-07-25
"""
from alembic import op

revision = "zzzzcappe24"
down_revision = "zzzzcappe23"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE cappe_merlin_messages ADD COLUMN IF NOT EXISTS ops JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE cappe_merlin_messages DROP COLUMN IF EXISTS ops")
