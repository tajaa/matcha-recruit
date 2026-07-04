"""Add ir_info_requests.respondent_name (self-typed attestation name).

The IR "Request More Info" public form now captures the responder's own name
alongside a signed-submission disclaimer — the electronic equivalent of signing
the paper form. Distinct from ``recipient_name`` (who the admin addressed the
link to); this is who actually attested and submitted.

Revision ID: irinforesp01
Revises: brokersubnote01
Create Date: 2026-07-03
"""
from alembic import op


revision = "irinforesp01"
down_revision = "brokersubnote01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ir_info_requests ADD COLUMN IF NOT EXISTS respondent_name VARCHAR(255)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE ir_info_requests DROP COLUMN IF EXISTS respondent_name")
