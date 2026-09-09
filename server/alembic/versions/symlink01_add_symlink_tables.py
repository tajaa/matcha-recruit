"""add sym-link tables + seed the two sym-link scheduler rows

Sym-link is a bounded, guided task link (credential/document upload, manager
review, info update/confirmation, or a sender-defined custom checklist). A
sender mints a per-task token; the recipient unlocks it with the company's
weekly-rotating passcode and a Gemini-driven chat collects every required
field + attachment; completion lands a STAGED submission the sender must
confirm before anything writes into a domain table.

Tables:
  - symlink_passcodes    one row per company: the current weekly code (plaintext
                         by necessity — the admin UI displays it; the per-task
                         token is the real credential), rotation schedule, and
                         the optional channel the rotation is announced in.
  - symlinks             the task link. Conversation state (transcript,
                         known_fields) lives HERE — one recipient, one task —
                         so a device switch resumes after re-unlock.
  - symlink_unlocks      one row per successful passcode entry (hashed random
                         unlock token). A passcode rotation does NOT touch
                         these: an unlocked session outlives the rotation.
  - symlink_attachments  S3 objects the recipient uploaded, keyed by spec slot.
  - symlink_submissions  the staged result; status pending -> applied|rejected.
  - symlink_audit_log    the shared <domain>_audit_log shape written through
                         core/services/audit_log.insert_audit_log; NULL user_id
                         for the unauthenticated recipient side.

scheduler_settings rows 'symlink_passcode_rotation' + 'symlink_sweep' are
seeded DISABLED (repo convention).

Revision ID: symlink01
Revises: credcustom01
Create Date: 2026-09-09
"""

from alembic import op


revision = "symlink01"
down_revision = "credcustom01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS symlink_passcodes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL UNIQUE REFERENCES companies(id) ON DELETE CASCADE,
            code VARCHAR(16) NOT NULL,
            rotated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            next_rotation_at TIMESTAMPTZ NOT NULL,
            rotation_weekday SMALLINT NOT NULL DEFAULT 0
                CHECK (rotation_weekday BETWEEN 0 AND 6),
            announce_channel_id UUID NULL REFERENCES channels(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_symlink_passcodes_due "
        "ON symlink_passcodes(next_rotation_at);"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS symlinks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            token VARCHAR(64) NOT NULL UNIQUE,
            kind VARCHAR(32) NOT NULL
                CHECK (kind IN ('credential_upload','manager_review','info_update','custom')),
            title VARCHAR(200) NOT NULL,
            instructions TEXT,
            spec JSONB NOT NULL,
            recipient_name VARCHAR(255) NOT NULL,
            recipient_email VARCHAR(255) NOT NULL,
            employee_id UUID NULL REFERENCES employees(id) ON DELETE SET NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','in_progress','submitted','applied','rejected','revoked','expired')),
            expires_at TIMESTAMPTZ NOT NULL,
            created_by UUID NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            sent_at TIMESTAMPTZ NULL,
            last_sent_at TIMESTAMPTZ NULL,
            first_unlocked_at TIMESTAMPTZ NULL,
            completed_at TIMESTAMPTZ NULL,
            reminder_sent_at TIMESTAMPTZ NULL,
            transcript JSONB NOT NULL DEFAULT '[]'::jsonb,
            known_fields JSONB NOT NULL DEFAULT '{}'::jsonb,
            turn_count INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_symlinks_company_status "
        "ON symlinks(company_id, status);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_symlinks_company_created "
        "ON symlinks(company_id, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_symlinks_open_expiry "
        "ON symlinks(expires_at) WHERE status IN ('pending','in_progress');"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS symlink_unlocks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            symlink_id UUID NOT NULL REFERENCES symlinks(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            unlock_token_hash CHAR(64) NOT NULL UNIQUE,
            unlocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ip VARCHAR(64),
            revoked_at TIMESTAMPTZ NULL
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_symlink_unlocks_link "
        "ON symlink_unlocks(symlink_id);"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS symlink_attachments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            symlink_id UUID NOT NULL REFERENCES symlinks(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            slot VARCHAR(64) NOT NULL,
            storage_path TEXT NOT NULL,
            file_name VARCHAR(255) NOT NULL,
            content_type VARCHAR(120),
            size_bytes INTEGER NOT NULL DEFAULT 0,
            uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            discarded_at TIMESTAMPTZ NULL
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_symlink_attachments_link "
        "ON symlink_attachments(symlink_id) WHERE discarded_at IS NULL;"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS symlink_submissions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            symlink_id UUID NOT NULL UNIQUE REFERENCES symlinks(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            fields JSONB NOT NULL DEFAULT '{}'::jsonb,
            attachment_ids UUID[] NOT NULL DEFAULT '{}',
            submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','applied','rejected')),
            reviewed_by UUID NULL,
            reviewed_at TIMESTAMPTZ NULL,
            review_note TEXT,
            applied_ref JSONB NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_symlink_submissions_company_status "
        "ON symlink_submissions(company_id, status);"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS symlink_audit_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            symlink_id UUID NOT NULL REFERENCES symlinks(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            user_id UUID NULL,
            action VARCHAR(64) NOT NULL,
            entity_type VARCHAR(64),
            entity_id VARCHAR(64),
            details JSONB,
            ip_address VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_symlink_audit_log_link "
        "ON symlink_audit_log(symlink_id, created_at);"
    )
    op.execute(
        """
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES
        (
            'symlink_passcode_rotation',
            'Sym-link passcode rotation',
            'Rotates each company''s weekly sym-link passcode once its next_rotation_at '
            'passes and announces the new code in the chosen Ops channel. Default off.',
            false,
            500
        ),
        (
            'symlink_sweep',
            'Sym-link sweep',
            'Expires sym-links past their expiry and sends a one-shot reminder to '
            'recipients who have not finished within 3 days. Default off.',
            false,
            200
        )
        ON CONFLICT (task_key) DO NOTHING;
        """
    )


def downgrade():
    op.execute(
        "DELETE FROM scheduler_settings "
        "WHERE task_key IN ('symlink_passcode_rotation', 'symlink_sweep')"
    )
    op.execute("DROP TABLE IF EXISTS symlink_audit_log")
    op.execute("DROP TABLE IF EXISTS symlink_submissions")
    op.execute("DROP TABLE IF EXISTS symlink_attachments")
    op.execute("DROP TABLE IF EXISTS symlink_unlocks")
    op.execute("DROP TABLE IF EXISTS symlinks")
    op.execute("DROP TABLE IF EXISTS symlink_passcodes")
