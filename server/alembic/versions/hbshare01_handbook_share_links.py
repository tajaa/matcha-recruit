"""Public read-only share links for published handbooks

Revision ID: hbshare01
Revises: limadq02
Create Date: 2026-07-09

A published handbook (``status='active'``) can be handed to anyone via an
unguessable URL — new hires, counsel, a broker — without giving them an account.

Mirrors the ``er_case_export_links`` pattern (unique ``secrets.token_urlsafe(32)``
token, ``revoked_at`` kill switch, optional ``expires_at``, view counters), with
two deliberate differences:

- **No password.** The link is the credential; the token is the only secret.
  Revocation is how you take it back.
- **No stored artifact.** ER exports pin a rendered PDF in S3; a handbook share
  renders live from ``handbook_sections`` at the handbook's ``active_version``,
  so an edit-then-republish is reflected without minting a new link.

Viewing is read-only and non-downloadable by construction: the public endpoint
serves section JSON, never the auth-gated ``GET /handbooks/{id}/pdf``.

The partial unique index enforces at most one *live* link per handbook — a
re-share returns the existing token rather than scattering valid URLs.

NOTE: this branch has multiple alembic leaves — ``down_revision`` was pinned to
the head at authoring time (``limadq02``); confirm before ``alembic upgrade``.
"""

from alembic import op


revision = "hbshare01"
down_revision = "limadq02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS handbook_share_links (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            handbook_id UUID NOT NULL REFERENCES handbooks(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            token VARCHAR(64) NOT NULL UNIQUE,
            created_by UUID REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ,
            view_count INT NOT NULL DEFAULT 0,
            last_viewed_at TIMESTAMPTZ
        )
        """
    )
    # No explicit index on `token`: the UNIQUE constraint above already builds
    # one, and it serves both the share lookup and the per-view counter update.
    # At most one live link per handbook. Revoked rows stay for the audit trail.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_handbook_share_links_live "
        "ON handbook_share_links(handbook_id) WHERE revoked_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS handbook_share_links")
