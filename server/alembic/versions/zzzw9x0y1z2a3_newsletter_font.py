"""newsletter design settings — font

Adds a per-newsletter `font` column alongside the theme/accent_color
columns from zzzv8w9x0y1z2. Constrained to the curated Google Fonts set
in newsletter_service.FONT_STACKS rather than free text, since the value
is interpolated into an inline `style` attribute + @import URL sent to
subscribers.

Revision ID: zzzw9x0y1z2a3
Revises: zzzv8w9x0y1z2
Create Date: 2026-07-09
"""

from alembic import op


revision = "zzzw9x0y1z2a3"
down_revision = "zzzv8w9x0y1z2"
branch_labels = None
depends_on = None

# Keep in sync with FONT_STACKS keys in app/core/services/newsletter_service.py.
_FONTS = (
    "inter", "ibm_plex_sans", "poppins", "space_grotesk",
    "dm_sans", "lora", "playfair_display", "source_serif",
)


def upgrade() -> None:
    fonts_sql = ", ".join(f"'{f}'" for f in _FONTS)
    op.execute("""
        ALTER TABLE newsletters
            ADD COLUMN IF NOT EXISTS font VARCHAR(32) NOT NULL DEFAULT 'inter'
    """)
    op.execute(f"""
        ALTER TABLE newsletters
            ADD CONSTRAINT newsletters_font_check CHECK (font IN ({fonts_sql}))
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE newsletters DROP CONSTRAINT IF EXISTS newsletters_font_check")
    op.execute("ALTER TABLE newsletters DROP COLUMN IF EXISTS font")
