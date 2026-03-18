"""02: Add hierarchy columns to jurisdictions + facility_attributes to business_locations

Revision ID: zm1n2o3p4q5r
Revises: zl0m1n2o3p4q
Create Date: 2026-03-17
"""

from alembic import op


revision = "zm1n2o3p4q5r"
down_revision = "zl0m1n2o3p4q"
branch_labels = None
depends_on = None


# US state code → full name for display_name backfill
STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
    "PR": "Puerto Rico", "GU": "Guam", "VI": "U.S. Virgin Islands",
    "AS": "American Samoa", "MP": "Northern Mariana Islands",
}


def upgrade():
    # ── 1. Add new columns to jurisdictions ───────────────────────────────
    op.execute("""
        ALTER TABLE jurisdictions
        ADD COLUMN IF NOT EXISTS level jurisdiction_level_enum NOT NULL DEFAULT 'city'
    """)
    op.execute("""
        ALTER TABLE jurisdictions
        ADD COLUMN IF NOT EXISTS display_name VARCHAR(200)
    """)
    op.execute("""
        ALTER TABLE jurisdictions
        ADD COLUMN IF NOT EXISTS authority_type VARCHAR(30) NOT NULL DEFAULT 'geographic'
    """)

    # ── 2. Make city nullable ─────────────────────────────────────────────
    op.execute("""
        ALTER TABLE jurisdictions ALTER COLUMN city DROP NOT NULL
    """)

    # ── 3. Classify existing rows ─────────────────────────────────────────
    # State rows: city was empty string, state != 'US'
    op.execute("""
        UPDATE jurisdictions
        SET level = 'state', city = NULL
        WHERE (city = '' OR city IS NULL) AND state != 'US' AND level = 'city'
    """)

    # County rows: city contains '_county_' pattern
    op.execute("""
        UPDATE jurisdictions
        SET level = 'county'
        WHERE city LIKE '%_county_%' AND level = 'city'
    """)

    # ── 4. Insert federal row ─────────────────────────────────────────────
    op.execute("""
        INSERT INTO jurisdictions (city, state, level, display_name, authority_type)
        SELECT NULL, 'US', 'federal', 'Federal', 'geographic'
        WHERE NOT EXISTS (
            SELECT 1 FROM jurisdictions WHERE state = 'US' AND level = 'federal'
        )
    """)

    # ── 5. Link state rows to federal ─────────────────────────────────────
    op.execute("""
        UPDATE jurisdictions
        SET parent_id = (SELECT id FROM jurisdictions WHERE level = 'federal' AND state = 'US' LIMIT 1)
        WHERE level = 'state' AND parent_id IS NULL
    """)

    # ── 6. Backfill display_name ──────────────────────────────────────────
    # Federal already set above
    # States: use full state name
    for code, name in STATE_NAMES.items():
        safe_name = name.replace("'", "''")
        op.execute(f"""
            UPDATE jurisdictions
            SET display_name = '{safe_name}'
            WHERE level = 'state' AND state = '{code}' AND display_name IS NULL
        """)

    # Fallback for any state not in the lookup
    op.execute("""
        UPDATE jurisdictions
        SET display_name = state
        WHERE level = 'state' AND display_name IS NULL
    """)

    # County rows: "county, STATE"
    op.execute("""
        UPDATE jurisdictions
        SET display_name = COALESCE(county, city) || ', ' || state
        WHERE level = 'county' AND display_name IS NULL
    """)

    # City rows: "city, STATE"
    op.execute("""
        UPDATE jurisdictions
        SET display_name = city || ', ' || state
        WHERE level = 'city' AND display_name IS NULL AND city IS NOT NULL
    """)

    # Catch-all for any remaining NULLs
    op.execute("""
        UPDATE jurisdictions
        SET display_name = COALESCE(city, '') || CASE WHEN city IS NOT NULL THEN ', ' ELSE '' END || state
        WHERE display_name IS NULL
    """)

    # ── 7. Make display_name NOT NULL ─────────────────────────────────────
    op.execute("""
        ALTER TABLE jurisdictions ALTER COLUMN display_name SET NOT NULL
    """)

    # ── 8. Add indexes ────────────────────────────────────────────────────
    op.execute("CREATE INDEX IF NOT EXISTS ix_jurisdictions_level ON jurisdictions(level)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_jurisdictions_authority_type ON jurisdictions(authority_type)")

    # Partial unique index: prevent duplicate state-level rows
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_jurisdictions_state_level
        ON jurisdictions (state)
        WHERE city IS NULL AND level IN ('federal', 'state')
    """)

    # Replace old UNIQUE(city, state) with COALESCE-based index for NULL handling
    # First drop existing constraint if it exists
    op.execute("""
        DO $$
        BEGIN
            -- Drop unique constraint
            ALTER TABLE jurisdictions DROP CONSTRAINT IF EXISTS jurisdictions_city_state_key;
        EXCEPTION WHEN undefined_object THEN
            NULL;
        END $$
    """)
    op.execute("""
        DROP INDEX IF EXISTS jurisdictions_city_state_key
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_jurisdictions_city_state
        ON jurisdictions (COALESCE(city, ''), state)
    """)

    # ── 9. Add facility_attributes to business_locations ──────────────────
    op.execute("""
        ALTER TABLE business_locations
        ADD COLUMN IF NOT EXISTS facility_attributes JSONB
    """)


def downgrade():
    # Remove facility_attributes
    op.execute("ALTER TABLE business_locations DROP COLUMN IF EXISTS facility_attributes")

    # Remove indexes
    op.execute("DROP INDEX IF EXISTS uq_jurisdictions_city_state")
    op.execute("DROP INDEX IF EXISTS uq_jurisdictions_state_level")
    op.execute("DROP INDEX IF EXISTS ix_jurisdictions_authority_type")
    op.execute("DROP INDEX IF EXISTS ix_jurisdictions_level")

    # Remove federal row
    op.execute("DELETE FROM jurisdictions WHERE level = 'federal' AND state = 'US'")

    # Restore city NOT NULL (set NULLs back to empty string first)
    op.execute("UPDATE jurisdictions SET city = '' WHERE city IS NULL")
    op.execute("ALTER TABLE jurisdictions ALTER COLUMN city SET NOT NULL")

    # Remove new columns
    op.execute("ALTER TABLE jurisdictions DROP COLUMN IF EXISTS authority_type")
    op.execute("ALTER TABLE jurisdictions DROP COLUMN IF EXISTS display_name")
    op.execute("ALTER TABLE jurisdictions DROP COLUMN IF EXISTS level")

    # Restore original unique constraint
    op.execute("""
        ALTER TABLE jurisdictions ADD CONSTRAINT jurisdictions_city_state_key UNIQUE (city, state)
    """)
