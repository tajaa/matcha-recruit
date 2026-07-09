"""newsletter design settings — per-newsletter theme + accent color

Lets admins customize each newsletter's look (light/dark wrapper palette,
accent color) instead of every send using the hardcoded dark palette
regardless of what the compose preview showed. `theme` also becomes the
single source of truth the compose-preview endpoint, test-send, and real
send all read from (previously only preview accepted a theme argument;
actual sends always defaulted to dark).

Revision ID: zzzv8w9x0y1z2
Revises: zzzu7v8w9x0y1
Create Date: 2026-07-09
"""

from alembic import op


revision = "zzzv8w9x0y1z2"
down_revision = "zzzu7v8w9x0y1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE newsletters
            ADD COLUMN IF NOT EXISTS theme VARCHAR(10) NOT NULL DEFAULT 'light',
            ADD COLUMN IF NOT EXISTS accent_color VARCHAR(7) NOT NULL DEFAULT '#059669'
    """)
    op.execute("""
        ALTER TABLE newsletters
            ADD CONSTRAINT newsletters_theme_check CHECK (theme IN ('dark', 'light'))
    """)
    op.execute("""
        ALTER TABLE newsletters
            ADD CONSTRAINT newsletters_accent_color_check CHECK (accent_color ~ '^#[0-9A-Fa-f]{6}$')
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE newsletters DROP CONSTRAINT IF EXISTS newsletters_accent_color_check")
    op.execute("ALTER TABLE newsletters DROP CONSTRAINT IF EXISTS newsletters_theme_check")
    op.execute("ALTER TABLE newsletters DROP COLUMN IF EXISTS accent_color")
    op.execute("ALTER TABLE newsletters DROP COLUMN IF EXISTS theme")
