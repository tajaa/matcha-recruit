"""Add ir_company_analysis cache table for company-scoped IR analyses

Sibling to ir_incident_analysis (which is per-incident). Used by the IR
Risk Insights endpoint to cache Gemini-generated theme detection across
the company corpus, keyed by (company_id, analysis_type, scope_key)
where scope_key encodes optional location filter + time window.

Existing 'company_consistency' rows continue to live in
ir_incident_analysis with their anchor-incident pattern; not migrated
because they expire 24h and the cache miss is harmless.

Revision ID: zzzn0o1p2q3r4
Revises: zzzm9n0o1p2q3
Create Date: 2026-04-30
"""

from typing import Sequence, Union

from alembic import op


revision: str = "zzzn0o1p2q3r4"
down_revision: Union[str, None] = "zzzm9n0o1p2q3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS ir_company_analysis (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            analysis_type VARCHAR(64) NOT NULL,
            scope_key VARCHAR(200) NOT NULL DEFAULT '',
            analysis_data JSONB NOT NULL,
            generated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(company_id, analysis_type, scope_key)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ir_company_analysis_company_type
            ON ir_company_analysis(company_id, analysis_type)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_ir_company_analysis_company_type")
    op.execute("DROP TABLE IF EXISTS ir_company_analysis")
