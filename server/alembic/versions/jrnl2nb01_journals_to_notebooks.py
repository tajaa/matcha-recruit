"""Migrate diary journals to the Evernote model (notebooks → single-doc notes).

Background: the Werk "Journals" hub previously had one multi-entry kind — the
diary `journal` — where a single `mw_journals` row held many dated
`mw_journal_entries`. Every other kind is a single document (one body entry).
We're collapsing to a strict Evernote model: every note is one document; a
multi-entry diary becomes a NOTEBOOK (folder) whose dated entries each become
their own single-document note inside it.

This is a DATA-ONLY migration (no schema change). It:
  1. Splits every multi-entry diary into a folder + one `note` journal per
     entry (lossless; collaborators copied to each split note).
  2. Flattens single-/zero-entry diaries to `kind='note'`.
  3. Ensures a default root "Notes" notebook per company and files any unfiled
     journals into it.

Every step is guarded, so re-running `upgrade()` is a no-op.

IRREVERSIBLE: the split discards the original diary's journal id and entry
grouping, so it cannot be losslessly recombined — `downgrade()` raises. Take a
DB snapshot before applying.

Revision ID: jrnl2nb01
Revises: contactsub01
Create Date: 2026-06-10
"""
from alembic import op


revision = "jrnl2nb01"
down_revision = "contactsub01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Step 1: split MULTI-entry diaries into notebook + one note per entry ──

    # 1a. One folder per multi-entry diary. gen_random_uuid() in the mapping so
    #     the new folder id can be referenced by both the folder INSERT and the
    #     per-entry note INSERTs below.
    op.execute("DROP TABLE IF EXISTS _jrnl_folder_map")
    op.execute(
        """
        CREATE TEMP TABLE _jrnl_folder_map AS
        SELECT j.id           AS old_journal_id,
               gen_random_uuid() AS new_folder_id,
               j.company_id,
               j.folder_id     AS parent_id,
               j.title,
               j.created_by,
               j.color
        FROM mw_journals j
        WHERE j.kind = 'journal'
          AND (SELECT count(*) FROM mw_journal_entries e WHERE e.journal_id = j.id) > 1
        """
    )
    op.execute(
        """
        INSERT INTO mw_journal_folders (id, company_id, parent_id, name, created_by, color)
        SELECT new_folder_id, company_id, parent_id,
               COALESCE(NULLIF(title, ''), 'Journal'), created_by, color
        FROM _jrnl_folder_map
        """
    )

    # 1b. One new `note` journal per diary entry, mapped so its body entry and
    #     collaborators can be attached. Title falls back to the entry date.
    op.execute("DROP TABLE IF EXISTS _entry_note_map")
    op.execute(
        """
        CREATE TEMP TABLE _entry_note_map AS
        SELECT e.id              AS old_entry_id,
               gen_random_uuid() AS new_journal_id,
               m.new_folder_id,
               j.company_id,
               j.created_by      AS journal_creator,
               j.color           AS journal_color,
               j.status          AS journal_status,
               e.title           AS entry_title,
               e.content         AS entry_content,
               e.entry_date      AS entry_date,
               e.author_id       AS entry_author
        FROM mw_journal_entries e
        JOIN _jrnl_folder_map m ON m.old_journal_id = e.journal_id
        JOIN mw_journals j      ON j.id = e.journal_id
        """
    )
    op.execute(
        """
        INSERT INTO mw_journals (id, company_id, created_by, title, kind, folder_id, color, status)
        SELECT new_journal_id, company_id, journal_creator,
               COALESCE(NULLIF(entry_title, ''), to_char(entry_date, 'YYYY-MM-DD')),
               'note', new_folder_id, journal_color, journal_status
        FROM _entry_note_map
        """
    )
    op.execute(
        """
        INSERT INTO mw_journal_entries (journal_id, author_id, title, content, entry_date)
        SELECT new_journal_id, entry_author, entry_title, entry_content, entry_date
        FROM _entry_note_map
        """
    )

    # 1c. Copy diary collaborators onto EACH split note (no-op when the diary
    #     was private — likely the common case).
    op.execute(
        """
        INSERT INTO mw_journal_collaborators (journal_id, user_id, invited_by, role, status, created_at)
        SELECT enm.new_journal_id, c.user_id, c.invited_by, c.role, c.status, c.created_at
        FROM mw_journal_collaborators c
        JOIN _jrnl_folder_map m  ON m.old_journal_id = c.journal_id
        JOIN _entry_note_map enm ON enm.new_folder_id = m.new_folder_id
        ON CONFLICT (journal_id, user_id) DO NOTHING
        """
    )

    # 1d. Delete the original diaries; their entries + collaborators cascade.
    op.execute(
        "DELETE FROM mw_journals WHERE id IN (SELECT old_journal_id FROM _jrnl_folder_map)"
    )

    # ── Step 2: flatten the remaining single-/zero-entry diaries to notes ──
    op.execute("UPDATE mw_journals SET kind = 'note' WHERE kind = 'journal'")

    # ── Step 3: default "Notes" notebook per company + file orphan notes ──
    # One root "Notes" folder per company that owns any journal (creator = the
    # earliest journal's creator). Skip companies that already have one.
    op.execute(
        """
        INSERT INTO mw_journal_folders (company_id, parent_id, name, created_by)
        SELECT DISTINCT ON (j.company_id) j.company_id, NULL, 'Notes', j.created_by
        FROM mw_journals j
        WHERE NOT EXISTS (
            SELECT 1 FROM mw_journal_folders f
            WHERE f.company_id = j.company_id AND f.parent_id IS NULL AND f.name = 'Notes'
        )
        ORDER BY j.company_id, j.created_at ASC
        """
    )
    op.execute(
        """
        UPDATE mw_journals j
        SET folder_id = (
            SELECT f.id FROM mw_journal_folders f
            WHERE f.company_id = j.company_id AND f.parent_id IS NULL AND f.name = 'Notes'
            LIMIT 1
        )
        WHERE j.folder_id IS NULL
        """
    )

    op.execute("DROP TABLE IF EXISTS _entry_note_map")
    op.execute("DROP TABLE IF EXISTS _jrnl_folder_map")


def downgrade() -> None:
    raise NotImplementedError(
        "jrnl2nb01 split multi-entry diaries into notebooks + per-entry notes; "
        "this is not losslessly reversible. Restore from a DB snapshot instead."
    )
