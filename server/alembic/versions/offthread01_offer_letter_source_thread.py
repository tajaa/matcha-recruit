"""Add offer_letters.source_thread_id — a durable, forward-declared link
from an offer letter back to the Huume/matcha-work thread that drafted it.

The existing link was backwards and fragile: mw_threads.linked_offer_letter_id
is one slot per thread, set only on the INSERT branch of draft_offer_letter —
drafting a second candidate in the same thread silently repoints it, so the
first candidate's signature notification (_notify_huume_thread_of_offer_event,
routes/employee_lifecycle/offer_letters.py) reverse-looked-up zero rows and
returned with no alert. This column lets the notifier resolve the thread
directly from the offer row instead.

NOTE: the alembic history on this branch has multiple leaves; down_revision
is set to `inventory01`, a verified leaf at authoring time (no other
migration's down_revision points to it as of 2026-08-02). Confirm the
correct head for your environment before `alembic upgrade` if time has
passed.

Revision ID: offthread01
Revises: inventory01
Create Date: 2026-08-02
"""

from alembic import op
import sqlalchemy as sa


revision = "offthread01"
down_revision = "inventory01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE offer_letters
        ADD COLUMN IF NOT EXISTS source_thread_id UUID
            REFERENCES mw_threads(id) ON DELETE SET NULL
    """)


def downgrade():
    op.execute("""
        ALTER TABLE offer_letters DROP COLUMN IF EXISTS source_thread_id
    """)
