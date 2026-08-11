"""Tell-Us brand memberships, location grants, invites, and access audit.

This migration is intentionally additive. Existing moderator rows are mapped
to the new ``staff`` role and receive explicit capability grants that preserve
their existing Board/inbox behavior without granting billing or team access.
"""
from alembic import op


revision = "tellus_app_19"
down_revision = "tellus_app_18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing rows use role='moderator'. Drop the generated CHECK constraint
    # before changing those values and installing the new role contract.
    op.execute(
        """DO $$
        DECLARE constraint_row RECORD;
        BEGIN
          FOR constraint_row IN
            SELECT c.conname
              FROM pg_constraint c
              JOIN pg_class t ON t.oid = c.conrelid
             WHERE t.relname = 'tellus_brand_members'
               AND c.contype = 'c'
               AND pg_get_constraintdef(c.oid) ILIKE '%role%'
          LOOP
            EXECUTE format(
              'ALTER TABLE tellus_brand_members DROP CONSTRAINT IF EXISTS %I',
              constraint_row.conname
            );
          END LOOP;
        END $$"""
    )
    op.execute(
        """UPDATE tellus_brand_members
              SET role = 'staff'
            WHERE role = 'moderator'"""
    )
    op.execute(
        """ALTER TABLE tellus_brand_members
           ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active'
             CHECK (status IN ('active', 'suspended', 'revoked'))"""
    )
    op.execute(
        """ALTER TABLE tellus_brand_members
           ADD COLUMN IF NOT EXISTS all_stores BOOLEAN NOT NULL DEFAULT FALSE"""
    )
    op.execute(
        """ALTER TABLE tellus_brand_members
           ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"""
    )
    op.execute(
        """ALTER TABLE tellus_brand_members
           ADD COLUMN IF NOT EXISTS suspended_at TIMESTAMPTZ"""
    )
    op.execute(
        """ALTER TABLE tellus_brand_members
           ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ"""
    )
    op.execute(
        """UPDATE tellus_brand_members
              SET all_stores = TRUE
            WHERE role IN ('owner', 'admin', 'staff')"""
    )
    op.execute(
        """ALTER TABLE tellus_brand_members
           ADD CONSTRAINT ck_tellus_brand_members_role
           CHECK (role IN ('owner', 'admin', 'location_manager', 'staff'))"""
    )
    op.execute(
        """ALTER TABLE tellus_brand_members
           ADD CONSTRAINT ck_tellus_brand_members_all_stores
           CHECK (role NOT IN ('owner', 'admin') OR all_stores = TRUE)"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_tellus_brand_members_brand_status
           ON tellus_brand_members (brand_id, status)"""
    )

    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_brand_member_stores (
            member_id UUID NOT NULL REFERENCES tellus_brand_members(id) ON DELETE CASCADE,
            store_id UUID NOT NULL REFERENCES tellus_stores(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (member_id, store_id)
        )"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_tellus_brand_member_stores_store
           ON tellus_brand_member_stores (store_id)"""
    )

    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_brand_member_capabilities (
            member_id UUID NOT NULL REFERENCES tellus_brand_members(id) ON DELETE CASCADE,
            capability TEXT NOT NULL,
            effect TEXT NOT NULL CHECK (effect IN ('grant', 'deny')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (member_id, capability)
        )"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_tellus_brand_member_capabilities_member
           ON tellus_brand_member_capabilities (member_id)"""
    )

    # Preserve old moderator behavior explicitly. Existing team members were
    # effectively all-store Board moderators; inbox-enabled members also had
    # the ability to work the business inbox.
    op.execute(
        """INSERT INTO tellus_brand_member_capabilities (member_id, capability, effect)
           SELECT id, 'board.manage', 'grant'
             FROM tellus_brand_members
            WHERE role = 'staff'
           ON CONFLICT (member_id, capability) DO NOTHING"""
    )
    op.execute(
        """INSERT INTO tellus_brand_member_capabilities (member_id, capability, effect)
           SELECT id, capability, 'grant'
             FROM tellus_brand_members
            CROSS JOIN (VALUES ('comms.read'), ('comms.reply'), ('comms.assign')) AS capabilities(capability)
            WHERE role = 'staff' AND can_manage_inbox = TRUE
           ON CONFLICT (member_id, capability) DO NOTHING"""
    )

    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_brand_invites (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_id UUID NOT NULL REFERENCES tellus_brands(id) ON DELETE CASCADE,
            email TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'location_manager', 'staff')),
            all_stores BOOLEAN NOT NULL DEFAULT FALSE,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            invited_by UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
            accepted_at TIMESTAMPTZ,
            accepted_by UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
            revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    op.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_brand_invites_pending_email
           ON tellus_brand_invites (brand_id, lower(email))
           WHERE accepted_at IS NULL AND revoked_at IS NULL"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_tellus_brand_invites_email
           ON tellus_brand_invites (lower(email), created_at DESC)"""
    )
    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_brand_invite_stores (
            invite_id UUID NOT NULL REFERENCES tellus_brand_invites(id) ON DELETE CASCADE,
            store_id UUID NOT NULL REFERENCES tellus_stores(id) ON DELETE CASCADE,
            PRIMARY KEY (invite_id, store_id)
        )"""
    )

    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_brand_audit_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_id UUID NOT NULL REFERENCES tellus_brands(id) ON DELETE CASCADE,
            actor_account_id UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
            action TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT,
            detail JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_tellus_brand_audit_events_brand_created
           ON tellus_brand_audit_events (brand_id, created_at DESC)"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_tellus_brand_audit_events_target
           ON tellus_brand_audit_events (target_type, target_id)"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tellus_brand_audit_events")
    op.execute("DROP TABLE IF EXISTS tellus_brand_invite_stores")
    op.execute("DROP TABLE IF EXISTS tellus_brand_invites")
    op.execute("DROP TABLE IF EXISTS tellus_brand_member_capabilities")
    op.execute("DROP TABLE IF EXISTS tellus_brand_member_stores")
    op.execute("ALTER TABLE tellus_brand_members DROP CONSTRAINT IF EXISTS ck_tellus_brand_members_all_stores")
    op.execute("ALTER TABLE tellus_brand_members DROP CONSTRAINT IF EXISTS ck_tellus_brand_members_role")
    op.execute("UPDATE tellus_brand_members SET role = 'moderator' WHERE role <> 'owner'")
    op.execute("ALTER TABLE tellus_brand_members DROP COLUMN IF EXISTS revoked_at")
    op.execute("ALTER TABLE tellus_brand_members DROP COLUMN IF EXISTS suspended_at")
    op.execute("ALTER TABLE tellus_brand_members DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE tellus_brand_members DROP COLUMN IF EXISTS all_stores")
    op.execute("ALTER TABLE tellus_brand_members DROP COLUMN IF EXISTS status")
    op.execute(
        """ALTER TABLE tellus_brand_members
           ADD CONSTRAINT tellus_brand_members_role_check
           CHECK (role IN ('owner', 'moderator'))"""
    )
