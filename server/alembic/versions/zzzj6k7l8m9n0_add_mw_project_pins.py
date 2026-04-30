"""Add per-user project pin table.

mw_projects.is_pinned was a single global boolean, so pinning a project
in one user's matcha-work workspace propagated to every collaborator's
sidebar. Pin is a personal organisation tool; switch to a (user_id,
project_id) join table.

Backfills mw_project_pins from the legacy global flag for the project's
creator and any active collaborators so existing star state is not lost
on first deploy.

Revision ID: zzzj6k7l8m9n0
Revises: zzzi5j6k7l8m9
Create Date: 2026-04-29
"""
from alembic import op


revision = "zzzj6k7l8m9n0"
down_revision = "zzzi5j6k7l8m9"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_project_pins (
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            project_id UUID NOT NULL REFERENCES mw_projects(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, project_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_project_pins_user
        ON mw_project_pins(user_id, created_at DESC)
    """)

    # Backfill: only the project's creator gets a row for any project
    # where the legacy global flag is set. Backfilling every active
    # collaborator would re-create the shared-pin behaviour we're trying
    # to leave behind — collaborators never explicitly starred those
    # projects, the global flag just leaked. They can re-star themselves.
    op.execute("""
        INSERT INTO mw_project_pins (user_id, project_id)
        SELECT p.created_by, p.id
        FROM mw_projects p
        WHERE p.is_pinned = TRUE
        ON CONFLICT (user_id, project_id) DO NOTHING
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_mw_project_pins_user")
    op.execute("DROP TABLE IF EXISTS mw_project_pins")
