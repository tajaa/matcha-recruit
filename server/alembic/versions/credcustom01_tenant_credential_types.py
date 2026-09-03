"""Add tenant-owned custom credential types without exposing them to old apps.

Revision ID: credcustom01
Revises: credvis01
"""

from alembic import op


revision = "credcustom01"
down_revision = "credvis01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep credential_types itself predecessor-compatible.  An older application
    # still selects the whole table, so tenant labels and ownership cannot live
    # there without becoming visible during a blue/green deploy or app rollback.
    # The base row is only an opaque FK target; current code reads the scoped view.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS company_credential_types (
            credential_type_id UUID PRIMARY KEY
                REFERENCES credential_types(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            label VARCHAR(200) NOT NULL,
            category VARCHAR(40) NOT NULL,
            description TEXT,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_company_credential_types_company
        ON company_credential_types(company_id)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_company_credential_types_label
        ON company_credential_types(company_id, lower(btrim(label)))
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW scoped_credential_types AS
        SELECT ct.id,
               ct.key,
               COALESCE(cct.label, ct.label) AS label,
               COALESCE(cct.category, ct.category) AS category,
               COALESCE(cct.description, ct.description) AS description,
               ct.has_expiration,
               ct.has_number,
               ct.has_state,
               ct.verification_method,
               ct.is_system,
               ct.created_at,
               ct.schedule_blocking,
               ct.warning_days,
               ct.auto_unassign_on_expiry,
               cct.company_id,
               cct.created_by
        FROM credential_types ct
        LEFT JOIN company_credential_types cct
          ON cct.credential_type_id = ct.id
        """
    )

    # IDs are not authorization boundaries.  These triggers also protect an
    # older application that knows a tenant type UUID but does not understand
    # company_credential_types yet.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_credential_type_company_scope()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        DECLARE
            owner_company_id UUID;
            target_company_id UUID;
        BEGIN
            SELECT company_id
              INTO owner_company_id
              FROM company_credential_types
             WHERE credential_type_id = NEW.credential_type_id;

            IF owner_company_id IS NULL THEN
                RETURN NEW;
            END IF;

            IF TG_TABLE_NAME = 'employee_credential_requirements' THEN
                SELECT org_id
                  INTO target_company_id
                  FROM employees
                 WHERE id = NEW.employee_id;
            ELSE
                target_company_id := NEW.company_id;
            END IF;

            IF target_company_id IS DISTINCT FROM owner_company_id THEN
                RAISE EXCEPTION 'credential type is not available to this company'
                    USING ERRCODE = '23503';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION delete_company_credential_type_base()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        BEGIN
            DELETE FROM credential_types WHERE id = OLD.credential_type_id;
            RETURN OLD;
        END;
        $$
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_delete_company_credential_type_base "
        "ON company_credential_types"
    )
    op.execute(
        """
        CREATE TRIGGER trg_delete_company_credential_type_base
        AFTER DELETE ON company_credential_types
        FOR EACH ROW EXECUTE FUNCTION delete_company_credential_type_base()
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_credential_template_type_scope "
        "ON credential_requirement_templates"
    )
    op.execute(
        """
        CREATE TRIGGER trg_credential_template_type_scope
        BEFORE INSERT OR UPDATE OF company_id, credential_type_id
            ON credential_requirement_templates
        FOR EACH ROW EXECUTE FUNCTION enforce_credential_type_company_scope()
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_employee_credential_type_scope "
        "ON employee_credential_requirements"
    )
    op.execute(
        """
        CREATE TRIGGER trg_employee_credential_type_scope
        BEFORE INSERT OR UPDATE OF employee_id, credential_type_id
            ON employee_credential_requirements
        FOR EACH ROW EXECUTE FUNCTION enforce_credential_type_company_scope()
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_job_credential_type_scope "
        "ON schedule_job_credential_requirements"
    )
    op.execute(
        """
        CREATE TRIGGER trg_job_credential_type_scope
        BEFORE INSERT OR UPDATE OF company_id, credential_type_id
            ON schedule_job_credential_requirements
        FOR EACH ROW EXECUTE FUNCTION enforce_credential_type_company_scope()
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_credential_filter_type_scope "
        "ON company_credential_type_filter_items"
    )
    op.execute(
        """
        CREATE TRIGGER trg_credential_filter_type_scope
        BEFORE INSERT OR UPDATE OF company_id, credential_type_id
            ON company_credential_type_filter_items
        FOR EACH ROW EXECUTE FUNCTION enforce_credential_type_company_scope()
        """
    )


def downgrade() -> None:
    # Removing the ownership table while custom rows exist would turn their
    # opaque base rows into shared credential types.  Fail closed and require an
    # explicit archival/deletion decision instead of silently widening access.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM company_credential_types) THEN
                RAISE EXCEPTION
                    'cannot downgrade credcustom01 while tenant credential types exist';
            END IF;
        END;
        $$
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_credential_filter_type_scope "
        "ON company_credential_type_filter_items"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_job_credential_type_scope "
        "ON schedule_job_credential_requirements"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_employee_credential_type_scope "
        "ON employee_credential_requirements"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_credential_template_type_scope "
        "ON credential_requirement_templates"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_delete_company_credential_type_base "
        "ON company_credential_types"
    )
    op.execute("DROP FUNCTION IF EXISTS delete_company_credential_type_base()")
    op.execute("DROP FUNCTION IF EXISTS enforce_credential_type_company_scope()")
    op.execute("DROP VIEW IF EXISTS scoped_credential_types")
    op.execute("DROP TABLE IF EXISTS company_credential_types")
