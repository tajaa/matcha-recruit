"""add wage_benchmarks table for BLS OEWS data

Revision ID: zzy5z6a7b8c9
Revises: zzx4y5z6a7b8
Create Date: 2026-04-16

Backs the §3.1 hourly wage benchmarking + below-market alerts feature
in QSR_RETENTION_PLAN.md. Stores BLS OEWS percentile wages keyed by
SOC code × area (metro / state / national) so we can compute per-employee
delta vs. local market.

The free-text-title → SOC mapping lives in
server/app/matcha/data/title_to_soc.json (loaded into memory at service
init), not in this table. Mappings are static + small, no need for a
DB round-trip per classify call.

Data is loaded by server/scripts/seed_wage_benchmarks.py from a curated
CSV at server/app/matcha/data/oews_qsr_subset.csv. Quarterly refresh
from the full BLS dump is a future Celery task — out of scope for MVP.
"""

from alembic import op


revision = "zzy5z6a7b8c9"
down_revision = "zzx4y5z6a7b8"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS wage_benchmarks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            soc_code VARCHAR(10) NOT NULL,
            soc_label VARCHAR(255),
            area_type VARCHAR(20) NOT NULL,
            area_code VARCHAR(20) NOT NULL,
            area_name VARCHAR(255),
            state VARCHAR(2),
            hourly_p10 DECIMAL(8,2),
            hourly_p25 DECIMAL(8,2),
            hourly_p50 DECIMAL(8,2) NOT NULL,
            hourly_p75 DECIMAL(8,2),
            hourly_p90 DECIMAL(8,2),
            annual_p50 DECIMAL(10,2),
            source VARCHAR(50) NOT NULL DEFAULT 'BLS_OEWS',
            period VARCHAR(10) NOT NULL,
            refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (soc_code, area_type, area_code, period),
            CONSTRAINT chk_wage_benchmarks_area_type
                CHECK (area_type IN ('metro', 'state', 'national'))
        )
    """)

    # Lookup index supports the 3-tier fallback in wage_benchmark_service:
    # SOC + state + area_type (most queries hit this composite)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_wage_benchmarks_lookup
        ON wage_benchmarks (soc_code, state, area_type)
    """)

    # Secondary index for metro lookups by area_name ILIKE
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_wage_benchmarks_area_name
        ON wage_benchmarks (area_name)
        WHERE area_type = 'metro'
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_wage_benchmarks_area_name")
    op.execute("DROP INDEX IF EXISTS idx_wage_benchmarks_lookup")
    op.execute("DROP TABLE IF EXISTS wage_benchmarks")
