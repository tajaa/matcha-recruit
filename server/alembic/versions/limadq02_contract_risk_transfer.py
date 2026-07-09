"""Contract risk-transfer review (indemnity extraction + insurability verdict)

Revision ID: limadq02
Revises: leadqual01
Create Date: 2026-07-09

Extends ``company_contracts`` (limadq01) with the risk-transfer half of broker
contract review:

- ``contract_type`` / ``governing_state`` / ``project_state`` — extracted
  contract context. ``project_state`` is load-bearing: most construction
  anti-indemnity statutes are anti-waiver (they attach to the project's
  location regardless of the contract's chosen law), so the verdict engine
  considers both states.
- ``storage_path`` — private ``s3://`` URI of the retained source PDF. This
  deliberately reverses limadq01's parse-and-discard: a clause finding
  ("your indemnity is likely void") is unverifiable without the source text.
  Null for manual/legacy rows and when S3 is unavailable at upload time.
- ``risk_transfer`` — extracted indemnity clause (form, direction,
  sole-negligence coverage, defense obligation, verbatim quote + page anchor)
  as JSONB.
- ``confirmed_at`` / ``confirmed_by`` — the Analysis-Pilot-style human-confirm
  gate: verdicts render provisional until a human confirms the extraction, and
  any edit to ``risk_transfer`` resets the confirmation.

No new tables. Gated by the existing ``limit_adequacy`` feature.

NOTE: this branch has multiple alembic leaves — ``down_revision`` was pinned to
the head at authoring time (``leadqual01``); confirm before ``alembic upgrade``.
"""

from alembic import op


revision = "limadq02"
down_revision = "leadqual01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE company_contracts
            ADD COLUMN IF NOT EXISTS contract_type   VARCHAR(30),
            ADD COLUMN IF NOT EXISTS governing_state VARCHAR(2),
            ADD COLUMN IF NOT EXISTS project_state   VARCHAR(2),
            ADD COLUMN IF NOT EXISTS storage_path    TEXT,
            ADD COLUMN IF NOT EXISTS risk_transfer   JSONB,
            ADD COLUMN IF NOT EXISTS confirmed_at    TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS confirmed_by    UUID REFERENCES users(id) ON DELETE SET NULL
        """
    )


def downgrade():
    op.execute(
        """
        ALTER TABLE company_contracts
            DROP COLUMN IF EXISTS confirmed_by,
            DROP COLUMN IF EXISTS confirmed_at,
            DROP COLUMN IF EXISTS risk_transfer,
            DROP COLUMN IF EXISTS storage_path,
            DROP COLUMN IF EXISTS project_state,
            DROP COLUMN IF EXISTS governing_state,
            DROP COLUMN IF EXISTS contract_type
        """
    )
