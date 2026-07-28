"""Handbook Pilot amend — attribute in-place handbook edits

Revision ID: handbookpilot02
Revises: analysispilot02
Create Date: 2026-07-28

`amend_handbook_sections` (the Handbook Pilot promote-into-existing-handbook
path) and `resolve_change_request` already accept an `updated_by` caller but
had nowhere to write it — `handbooks` only carries `created_by`. Adds
`updated_by` so an in-place edit of a live handbook records who made it.

NOTE: the alembic history on this branch has multiple leaves; `down_revision`
is set to `analysispilot02`, downstream of the `handbookpilot01` chain and a
verified head at authoring time. Confirm the correct head for your
environment before `alembic upgrade`.
"""

from alembic import op


revision = "handbookpilot02"
down_revision = "analysispilot02"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE handbooks ADD COLUMN IF NOT EXISTS updated_by UUID REFERENCES users(id)"
    )


def downgrade():
    op.execute("ALTER TABLE handbooks DROP COLUMN IF EXISTS updated_by")
