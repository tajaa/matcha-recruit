"""Employee "Ask HR" — portal Q&A sessions + escalation-queue widening.

Adds the two tables the employee-facing Ask HR surface persists to, and widens
`mw_escalated_queries` so an Ask HR hard-stop can be filed into the SAME human
review queue supervisor HR Pilot hard-stops already use (one queue, one dashboard
count, one triage habit — a parallel table would fragment that).

Three changes to `mw_escalated_queries`, each load-bearing:

1. `thread_id` / `message_id` become NULLABLE. They are FKs to `mw_threads` /
   `mw_messages`, and an Ask HR conversation is neither — it lives in
   `ask_hr_sessions` / `ask_hr_messages`. Without this the insert simply cannot
   happen.

2. `ai_mode` VARCHAR(20) → VARCHAR(40). This fixes a live latent bug, not just
   headroom for our own `ask_hr_hard_stop`: `escalation_service.
   create_hr_pilot_compliance_escalation` inserts the literal
   `'hr_pilot_compliance_block'` — 25 characters into a 20-character column, so
   every statutory discipline block raises `StringDataRightTruncation` at insert
   time. The escalation is best-effort at its call site (`messaging.py` logs and
   continues), so it has been failing silently rather than surfacing.

3. `ask_hr_session_id` / `ask_hr_message_id` — the Ask HR analog of hrpilot02's
   `linked_record_*`. The session gets a real FK (SET NULL: losing the session
   must not erase the record that HR was notified); the message id deliberately
   does NOT, matching the `linked_record_id` precedent — the escalation is an
   HR-side record that outlives message pruning.

Set-based DDL only; no data backfill. Reversible.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "askhr01"
down_revision = "hrpilot02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ask_hr_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        # org_id, not company_id: employees are tenant-scoped by employees.org_id
        # (see server/CLAUDE.md) and require_employee_record hands back that column.
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    # The portal's only list query: this employee's sessions, newest first.
    op.create_index("idx_ask_hr_sessions_employee", "ask_hr_sessions",
                    ["employee_id", sa.text("updated_at DESC")])
    # Company-scoped reads (HR-side visibility, retention sweeps).
    op.create_index("idx_ask_hr_sessions_org", "ask_hr_sessions", ["org_id"])

    op.create_table(
        "ask_hr_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ask_hr_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        # citations / dropped_citations / hard_stop_category
        sa.Column("metadata", postgresql.JSONB),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint("role IN ('user','assistant','system')",
                           name="ask_hr_messages_role_check"),
    )
    op.create_index("idx_ask_hr_messages_session", "ask_hr_messages",
                    ["session_id", "created_at"])

    # --- mw_escalated_queries: admit non-thread escalations ------------------
    op.alter_column("mw_escalated_queries", "thread_id", nullable=True)
    op.alter_column("mw_escalated_queries", "message_id", nullable=True)
    op.alter_column("mw_escalated_queries", "ai_mode",
                    type_=sa.String(40), existing_type=sa.String(20))
    op.add_column("mw_escalated_queries",
                  sa.Column("ask_hr_session_id", postgresql.UUID(as_uuid=True),
                            sa.ForeignKey("ask_hr_sessions.id", ondelete="SET NULL")))
    op.add_column("mw_escalated_queries",
                  sa.Column("ask_hr_message_id", postgresql.UUID(as_uuid=True)))


def downgrade() -> None:
    op.drop_column("mw_escalated_queries", "ask_hr_message_id")
    op.drop_column("mw_escalated_queries", "ask_hr_session_id")
    op.alter_column("mw_escalated_queries", "ai_mode",
                    type_=sa.String(20), existing_type=sa.String(40))

    # Restoring NOT NULL requires no orphan rows. Ask HR escalations have NULL
    # thread_id by construction, so drop them first — they are unreachable under
    # the old schema anyway. Set-based, no loop.
    op.execute("DELETE FROM mw_escalated_queries WHERE thread_id IS NULL OR message_id IS NULL")
    op.alter_column("mw_escalated_queries", "thread_id", nullable=False)
    op.alter_column("mw_escalated_queries", "message_id", nullable=False)

    op.drop_index("idx_ask_hr_messages_session", table_name="ask_hr_messages")
    op.drop_table("ask_hr_messages")
    op.drop_index("idx_ask_hr_sessions_org", table_name="ask_hr_sessions")
    op.drop_index("idx_ask_hr_sessions_employee", table_name="ask_hr_sessions")
    op.drop_table("ask_hr_sessions")
