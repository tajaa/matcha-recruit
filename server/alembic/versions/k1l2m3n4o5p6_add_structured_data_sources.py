"""Add Tier 1 structured data sources tables

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-02-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'k1l2m3n4o5p6'
down_revision: Union[str, None] = 'j0k1l2m3n4o5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Structured data sources registry
    op.execute("""
        CREATE TABLE IF NOT EXISTS structured_data_sources (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_key VARCHAR(100) NOT NULL UNIQUE,
            source_name VARCHAR(255) NOT NULL,
            source_url VARCHAR(500) NOT NULL,
            source_type VARCHAR(50) NOT NULL,
            domain VARCHAR(100) NOT NULL,
            categories TEXT[] NOT NULL,
            coverage_scope VARCHAR(50) NOT NULL,
            coverage_states TEXT[],
            parser_config JSONB NOT NULL DEFAULT '{}',
            fetch_interval_hours INTEGER DEFAULT 168,
            last_fetched_at TIMESTAMP,
            last_fetch_status VARCHAR(20),
            last_fetch_error TEXT,
            record_count INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_structured_data_sources_active
        ON structured_data_sources(is_active)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_structured_data_sources_domain
        ON structured_data_sources(domain)
    """)

    # Structured data cache - parsed requirement data
    op.execute("""
        CREATE TABLE IF NOT EXISTS structured_data_cache (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_id UUID NOT NULL REFERENCES structured_data_sources(id) ON DELETE CASCADE,
            jurisdiction_key VARCHAR(100) NOT NULL,
            category VARCHAR(50) NOT NULL,
            rate_type VARCHAR(50),
            jurisdiction_level VARCHAR(20) NOT NULL,
            jurisdiction_name VARCHAR(100) NOT NULL,
            state VARCHAR(2) NOT NULL,
            raw_data JSONB NOT NULL,
            current_value VARCHAR(100),
            numeric_value DECIMAL(10, 4),
            effective_date DATE,
            next_scheduled_date DATE,
            next_scheduled_value VARCHAR(100),
            notes TEXT,
            fetched_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(source_id, jurisdiction_key, category, rate_type)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_structured_data_cache_source
        ON structured_data_cache(source_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_structured_data_cache_jurisdiction
        ON structured_data_cache(jurisdiction_key)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_structured_data_cache_state
        ON structured_data_cache(state)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_structured_data_cache_lookup
        ON structured_data_cache(state, jurisdiction_level, category)
    """)

    # Add source_tier column to jurisdiction_requirements
    op.execute("""
        ALTER TABLE jurisdiction_requirements
        ADD COLUMN IF NOT EXISTS source_tier INTEGER DEFAULT 3
    """)

    op.execute("""
        ALTER TABLE jurisdiction_requirements
        ADD COLUMN IF NOT EXISTS structured_source_id UUID REFERENCES structured_data_sources(id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_jurisdiction_requirements_source_tier
        ON jurisdiction_requirements(source_tier)
    """)

    # Seed initial structured data sources
    op.execute("""
        INSERT INTO structured_data_sources (source_key, source_name, source_url, source_type, domain, categories, coverage_scope, coverage_states, parser_config, fetch_interval_hours)
        VALUES
            (
                'berkeley_minwage_csv',
                'UC Berkeley Labor Center',
                'https://laborcenter.berkeley.edu/wp-content/uploads/2024/01/Local-Minimum-Wage-Ordinances-Inventory-2024.csv',
                'csv',
                'laborcenter.berkeley.edu',
                ARRAY['minimum_wage'],
                'city_county',
                NULL,
                '{"encoding": "utf-8", "skip_rows": 0, "columns": {"jurisdiction": "Jurisdiction", "state": "State", "current_wage": "Current Minimum Wage", "effective_date": "Effective Date", "next_wage": "Scheduled Increase", "next_date": "Next Increase Date", "notes": "Notes"}}'::jsonb,
                168
            ),
            (
                'epi_minwage_tracker',
                'Economic Policy Institute',
                'https://www.epi.org/minimum-wage-tracker/',
                'html_table',
                'epi.org',
                ARRAY['minimum_wage'],
                'state',
                NULL,
                '{"table_selector": "table.mw-tracker-table", "rate_type": "general", "columns": {"state": 0, "current_wage": 1, "effective_date": 2, "next_wage": 3, "next_date": 4}}'::jsonb,
                168
            ),
            (
                'dol_whd_tipped',
                'US DOL Wage and Hour Division - Tipped',
                'https://www.dol.gov/agencies/whd/state/minimum-wage/tipped',
                'html_table',
                'dol.gov',
                ARRAY['minimum_wage'],
                'state',
                NULL,
                '{"table_selector": "table", "rate_type": "tipped", "columns": {"state": 0, "cash_wage": 1, "tip_credit": 2, "total": 3}}'::jsonb,
                168
            ),
            (
                'ncsl_minwage_chart',
                'NCSL State Minimum Wage Chart',
                'https://www.ncsl.org/labor-and-employment/state-minimum-wages',
                'html_table',
                'ncsl.org',
                ARRAY['minimum_wage'],
                'state',
                NULL,
                '{"table_selector": "table.state-table", "rate_type": "general", "columns": {"state": 0, "current_wage": 1, "future_changes": 2}}'::jsonb,
                168
            )
        ON CONFLICT (source_key) DO UPDATE SET
            source_url = EXCLUDED.source_url,
            parser_config = EXCLUDED.parser_config
    """)

    # Add scheduler setting for structured data fetch
    op.execute("""
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES
            ('structured_data_fetch', 'Structured Data Fetch', 'Fetch Tier 1 structured data from authoritative sources (Berkeley, DOL, EPI, NCSL).', false, 0)
        ON CONFLICT (task_key) DO NOTHING
    """)


def downgrade() -> None:
    # Remove scheduler setting
    op.execute("""
        DELETE FROM scheduler_settings
        WHERE task_key = 'structured_data_fetch'
    """)

    # Remove columns from jurisdiction_requirements
    op.execute("""
        ALTER TABLE jurisdiction_requirements
        DROP COLUMN IF EXISTS structured_source_id
    """)

    op.execute("""
        ALTER TABLE jurisdiction_requirements
        DROP COLUMN IF EXISTS source_tier
    """)

    # Drop tables
    op.execute("DROP TABLE IF EXISTS structured_data_cache")
    op.execute("DROP TABLE IF EXISTS structured_data_sources")
