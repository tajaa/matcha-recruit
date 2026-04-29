"""Backfill pre-mw_projects threads into mw_projects.

Before migration zx2y3z4a5b6c (2026-03-30), matcha-work "projects" lived as
mw_threads rows whose current_state held project_title + project_sections.
That migration created the mw_projects table and added project_id to
mw_threads but shipped no backfill. After commit 89dcf2c added
"project_id IS NULL" to the standalone threads list, those legacy rows
appear as plain chats in the threads panel and are absent from the
projects panel. This migration creates a matching mw_projects row for
each candidate thread, links the thread via project_id, and seeds the
creator as an active owner-collaborator (so admin users — who list via
collaborator membership only — see the migrated project too).

Revision ID: zzze1f2g3h4i5
Revises: zzzd0e1f2g3h4
Create Date: 2026-04-28
"""
import json

from alembic import op
from sqlalchemy import text

revision = "zzze1f2g3h4i5"
down_revision = "zzzd0e1f2g3h4"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()

    # Cast new_sections to text in the SELECT so asyncpg returns a JSON
    # string we can re-encode and pass back through a :sections::jsonb
    # cast on the INSERT. Without the round-trip cast asyncpg pulls the
    # JSONB column back as a Python list, then refuses to encode the
    # list when bound as a parameter ("'list' object has no attribute
    # 'encode'").
    candidates = bind.execute(text("""
        SELECT id, company_id, created_by, title,
               COALESCE(NULLIF(current_state->>'project_title', ''), title, 'Untitled Project') AS new_title,
               COALESCE(current_state->'project_sections', '[]'::jsonb)::text AS new_sections,
               created_at, updated_at
        FROM mw_threads
        WHERE project_id IS NULL
          AND (current_state ? 'project_sections' OR current_state ? 'project_title')
    """)).fetchall()

    for row in candidates:
        # new_sections is a JSON-encoded string from the SELECT cast.
        # If somehow it came back as a list (e.g. driver auto-decoded),
        # re-encode defensively.
        sections_json = row.new_sections
        if not isinstance(sections_json, str):
            sections_json = json.dumps(sections_json or [])

        new_project_id = bind.execute(text("""
            INSERT INTO mw_projects (
                company_id, created_by, title, project_type,
                sections, status, created_at, updated_at
            )
            VALUES (
                :company_id, :created_by, :title, 'general',
                :sections::jsonb, 'active', :created_at, :updated_at
            )
            RETURNING id
        """), {
            "company_id": row.company_id,
            "created_by": row.created_by,
            "title": row.new_title,
            "sections": sections_json,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }).scalar()

        bind.execute(text("""
            UPDATE mw_threads
               SET project_id = :project_id
             WHERE id = :thread_id
        """), {"project_id": new_project_id, "thread_id": row.id})

        bind.execute(text("""
            INSERT INTO mw_project_collaborators (
                project_id, user_id, invited_by, role, status
            )
            VALUES (:project_id, :user_id, :user_id, 'owner', 'active')
            ON CONFLICT (project_id, user_id) DO UPDATE SET status = 'active'
        """), {"project_id": new_project_id, "user_id": row.created_by})


def downgrade():
    # No-op. Legacy threads can't be losslessly restored — the projects
    # table now owns their title/sections and dropping the parent rows
    # would break the FK on mw_threads.project_id (ON DELETE SET NULL
    # would orphan threads, not undo the merge). Leave migrated rows in
    # place if rolling back schema changes downstream.
    pass
