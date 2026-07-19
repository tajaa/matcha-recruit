"""add hr_proactive_push_log + seed hr_proactive_push scheduler row

Backs the proactive-push worker (app/workers/tasks/hr_proactive_push.py), which
opens a pre-briefed HR Pilot thread ahead of an HR event instead of waiting for a
supervisor to think to ask: an employee returning from leave, a discipline record
reaching its review/expiry date, handbook signatures going unreturned.

  - hr_proactive_push_log: the idempotency ledger. The thread itself cannot be
    the dedupe key — it persists after the event is handled, and it can be
    renamed or archived by the user, so "has a thread already been opened for
    this?" is not answerable from mw_threads. The UNIQUE here is a same-day
    safety net; the real per-trigger semantics live in the worker (one-shot for
    deadline events, weekly for the pending-signature digest).
  - scheduler_settings row 'hr_proactive_push', seeded DISABLED (repo
    convention — the user enables it from /admin when ready). It appears in the
    /admin Automation tab automatically, which reads the whole table.

`subject_id` is polymorphic across triggers (a leave_requests id, a
progressive_discipline id, or the company id for the aggregate digest) and so
carries NO foreign key, matching the linked_record_id precedent in hrpilot02.
`thread_id` likewise: the ledger is an audit of what we sent, and it must
outlive a thread the user deletes.

Revision ID: hrpush01
Revises: askhr01
Create Date: 2026-07-19
"""

from alembic import op


revision = "hrpush01"
down_revision = "askhr01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_proactive_push_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            trigger_kind VARCHAR(40) NOT NULL,
            subject_id UUID NOT NULL,
            thread_id UUID,
            sent_on DATE NOT NULL DEFAULT CURRENT_DATE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (company_id, trigger_kind, subject_id, sent_on)
        );
        """
    )
    # The one-shot sweeps ask "have we EVER pushed this subject?", which is a
    # lookup on (trigger_kind, subject_id) with no date bound — the UNIQUE above
    # leads with company_id and can't serve it.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_hr_proactive_push_log_subject "
        "ON hr_proactive_push_log(trigger_kind, subject_id);"
    )
    op.execute(
        """
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES (
            'hr_proactive_push',
            'HR Pilot Proactive Push',
            'Opens a pre-briefed HR Pilot thread ahead of an HR event: an employee '
            'returning from leave, a discipline record reaching its review or expiry '
            'date, and a weekly digest of unreturned handbook/policy signatures. '
            'Best-effort; default off.',
            false,
            100
        )
        ON CONFLICT (task_key) DO NOTHING;
        """
    )


def downgrade():
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'hr_proactive_push'")
    op.execute("DROP TABLE IF EXISTS hr_proactive_push_log")
