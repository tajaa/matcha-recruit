"""huume: offer letter sign/accept columns

Adds the columns needed for the in-app public offer-signing page
(GET/POST /offer-letters/candidate/{token}/...): a typed-name signature,
acceptance/decline stamps, the stored signed PDF path, and a link back to
the employee record created on acceptance. Does NOT add a thread link —
`mw_threads.linked_offer_letter_id` (migration 7c3a7b1e830a-era) already
gives the offer->thread relationship the classic matcha-work `offer_letter`
skill uses, and Huume reuses it rather than duplicating a second FK.

Deliberately does NOT touch the existing `status` CHECK constraint
(draft/sent/accepted/rejected/expired) — acceptance reuses `status =
'accepted'` (as the existing range-negotiation match path already does)
and decline reuses `status = 'rejected'`, avoiding a constraint
drop/re-add on prod.

Revision ID: huume01
Revises: c0d1e2f3a4b5
Create Date: 2026-07-26
"""

from alembic import op


revision = "huume01"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE offer_letters
            ADD COLUMN IF NOT EXISTS signed_name VARCHAR(255),
            ADD COLUMN IF NOT EXISTS signed_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS signer_ip VARCHAR(64),
            ADD COLUMN IF NOT EXISTS declined_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS decline_reason TEXT,
            ADD COLUMN IF NOT EXISTS signed_pdf_storage_path TEXT,
            ADD COLUMN IF NOT EXISTS employee_id UUID REFERENCES employees(id) ON DELETE SET NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_offer_letters_employee
        ON offer_letters(employee_id)
        WHERE employee_id IS NOT NULL
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_offer_letters_employee")
    op.execute(
        """
        ALTER TABLE offer_letters
            DROP COLUMN IF EXISTS signed_name,
            DROP COLUMN IF EXISTS signed_at,
            DROP COLUMN IF EXISTS signer_ip,
            DROP COLUMN IF EXISTS declined_at,
            DROP COLUMN IF EXISTS decline_reason,
            DROP COLUMN IF EXISTS signed_pdf_storage_path,
            DROP COLUMN IF EXISTS employee_id
        """
    )
