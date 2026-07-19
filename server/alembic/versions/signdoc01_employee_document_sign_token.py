"""Public, no-login token for employee document signatures (handbook acknowledgement)

Revision ID: signdoc01
Revises: hbshare01
Create Date: 2026-07-19

The handbook-distribution email (`send_handbook_acknowledgement_email`) has
always linked to `/portal` — the employee-portal login page — because the
only signing endpoint, `POST /v1/portal/me/documents/{id}/sign`, requires an
authenticated `require_employee_record` session. That's the "signature link
redirects to login" bug: employees who've never logged into the portal (most
of a freshly-onboarded roster) hit a login wall on a link that was supposed
to let them acknowledge a handbook without an account.

Mirrors `hbshare01`'s already-working pattern (unguessable `secrets.
token_urlsafe(32)` token is the credential, no password) rather than
inventing a new one — `policy_signatures.token` is the same idea for the
separate ad-hoc policy-signature-request flow.

One token per `employee_documents` row (not a shared link) because each row
already carries its own signer identity (`employee_id`) — the row IS the
signature request. Nullable + backfilled for existing pending rows so
handbooks already distributed before this migration get a usable link too.

NOTE: this branch has multiple alembic leaves — ``down_revision`` was pinned
to ``hbshare01`` at authoring time; confirm before ``alembic upgrade``.
"""

from alembic import op


revision = "signdoc01"
down_revision = "hbshare01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE employee_documents ADD COLUMN IF NOT EXISTS sign_token VARCHAR(64)"
    )
    # Backfill existing pending/signed rows so already-distributed handbooks
    # (sent before this migration, currently only reachable via portal login)
    # get a working public link too. Two concatenated UUIDs (dashes stripped) =
    # 64 hex chars, unique per row, and NO pgcrypto dependency — gen_random_uuid()
    # is core in PG13+ (used as a column default throughout this schema) whereas
    # gen_random_bytes() would require the pgcrypto extension, which is not enabled.
    op.execute(
        """
        UPDATE employee_documents
        SET sign_token = replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '')
        WHERE sign_token IS NULL
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_employee_documents_sign_token "
        "ON employee_documents(sign_token)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_employee_documents_sign_token")
    op.execute("ALTER TABLE employee_documents DROP COLUMN IF EXISTS sign_token")
