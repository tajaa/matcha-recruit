"""Add ir_security_surveys table for workplace security self-assessments

Revision ID: zzzo1p2q3r4s5
Revises: zzzn0o1p2q3r4
Create Date: 2026-04-30
"""

from typing import Sequence, Union

from alembic import op


revision: str = "zzzo1p2q3r4s5"
down_revision: Union[str, None] = "zzzn0o1p2q3r4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS ir_security_surveys (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id      UUID NOT NULL,
            location_id     UUID,
            conducted_by    UUID NOT NULL,
            conducted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            responses       JSONB NOT NULL DEFAULT '{}',
            score           NUMERIC(5,2),
            notes           TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ir_security_surveys_company_date
            ON ir_security_surveys (company_id, conducted_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ir_security_surveys")
