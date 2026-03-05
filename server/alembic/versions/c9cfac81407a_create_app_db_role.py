"""create non-superuser app role for RLS enforcement

Revision ID: c9cfac81407a
Revises: f1d6d19f0f3e
Create Date: 2026-03-05

Creates a ``matcha_app`` role with LOGIN + NOBYPASSRLS. Once
DATABASE_URL is switched to this role, PostgreSQL will actually
enforce RLS policies instead of silently bypassing them (as happens
with the superuser ``matcha`` role).

Deployment steps after running this migration:
  1. Set a strong password: ALTER ROLE matcha_app PASSWORD '...';
  2. Update DATABASE_URL to use matcha_app
  3. Restart the application
"""

from alembic import op


revision = "c9cfac81407a"
down_revision = "f1d6d19f0f3e"
branch_labels = None
depends_on = None

APP_ROLE = "matcha_app"


def upgrade():
    # Create role only if it doesn't already exist
    op.execute(f"""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} LOGIN NOBYPASSRLS;
            END IF;
        END $$
    """)

    # Grant connect + schema usage
    op.execute(f"""
        DO $$ BEGIN
            EXECUTE 'GRANT CONNECT ON DATABASE ' || current_database() || ' TO {APP_ROLE}';
        END $$
    """)
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")

    # Grant DML on all existing tables and sequences
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")

    # Ensure future tables/sequences also get grants automatically
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}")


def downgrade():
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {APP_ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {APP_ROLE}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}")
    op.execute(f"""
        DO $$ BEGIN
            DROP ROLE IF EXISTS {APP_ROLE};
        EXCEPTION WHEN dependent_objects_still_exist THEN NULL;
        END $$
    """)
