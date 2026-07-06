"""Handbook Pilot — grounded conversational handbook/policy generation

Revision ID: handbookpilot01
Revises: legaldef03
Create Date: 2026-07-06

Backs the "Handbook Pilot" feature (Pro + Matcha-X): a business admin opens a
generation session, converses with an AI grounded in the company's handbook
profile + jurisdiction/compliance requirements + existing handbooks/policies,
and iteratively drafts handbook sections and standalone policies. The session
persists the transcript; AI-authored candidate artifacts persist as `drafts`
that the admin reviews/edits and then PROMOTES into the real handbooks /
policies tables as drafts. Every mutation/generation/promotion is audit-logged.

Modeled on the Broker Pilot / Legal Pilot schema (`brokerpilot01` / `legaldef01`)
minus the document-upload surface — Handbook Pilot grounds on internal records,
not ad-hoc uploads. Packet/PDF export is a later add-on (no table yet).

NOTE: the alembic history on this branch has multiple leaves; `down_revision`
is set to `legaldef03`, the tip of the pilot-family chain
(`adminupd01 -> brokerpilot01 -> legaldef03`) and a verified head at authoring
time. Confirm the correct head for your environment before `alembic upgrade`.
"""

from alembic import op


revision = "handbookpilot01"
down_revision = "legaldef03"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS handbook_pilot_sessions (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id  UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            title       VARCHAR(300) NOT NULL,
            goal        TEXT,
            industry    VARCHAR(60),
            scopes      JSONB,
            status      VARCHAR(20) NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active','closed')),
            created_by  UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            closed_at   TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_handbook_pilot_sessions_company "
        "ON handbook_pilot_sessions(company_id, updated_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS handbook_pilot_messages (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID NOT NULL REFERENCES handbook_pilot_sessions(id) ON DELETE CASCADE,
            role       VARCHAR(16) NOT NULL
                         CHECK (role IN ('user','assistant','system')),
            content    TEXT NOT NULL,
            metadata   JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_handbook_pilot_messages_session "
        "ON handbook_pilot_messages(session_id, created_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS handbook_pilot_drafts (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id         UUID NOT NULL REFERENCES handbook_pilot_sessions(id) ON DELETE CASCADE,
            -- Denormalized so promotion + tenant checks never need the session join.
            company_id         UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            kind               VARCHAR(20) NOT NULL
                                 CHECK (kind IN ('handbook_section','policy')),
            title              VARCHAR(300) NOT NULL,
            section_key        VARCHAR(120),
            content            TEXT NOT NULL DEFAULT '',
            jurisdiction_scope JSONB,
            citations          JSONB,
            status             VARCHAR(16) NOT NULL DEFAULT 'pending'
                                 CHECK (status IN ('pending','promoted','discarded')),
            promoted_ref       JSONB,
            created_by         UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_handbook_pilot_drafts_session "
        "ON handbook_pilot_drafts(session_id, created_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS handbook_pilot_audit_log (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID REFERENCES handbook_pilot_sessions(id) ON DELETE CASCADE,
            user_id    UUID REFERENCES users(id) ON DELETE SET NULL,
            action     VARCHAR(50) NOT NULL,
            details    JSONB,
            ip_address VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_handbook_pilot_audit_session "
        "ON handbook_pilot_audit_log(session_id, created_at)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS handbook_pilot_audit_log")
    op.execute("DROP TABLE IF EXISTS handbook_pilot_drafts")
    op.execute("DROP TABLE IF EXISTS handbook_pilot_messages")
    op.execute("DROP TABLE IF EXISTS handbook_pilot_sessions")
