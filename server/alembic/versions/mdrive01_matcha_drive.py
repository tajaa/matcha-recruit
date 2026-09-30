"""Matcha Drive: company document store (folders, files, per-folder grants, audit).

Two spaces per company:
  - general: company-wide documents. Business admins/operators manage, every
    member can read.
  - hr: HR-only by default (company owner + clients.is_hr_approver). Anyone
    else needs an explicit per-folder grant.

drive_folder_grants carries per-user exceptions ('view' | 'upload' | 'edit')
that apply to the folder and every descendant. 'upload' is a drop-box: the
holder can add a file but cannot list or read the folder — the GM-submits-a-
draft-into-HR case.

File bytes live in the PRIVATE bucket only (storage.upload_private_file);
downloads are short-lived presigned URLs. extracted_text feeds search and
Huume reads; extraction failure never fails an upload (text_status='failed').

system_key marks the seeded folders (hr_discipline_drafts, ...) that the HR
cases flow files into — they cannot be renamed, moved, or deleted.

Revision ID: mdrive01
Revises: discipapp02
Create Date: 2026-09-29
"""

from alembic import op


revision = "mdrive01"
down_revision = "discipapp02"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS drive_folders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            parent_id UUID REFERENCES drive_folders(id) ON DELETE CASCADE,
            space VARCHAR(10) NOT NULL CHECK (space IN ('general', 'hr')),
            name TEXT NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 200),
            system_key VARCHAR(40),
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_drive_folders_sibling ON drive_folders (
            company_id, space,
            COALESCE(parent_id, '00000000-0000-0000-0000-000000000000'::uuid),
            lower(name)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_drive_folders_system "
        "ON drive_folders (company_id, system_key) WHERE system_key IS NOT NULL"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_drive_folders_parent ON drive_folders (parent_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS drive_files (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            -- NO ACTION, not RESTRICT: checked at end of statement, so a company
                -- delete (which cascades both tables) succeeds. Folder deletes
                -- are refused while non-empty in app code (drive_service).
                folder_id UUID NOT NULL REFERENCES drive_folders(id),
            filename TEXT NOT NULL,
            storage_path TEXT NOT NULL,
            content_type VARCHAR(150),
            file_size BIGINT NOT NULL DEFAULT 0,
            sha256 CHAR(64),
            extracted_text TEXT,
            text_status VARCHAR(12) NOT NULL DEFAULT 'pending'
                CHECK (text_status IN ('pending', 'ok', 'empty', 'failed', 'unsupported')),
            source VARCHAR(16) NOT NULL DEFAULT 'upload'
                CHECK (source IN ('upload', 'google_drive', 'huume', 'system')),
            source_ref TEXT,
            linked_type VARCHAR(20)
                CHECK (linked_type IN ('discipline', 'incident', 'employee', 'hr_case')),
            linked_id UUID,
            uploaded_by UUID REFERENCES users(id) ON DELETE SET NULL,
            deleted_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_drive_files_folder "
        "ON drive_files (company_id, folder_id) WHERE deleted_at IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_drive_files_linked "
        "ON drive_files (linked_type, linked_id) WHERE linked_id IS NOT NULL"
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_drive_files_fts ON drive_files
        USING GIN (to_tsvector('english', filename || ' ' || COALESCE(extracted_text, '')))
        WHERE deleted_at IS NULL
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS drive_folder_grants (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            folder_id UUID NOT NULL REFERENCES drive_folders(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            permission VARCHAR(8) NOT NULL CHECK (permission IN ('view', 'upload', 'edit')),
            granted_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (folder_id, user_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_drive_folder_grants_user "
        "ON drive_folder_grants (company_id, user_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS drive_audit_log (
            id BIGSERIAL PRIMARY KEY,
            company_id UUID NOT NULL,
            file_id UUID,
            folder_id UUID,
            actor_user_id UUID,
            action VARCHAR(24) NOT NULL,
            details JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_drive_audit_company "
        "ON drive_audit_log (company_id, created_at DESC)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS drive_audit_log")
    op.execute("DROP TABLE IF EXISTS drive_folder_grants")
    op.execute("DROP TABLE IF EXISTS drive_files")
    op.execute("DROP TABLE IF EXISTS drive_folders")
