"""Add international jurisdiction support: country_code, widen state, new jurisdiction levels.

Phase 1 of the International Jurisdiction Support Plan.

Revision ID: q2r3s4t5u6v7
Revises: p1q2r3s4t5u6
Create Date: 2026-03-23
"""

from alembic import op

revision = "q2r3s4t5u6v7"
down_revision = "p1q2r3s4t5u6"
branch_labels = None
depends_on = None


def upgrade():
    # ── 1A. Extend jurisdiction_level_enum ────────────────────────────────
    # ALTER TYPE ADD VALUE cannot run inside a transaction in Postgres.
    # alembic wraps migrations in a transaction by default, but op.execute
    # with ALTER TYPE ADD VALUE IF NOT EXISTS works in newer Postgres (12+).
    op.execute("COMMIT")  # exit the transaction
    op.execute("ALTER TYPE jurisdiction_level_enum ADD VALUE IF NOT EXISTS 'national'")
    op.execute("ALTER TYPE jurisdiction_level_enum ADD VALUE IF NOT EXISTS 'province'")
    op.execute("ALTER TYPE jurisdiction_level_enum ADD VALUE IF NOT EXISTS 'region'")
    op.execute("BEGIN")  # re-enter a transaction for the rest

    # ── 1B. jurisdictions table ───────────────────────────────────────────

    # Add country_code (defaults to 'US' for all existing rows)
    op.execute("""
        ALTER TABLE jurisdictions
        ADD COLUMN IF NOT EXISTS country_code VARCHAR(2) NOT NULL DEFAULT 'US'
    """)

    # Widen state from VARCHAR(2) to VARCHAR(10) for international codes (CDMX, etc.)
    op.execute("""
        ALTER TABLE jurisdictions
        ALTER COLUMN state TYPE VARCHAR(10)
    """)

    # Make state nullable (city-states like Singapore have no subdivision)
    op.execute("""
        ALTER TABLE jurisdictions
        ALTER COLUMN state DROP NOT NULL
    """)

    # Drop old unique index and create new one that includes country_code
    op.execute("DROP INDEX IF EXISTS uq_jurisdictions_city_state")
    op.execute("""
        CREATE UNIQUE INDEX uq_jurisdictions_city_state_country
        ON jurisdictions (COALESCE(city, ''), COALESCE(state, ''), country_code)
    """)

    # Update state-level unique index to include country_code
    op.execute("DROP INDEX IF EXISTS uq_jurisdictions_state_level")
    op.execute("""
        CREATE UNIQUE INDEX uq_jurisdictions_state_level
        ON jurisdictions (COALESCE(state, ''), country_code)
        WHERE city IS NULL AND level IN ('federal'::jurisdiction_level_enum, 'state'::jurisdiction_level_enum, 'national'::jurisdiction_level_enum)
    """)

    # Index on country_code for filtering
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_jurisdictions_country_code
        ON jurisdictions(country_code)
    """)

    # ── 1C. business_locations table ──────────────────────────────────────

    op.execute("""
        ALTER TABLE business_locations
        ADD COLUMN IF NOT EXISTS country_code VARCHAR(2) NOT NULL DEFAULT 'US'
    """)

    op.execute("""
        ALTER TABLE business_locations
        ALTER COLUMN state TYPE VARCHAR(10)
    """)

    op.execute("""
        ALTER TABLE business_locations
        ALTER COLUMN state DROP NOT NULL
    """)

    op.execute("""
        ALTER TABLE business_locations
        ALTER COLUMN zipcode DROP NOT NULL
    """)

    # ── 1D. structured_data_cache table ───────────────────────────────────

    op.execute("""
        ALTER TABLE structured_data_cache
        ADD COLUMN IF NOT EXISTS country_code VARCHAR(2) NOT NULL DEFAULT 'US'
    """)

    op.execute("""
        ALTER TABLE structured_data_cache
        ALTER COLUMN state TYPE VARCHAR(10)
    """)

    op.execute("""
        ALTER TABLE structured_data_cache
        ALTER COLUMN state DROP NOT NULL
    """)

    # ── 1E. jurisdiction_reference table ──────────────────────────────────

    op.execute("""
        ALTER TABLE jurisdiction_reference
        ADD COLUMN IF NOT EXISTS country_code VARCHAR(2) NOT NULL DEFAULT 'US'
    """)

    op.execute("""
        ALTER TABLE jurisdiction_reference
        ALTER COLUMN state TYPE VARCHAR(10)
    """)

    op.execute("""
        ALTER TABLE jurisdiction_reference
        ALTER COLUMN state DROP NOT NULL
    """)


def downgrade():
    # ── Reverse 1E ────────────────────────────────────────────────────────
    op.execute("ALTER TABLE jurisdiction_reference DROP COLUMN IF EXISTS country_code")
    op.execute("ALTER TABLE jurisdiction_reference ALTER COLUMN state SET NOT NULL")
    op.execute("ALTER TABLE jurisdiction_reference ALTER COLUMN state TYPE VARCHAR(2)")

    # ── Reverse 1D ────────────────────────────────────────────────────────
    op.execute("ALTER TABLE structured_data_cache DROP COLUMN IF EXISTS country_code")
    op.execute("ALTER TABLE structured_data_cache ALTER COLUMN state SET NOT NULL")
    op.execute("ALTER TABLE structured_data_cache ALTER COLUMN state TYPE VARCHAR(2)")

    # ── Reverse 1C ────────────────────────────────────────────────────────
    op.execute("ALTER TABLE business_locations ALTER COLUMN zipcode SET NOT NULL")
    op.execute("ALTER TABLE business_locations ALTER COLUMN state SET NOT NULL")
    op.execute("ALTER TABLE business_locations ALTER COLUMN state TYPE VARCHAR(2)")
    op.execute("ALTER TABLE business_locations DROP COLUMN IF EXISTS country_code")

    # ── Reverse 1B ────────────────────────────────────────────────────────
    op.execute("DROP INDEX IF EXISTS idx_jurisdictions_country_code")
    op.execute("DROP INDEX IF EXISTS uq_jurisdictions_state_level")
    op.execute("DROP INDEX IF EXISTS uq_jurisdictions_city_state_country")

    # Restore original indexes
    op.execute("""
        CREATE UNIQUE INDEX uq_jurisdictions_city_state
        ON jurisdictions (COALESCE(city, ''::character varying), state)
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_jurisdictions_state_level
        ON jurisdictions (state)
        WHERE city IS NULL AND level IN ('federal'::jurisdiction_level_enum, 'state'::jurisdiction_level_enum)
    """)

    op.execute("ALTER TABLE jurisdictions ALTER COLUMN state SET NOT NULL")
    op.execute("ALTER TABLE jurisdictions ALTER COLUMN state TYPE VARCHAR(2)")
    op.execute("ALTER TABLE jurisdictions DROP COLUMN IF EXISTS country_code")

    # Note: Cannot remove ENUM values in Postgres. 'national', 'province', 'region'
    # will remain in the enum but won't be used.
