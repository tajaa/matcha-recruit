"""IR incident documents — record how an attachment arrived

Revision ID: irdocvia01
Revises: compliedrem01
Create Date: 2026-07-16

The per-location magic-link intake (`/intake/{token}`) can now carry file
attachments. Those uploads are anonymous — there is no authenticated user, so
`uploaded_by` is NULL on every one of them.

NULL `uploaded_by` is already ambiguous: legacy rows have it too. Without a
positive marker the admin UI cannot tell "a reporter attached this through a
magic link" from "we don't know who uploaded this", which is exactly the
provenance question an incident record exists to answer.

`uploaded_via` is that marker: 'magic_link' | 'authed' | NULL (legacy, pre-dating
the column). Nullable and unconstrained by design — backfilling legacy rows to
'authed' would be a claim we cannot support.
"""

from alembic import op


revision = "irdocvia01"
down_revision = "compliedrem01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ir_incident_documents ADD COLUMN IF NOT EXISTS uploaded_via VARCHAR(30)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE ir_incident_documents DROP COLUMN IF EXISTS uploaded_via")
