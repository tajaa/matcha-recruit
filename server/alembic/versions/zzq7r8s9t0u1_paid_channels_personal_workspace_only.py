"""Enforce paid channels in personal workspaces only (DB-level trigger).

Creates a BEFORE INSERT/UPDATE trigger on channels that rejects any attempt
to set is_paid=true on a channel whose company is not a personal workspace
(companies.is_personal = false). Belt-and-suspenders — the route layer in
channels.py already enforces this, but the trigger guarantees it even if a
future code path bypasses the route.

Revision ID: zzq7r8s9t0u1
Revises: zzp6q7r8s9t0
Create Date: 2026-04-13
"""
from alembic import op

revision = "zzq7r8s9t0u1"
down_revision = "zzp6q7r8s9t0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION channels_enforce_paid_personal_only()
        RETURNS TRIGGER AS $fn$
        BEGIN
          IF NEW.is_paid = true THEN
            IF NOT EXISTS (
              SELECT 1 FROM companies
              WHERE id = NEW.company_id AND is_personal = true
            ) THEN
              RAISE EXCEPTION
                'Paid channels are only allowed in personal workspaces (channel %, company %)',
                NEW.id, NEW.company_id;
            END IF;
          END IF;
          RETURN NEW;
        END;
        $fn$ LANGUAGE plpgsql;
    """)
    op.execute("DROP TRIGGER IF EXISTS channels_paid_personal_only ON channels")
    op.execute("""
        CREATE TRIGGER channels_paid_personal_only
        BEFORE INSERT OR UPDATE OF is_paid, company_id ON channels
        FOR EACH ROW
        EXECUTE FUNCTION channels_enforce_paid_personal_only()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS channels_paid_personal_only ON channels")
    op.execute("DROP FUNCTION IF EXISTS channels_enforce_paid_personal_only()")
