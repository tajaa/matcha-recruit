"""add anchoring + resolve to mw_section_comments

Anchored (highlight-attached) note comments: a comment can carry a character
range into the section's text (anchor_start/anchor_end), the quoted snippet at
creation time (quoted_text, for re-anchoring if the text shifts), and a resolved
flag. All nullable / defaulted so existing flat comments are unaffected.

Revision ID: seccmtanchor01
Revises: benefitelig01
Create Date: 2026-06-01
"""

from alembic import op


revision = "seccmtanchor01"
down_revision = "benefitelig01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE mw_section_comments
            ADD COLUMN IF NOT EXISTS anchor_start INTEGER,
            ADD COLUMN IF NOT EXISTS anchor_end INTEGER,
            ADD COLUMN IF NOT EXISTS quoted_text TEXT,
            ADD COLUMN IF NOT EXISTS resolved BOOLEAN NOT NULL DEFAULT FALSE
        """
    )


def downgrade():
    op.execute(
        """
        ALTER TABLE mw_section_comments
            DROP COLUMN IF EXISTS anchor_start,
            DROP COLUMN IF EXISTS anchor_end,
            DROP COLUMN IF EXISTS quoted_text,
            DROP COLUMN IF EXISTS resolved
        """
    )
