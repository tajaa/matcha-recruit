"""Seed scheduler_settings row for hr_news_fetch.

Allows the periodic worker to refresh HR news RSS feeds on the same
worker_ready dispatch path as legislation_watch et al. Default disabled —
admin enables via the scheduler admin UI.

Revision ID: zzzw9x0y1z2a3
Revises: zzzv8w9x0y1z2
Create Date: 2026-05-06
"""
from alembic import op


revision = "zzzw9x0y1z2a3"
down_revision = "zzzv8w9x0y1z2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES ('hr_news_fetch', 'HR News Fetch', 'Refresh HR industry RSS feeds for the public news section.', false, 0)
        ON CONFLICT (task_key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'hr_news_fetch'")
