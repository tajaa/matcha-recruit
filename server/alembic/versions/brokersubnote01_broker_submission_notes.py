"""Add broker_submission_notes (broker-authored commentary on a client's carrier submission).

Lets a broker annotate a client's underwriting submission before handing the
PDF to carriers — a free-text cover memo ("thoughts") plus labeled annotations
that explain specific scores / steps the client took to improve. Keyed per
(broker, subject) where subject is an on-platform company or an off-platform
Broker Pro client, so the same editor serves both surfaces. Read back into the
submission PDF renderer as a "Broker Commentary" section.

Revision ID: brokersubnote01
Revises: irinforeq01
Create Date: 2026-07-03
"""
from alembic import op


revision = "brokersubnote01"
down_revision = "irinforeq01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_submission_notes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            broker_id UUID NOT NULL,
            subject_type VARCHAR(16) NOT NULL
                CHECK (subject_type IN ('company', 'external')),
            subject_id UUID NOT NULL,
            cover_note TEXT NOT NULL DEFAULT '',
            annotations JSONB NOT NULL DEFAULT '[]'::jsonb,
            updated_by UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (broker_id, subject_type, subject_id)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS broker_submission_notes")
