"""Materialize food-handler document evidence for schedule enforcement.

Food-handler documents could previously exist without a matching employee
credential requirement. The approval API then discarded the manager-confirmed
expiration date and scheduling failed open. Persist the confirmed date on the
document and backfill the missing evidence rows.

Revision ID: empsched14
Revises: empsched13
"""
from alembic import op


revision = "empsched14"
down_revision = "empsched13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE credential_documents
            ADD COLUMN IF NOT EXISTS expires_at DATE
    """)
    op.execute("""
        UPDATE credential_documents cd
           SET expires_at=ecr.expires_at
          FROM employee_credential_requirements ecr
         WHERE ecr.credential_document_id=cd.id
           AND cd.expires_at IS NULL
           AND ecr.expires_at IS NOT NULL
    """)
    # Older approvals did not persist the manually confirmed date. Recover a
    # valid extracted ISO date when available; malformed extraction remains
    # NULL and therefore creates a pending, schedule-blocking requirement.
    op.execute("""
        DO $$
        DECLARE
            item RECORD;
            parsed_expiry DATE;
        BEGIN
            FOR item IN
                SELECT id, extracted_data #>> '{fields,expiration,value}' AS value
                  FROM credential_documents
                 WHERE document_type='food_handler_card'
                   AND expires_at IS NULL
                   AND extracted_data #>> '{fields,expiration,value}' IS NOT NULL
            LOOP
                BEGIN
                    parsed_expiry := item.value::date;
                    UPDATE credential_documents SET expires_at=parsed_expiry WHERE id=item.id;
                EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN
                    NULL;
                END;
            END LOOP;
        END $$
    """)
    op.execute("""
        WITH ranked_documents AS (
            SELECT cd.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY cd.employee_id
                       ORDER BY (cd.review_status='approved' AND cd.expires_at IS NOT NULL) DESC,
                                cd.created_at DESC, cd.id DESC
                   ) AS row_number
              FROM credential_documents cd
              JOIN employees e ON e.id=cd.employee_id AND e.org_id=cd.company_id
             WHERE cd.document_type='food_handler_card'
        ), food_handler_type AS (
            SELECT id FROM credential_types WHERE key='food_handler_card'
        )
        INSERT INTO employee_credential_requirements
            (employee_id, credential_type_id, status, is_required, priority,
             credential_document_id, verified_at, expires_at, applies_company_wide)
        SELECT cd.employee_id, ct.id,
               CASE WHEN cd.review_status='approved' AND cd.expires_at IS NOT NULL
                    THEN 'verified' ELSE 'pending' END,
               true, 'blocking',
               CASE WHEN cd.review_status='approved' AND cd.expires_at IS NOT NULL
                    THEN cd.id ELSE NULL END,
               CASE WHEN cd.review_status='approved' AND cd.expires_at IS NOT NULL
                    THEN COALESCE(cd.reviewed_at, NOW()) ELSE NULL END,
               CASE WHEN cd.review_status='approved' THEN cd.expires_at ELSE NULL END,
               true
          FROM ranked_documents cd CROSS JOIN food_handler_type ct
         WHERE cd.row_number=1
        ON CONFLICT (employee_id, credential_type_id) DO NOTHING
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_credential_documents_food_handler_expiry
            ON credential_documents(employee_id, expires_at)
            WHERE document_type='food_handler_card' AND review_status='approved'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_credential_documents_food_handler_expiry")
    # Retain materialized requirement evidence; deleting it would make a
    # downgrade fail open for employees already governed by this policy.
    op.execute("ALTER TABLE credential_documents DROP COLUMN IF EXISTS expires_at")
