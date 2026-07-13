"""newsletter idea scratchpad

A lightweight quick-capture space for newsletter concepts. Each row is a
free-form draft idea (title + notes + optional captured media) that an admin
can later convert — via the "Create Newsletter" action — into a structured
newsletter draft whose template enforces at least one visual (media/image).

Revision ID: nlideas01
Revises: zzzzcappe21
Create Date: 2026-07-13
"""

from alembic import op


revision = "nlideas01"
down_revision = "zzzzcappe21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS newsletter_ideas (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title VARCHAR(255) NOT NULL,
            notes TEXT,
            -- Media captured at the idea stage is optional; the mandatory
            -- visual is enforced at conversion time by the template builder.
            media_url TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'idea',
            -- Set once the idea is exported into a newsletter draft.
            newsletter_id UUID REFERENCES newsletters(id) ON DELETE SET NULL,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_newsletter_ideas_status_created
            ON newsletter_ideas(status, created_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_newsletter_ideas_status_created")
    op.execute("DROP TABLE IF EXISTS newsletter_ideas")
