"""Persist public contact / consultation form submissions.

The "Book a Consultation" + "Request a Demo" / contact flows were email-only
(POST /contact → Gmail send). A failed/expired Gmail token silently dropped the
lead. This table captures every submission so a lead is never lost even when the
email backend fails; the email send becomes best-effort on top of it.

Revision ID: contactsub01
Revises: chcallrace01
Create Date: 2026-06-10
"""
from alembic import op


revision = "contactsub01"
down_revision = "chcallrace01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS contact_submissions (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            kind            TEXT NOT NULL DEFAULT 'contact',
            company_name    TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            email           TEXT NOT NULL,
            description     TEXT NOT NULL,
            preferred_date  TEXT,
            preferred_time  TEXT,
            source          TEXT,
            ip              TEXT,
            email_sent      BOOLEAN NOT NULL DEFAULT FALSE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_contact_submissions_created_at "
        "ON contact_submissions(created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contact_submissions")
