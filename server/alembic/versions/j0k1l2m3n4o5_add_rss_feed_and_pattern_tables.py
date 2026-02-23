"""Add RSS feed sources and pattern recognition tables

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-02-03

"""
from typing import Sequence, Union

from alembic import op

revision = 'j0k1l2m3n4o5'
down_revision = 'i9j0k1l2m3n4'
branch_labels = None
depends_on = None
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j0k1l2m3n4o5'
down_revision: Union[str, None] = 'i9j0k1l2m3n4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # RSS Feed Sources table
    op.execute("""
        CREATE TABLE IF NOT EXISTS rss_feed_sources (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            state VARCHAR(2) NOT NULL,
            feed_url TEXT NOT NULL UNIQUE,
            feed_name VARCHAR(255) NOT NULL,
            feed_type VARCHAR(50) DEFAULT 'dol',
            categories TEXT[],
            is_active BOOLEAN DEFAULT true,
            last_fetched_at TIMESTAMP,
            last_item_hash VARCHAR(64),
            error_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_rss_feed_sources_state
        ON rss_feed_sources(state)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_rss_feed_sources_active
        ON rss_feed_sources(is_active)
    """)

    # RSS Feed Items table
    op.execute("""
        CREATE TABLE IF NOT EXISTS rss_feed_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            feed_id UUID NOT NULL REFERENCES rss_feed_sources(id) ON DELETE CASCADE,
            item_hash VARCHAR(64) NOT NULL,
            title TEXT NOT NULL,
            link TEXT,
            pub_date TIMESTAMP,
            description TEXT,
            processed BOOLEAN DEFAULT false,
            gemini_triggered BOOLEAN DEFAULT false,
            relevance_score DECIMAL(3,2),
            detected_category VARCHAR(50),
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(feed_id, item_hash)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_rss_feed_items_feed_id
        ON rss_feed_items(feed_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_rss_feed_items_processed
        ON rss_feed_items(processed)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_rss_feed_items_relevance
        ON rss_feed_items(relevance_score)
    """)

    # Legislative Patterns table
    op.execute("""
        CREATE TABLE IF NOT EXISTS legislative_patterns (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            pattern_key VARCHAR(100) NOT NULL UNIQUE,
            display_name VARCHAR(255) NOT NULL,
            category VARCHAR(50),
            trigger_month INTEGER,
            trigger_day INTEGER,
            lookback_days INTEGER DEFAULT 30,
            min_jurisdictions INTEGER DEFAULT 3,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Pattern Detections table
    op.execute("""
        CREATE TABLE IF NOT EXISTS pattern_detections (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            pattern_id UUID REFERENCES legislative_patterns(id) ON DELETE CASCADE,
            detection_year INTEGER NOT NULL,
            jurisdictions_matched JSONB NOT NULL,
            jurisdictions_flagged JSONB,
            detection_date TIMESTAMP DEFAULT NOW(),
            alerts_created INTEGER DEFAULT 0,
            UNIQUE(pattern_id, detection_year)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_pattern_detections_year
        ON pattern_detections(detection_year)
    """)

    # Seed initial RSS feeds for major states
    op.execute("""
        INSERT INTO rss_feed_sources (state, feed_url, feed_name, feed_type, categories)
        VALUES
            ('CA', 'https://www.dir.ca.gov/rss/news.xml', 'CA DIR News', 'dol', ARRAY['minimum_wage', 'sick_leave', 'overtime', 'meal_breaks']),
            ('NY', 'https://dol.ny.gov/rss.xml', 'NY DOL News', 'dol', ARRAY['minimum_wage', 'sick_leave', 'pay_frequency']),
            ('WA', 'https://lni.wa.gov/news/rss.xml', 'WA L&I News', 'dol', ARRAY['minimum_wage', 'sick_leave', 'overtime'])
        ON CONFLICT (feed_url) DO NOTHING
    """)

    # Seed known legislative patterns
    op.execute("""
        INSERT INTO legislative_patterns (pattern_key, display_name, category, trigger_month, trigger_day, lookback_days, min_jurisdictions)
        VALUES
            ('jan_1_wage_update', 'January 1st Minimum Wage Update', 'minimum_wage', 1, 1, 60, 3),
            ('july_1_fiscal_year', 'July 1st Fiscal Year Updates', NULL, 7, 1, 30, 2),
            ('jan_1_sick_leave', 'January 1st Sick Leave Update', 'sick_leave', 1, 1, 45, 2)
        ON CONFLICT (pattern_key) DO NOTHING
    """)

    # Add new scheduler settings for legislation watch and pattern recognition
    op.execute("""
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES
            ('legislation_watch', 'Legislation Watch (RSS)', 'Monitor RSS feeds from state DOL/legislature sites for upcoming legislation.', false, 0),
            ('pattern_recognition', 'Pattern Recognition', 'Detect coordinated legislative changes across jurisdictions.', false, 0)
        ON CONFLICT (task_key) DO NOTHING
    """)


def downgrade() -> None:
    # Remove scheduler settings
    op.execute("""
        DELETE FROM scheduler_settings
        WHERE task_key IN ('legislation_watch', 'pattern_recognition')
    """)

    # Drop tables
    op.execute("DROP TABLE IF EXISTS pattern_detections")
    op.execute("DROP TABLE IF EXISTS legislative_patterns")
    op.execute("DROP TABLE IF EXISTS rss_feed_items")
    op.execute("DROP TABLE IF EXISTS rss_feed_sources")
