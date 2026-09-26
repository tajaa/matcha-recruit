"""OAuth 2.1 authorization-server tables for the Matcha MCP connector.

Claude and ChatGPT reach Matcha as a remote MCP connector: the model runs on
the person's own Claude / ChatGPT plan, and Matcha only exposes tools over that
person's own data. The connector authenticates the person to Matcha — never the
other way round — so Matcha is the OAuth authorization server here, and these
three tables are its state:

- `oauth_clients`: dynamically registered clients (RFC 7591). One row per
  claude.ai / ChatGPT / Claude Code install that registered with us.
- `oauth_authorization_codes`: single-use, PKCE-bound, 10-minute codes.
- `oauth_tokens`: opaque access + refresh tokens, stored only as sha256. A
  refresh token rotates on every use; replaying a spent one revokes its whole
  `family_id` (the grant), per OAuth 2.1 refresh-token rotation.

Connector tokens are deliberately NOT the app's JWTs: those are capped at a
15-minute access / 12-hour absolute session by design (core/services/
session_tokens.py), which is right for a browser tab and wrong for a connector
that should keep working until the person disconnects it.

Additive and re-runnable. Nothing reads these tables until the connector ships.

Revision ID: mcpconn01
Revises: autoprrt01
"""

from alembic import op


revision = "mcpconn01"
down_revision = "autoprrt01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oauth_clients (
            client_id TEXT PRIMARY KEY,
            client_name TEXT NOT NULL,
            client_uri TEXT,
            logo_uri TEXT,
            redirect_uris JSONB NOT NULL,
            grant_types JSONB NOT NULL,
            scope TEXT,
            token_endpoint_auth_method TEXT NOT NULL,
            client_secret TEXT,
            client_id_issued_at BIGINT NOT NULL,
            client_secret_expires_at BIGINT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oauth_authorization_codes (
            code_hash TEXT PRIMARY KEY,
            client_id TEXT NOT NULL REFERENCES oauth_clients(client_id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            redirect_uri TEXT NOT NULL,
            redirect_uri_provided_explicitly BOOLEAN NOT NULL,
            scope TEXT NOT NULL,
            code_challenge TEXT NOT NULL,
            resource TEXT NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oauth_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            token_hash TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL CHECK (kind IN ('access', 'refresh')),
            family_id UUID NOT NULL,
            client_id TEXT NOT NULL REFERENCES oauth_clients(client_id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            scope TEXT NOT NULL,
            resource TEXT NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            revoked_at TIMESTAMPTZ,
            last_used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS oauth_tokens_user_client_active_idx
            ON oauth_tokens (user_id, client_id)
            WHERE revoked_at IS NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS oauth_tokens_family_idx ON oauth_tokens (family_id)"
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS oauth_authorization_codes_expires_idx
            ON oauth_authorization_codes (expires_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS oauth_tokens")
    op.execute("DROP TABLE IF EXISTS oauth_authorization_codes")
    op.execute("DROP TABLE IF EXISTS oauth_clients")
