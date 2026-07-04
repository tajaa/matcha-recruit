"""Add mw_task_history.task_id_text (durable task identity for weekly replay).

`task_id` is `ON DELETE SET NULL` — when a ticket is hard-deleted, EVERY
history row for it (not just the delete event) loses its task_id in one FK
cascade, indistinguishable from every other deleted ticket's now-null rows.
Fine for the existing single-task timeline view (title is cached in
metadata), but the Weekly Work Replay feature groups events BY task across
a project's whole history to fold board state forward — with 2+ tickets
ever deleted, their rows collapse into one confused bucket instead of each
fading out correctly.

`task_id_text` is a plain TEXT copy with no FK, stamped at log time
(`_log_task_history`), so it survives the parent row's deletion. Replay
groups by COALESCE(task_id_text, task_id::text). Additive/nullable — no
backfill of pre-existing rows (their grouping identity for already-deleted
tasks is unrecoverable; going-forward correctness is what this fixes).

Revision ID: mwtaskhtxt01
Revises: posterbrand01
Create Date: 2026-07-04
"""
from alembic import op


revision = "mwtaskhtxt01"
down_revision = "posterbrand01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE mw_task_history ADD COLUMN IF NOT EXISTS task_id_text TEXT"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE mw_task_history DROP COLUMN IF EXISTS task_id_text"
    )
