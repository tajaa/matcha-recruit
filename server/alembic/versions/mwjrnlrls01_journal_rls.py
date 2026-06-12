"""enforce per-user RLS on Werk journal tables

Revision ID: mwjrnlrls01
Revises: prodcal01
Create Date: 2026-06-11

Adds row-level security policies to the journal tables so isolation is
enforced by PostgreSQL, not just application WHERE clauses. Journals are a
PERSONAL feature: a journal is visible to its `created_by` user or an active
collaborator; folders/notebooks are strictly per-user.

IMPORTANT — these policies are DORMANT until the app connects as a
non-superuser role. The app currently connects as `matcha` (SUPERUSER), and
superusers bypass RLS unconditionally. Enforcement turns on only once
DATABASE_URL is switched to `matcha_app` (LOGIN NOBYPASSRLS, created in
c9cfac81407a). FORCE ROW LEVEL SECURITY is required because `matcha_app` owns
the tables (owners bypass plain RLS without FORCE).

Mirrors the handbook tenant-isolation pattern (init_db ~line 558). Idempotent
(DO/EXCEPTION duplicate_object) so it co-exists with the init_db bootstrap.

`mw_journal_collaborators` is deliberately left WITHOUT RLS: the mw_journals
policy reads it as the membership oracle, so it must stay unfiltered. Access
to it is gated app-side by `_has_access` / `_is_creator`.
"""

from alembic import op


revision = "mwjrnlrls01"
down_revision = "prodcal01"
branch_labels = None
depends_on = None


# Reused session-var predicates (set per-request by get_connection from the
# `app.current_user_id` / `app.is_admin` contextvars — see core/dependencies.py
# set_user_id at the get_current_user dep). current_setting(..., true) returns
# '' (not NULL) when unset, so an unauthenticated connection is fail-closed.
_IS_ADMIN = "current_setting('app.is_admin', true) = 'true'"
_IS_OWNER = "created_by::text = current_setting('app.current_user_id', true)"
_IS_COLLABORATOR = (
    "EXISTS (SELECT 1 FROM mw_journal_collaborators jc "
    "WHERE jc.journal_id = mw_journals.id "
    "AND jc.user_id::text = current_setting('app.current_user_id', true) "
    "AND jc.status = 'active')"
)


def _create_policy(table: str, name: str, using: str, check: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        DO $$ BEGIN
            CREATE POLICY {name} ON {table}
                USING ({using})
                WITH CHECK ({check});
        EXCEPTION WHEN duplicate_object THEN NULL;
                  WHEN undefined_table THEN NULL;
        END $$
    """)


def upgrade() -> None:
    # mw_journals: creator OR active collaborator OR master-admin.
    # WITH CHECK == USING so a collaborator can bump updated_at when they add
    # an entry (create_entry/update_entry do UPDATE mw_journals SET updated_at).
    journal_visible = f"{_IS_OWNER} OR {_IS_ADMIN} OR {_IS_COLLABORATOR}"
    _create_policy("mw_journals", "journal_user_isolation",
                   journal_visible, journal_visible)

    # mw_journal_entries: visible/writable iff the parent journal is visible.
    # The subquery is itself filtered by mw_journals' policy, so this collapses
    # to "entry visible when its journal is visible" — no created_by needed here.
    entry_visible = (
        f"{_IS_ADMIN} OR EXISTS (SELECT 1 FROM mw_journals j "
        "WHERE j.id = mw_journal_entries.journal_id)"
    )
    _create_policy("mw_journal_entries", "entry_user_isolation",
                   entry_visible, entry_visible)

    # mw_journal_folders: strictly per-user (notebooks are personal).
    folder_visible = (
        "created_by::text = current_setting('app.current_user_id', true) "
        f"OR {_IS_ADMIN}"
    )
    _create_policy("mw_journal_folders", "folder_user_isolation",
                   folder_visible, folder_visible)


def downgrade() -> None:
    for table, policy in (
        ("mw_journal_folders", "folder_user_isolation"),
        ("mw_journal_entries", "entry_user_isolation"),
        ("mw_journals", "journal_user_isolation"),
    ):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
