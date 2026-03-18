"""04: Add granular policy columns to jurisdiction_requirements + create policy_change_log

Revision ID: zo3p4q5r6s7t
Revises: zn2o3p4q5r6s
Create Date: 2026-03-17
"""

from alembic import op


revision = "zo3p4q5r6s7t"
down_revision = "zn2o3p4q5r6s"
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. Add new columns to jurisdiction_requirements ───────────────────
    op.execute("""
        ALTER TABLE jurisdiction_requirements
        ADD COLUMN IF NOT EXISTS canonical_key VARCHAR(255) UNIQUE
    """)
    op.execute("""
        ALTER TABLE jurisdiction_requirements
        ADD COLUMN IF NOT EXISTS category_id UUID REFERENCES compliance_categories(id)
    """)
    op.execute("""
        ALTER TABLE jurisdiction_requirements
        ADD COLUMN IF NOT EXISTS summary TEXT
    """)
    op.execute("""
        ALTER TABLE jurisdiction_requirements
        ADD COLUMN IF NOT EXISTS full_text_reference TEXT
    """)
    op.execute("""
        ALTER TABLE jurisdiction_requirements
        ADD COLUMN IF NOT EXISTS statute_citation VARCHAR(500)
    """)
    op.execute("""
        ALTER TABLE jurisdiction_requirements
        ADD COLUMN IF NOT EXISTS fetch_hash VARCHAR(64)
    """)
    op.execute("""
        ALTER TABLE jurisdiction_requirements
        ADD COLUMN IF NOT EXISTS status requirement_status_enum NOT NULL DEFAULT 'active'
    """)
    op.execute("""
        ALTER TABLE jurisdiction_requirements
        ADD COLUMN IF NOT EXISTS superseded_by_id UUID REFERENCES jurisdiction_requirements(id)
    """)
    op.execute("""
        ALTER TABLE jurisdiction_requirements
        ADD COLUMN IF NOT EXISTS applicable_entity_types JSONB
    """)
    op.execute("""
        ALTER TABLE jurisdiction_requirements
        ADD COLUMN IF NOT EXISTS trigger_conditions JSONB
    """)
    op.execute("""
        ALTER TABLE jurisdiction_requirements
        ADD COLUMN IF NOT EXISTS metadata JSONB
    """)

    # ── 2. Migrate source_tier: INTEGER → source_tier_enum ────────────────
    op.execute("""
        ALTER TABLE jurisdiction_requirements
        ADD COLUMN IF NOT EXISTS source_tier_new source_tier_enum
    """)
    op.execute("""
        UPDATE jurisdiction_requirements SET source_tier_new =
            CASE source_tier
                WHEN 1 THEN 'tier_1_government'::source_tier_enum
                WHEN 2 THEN 'tier_2_official_secondary'::source_tier_enum
                ELSE 'tier_3_aggregator'::source_tier_enum
            END
        WHERE source_tier IS NOT NULL
    """)
    # Set default for rows with NULL source_tier
    op.execute("""
        UPDATE jurisdiction_requirements
        SET source_tier_new = 'tier_3_aggregator'::source_tier_enum
        WHERE source_tier_new IS NULL
    """)
    op.execute("""
        ALTER TABLE jurisdiction_requirements DROP COLUMN IF EXISTS source_tier
    """)
    op.execute("""
        ALTER TABLE jurisdiction_requirements RENAME COLUMN source_tier_new TO source_tier
    """)

    # ── 3. Backfill category_id from compliance_categories ────────────────
    op.execute("""
        UPDATE jurisdiction_requirements jr
        SET category_id = cc.id
        FROM compliance_categories cc
        WHERE cc.slug = jr.category
        AND jr.category_id IS NULL
    """)

    # Insert uncategorized fallback for any orphaned rows
    op.execute("""
        INSERT INTO compliance_categories (slug, name, domain, "group", sort_order)
        SELECT 'uncategorized', 'Uncategorized', 'labor', 'supplementary', 999
        WHERE NOT EXISTS (SELECT 1 FROM compliance_categories WHERE slug = 'uncategorized')
        AND EXISTS (SELECT 1 FROM jurisdiction_requirements WHERE category_id IS NULL)
    """)
    op.execute("""
        UPDATE jurisdiction_requirements
        SET category_id = (SELECT id FROM compliance_categories WHERE slug = 'uncategorized')
        WHERE category_id IS NULL
    """)

    # Now enforce NOT NULL
    op.execute("""
        ALTER TABLE jurisdiction_requirements ALTER COLUMN category_id SET NOT NULL
    """)

    # ── 4. Backfill canonical_key ─────────────────────────────────────────
    # Format: {state}_{city_or_state}_{category}_{requirement_key_slug}
    op.execute("""
        UPDATE jurisdiction_requirements jr
        SET canonical_key = LOWER(
            j.state || '_' ||
            COALESCE(REPLACE(LOWER(j.city), ' ', '_'), LOWER(j.state)) || '_' ||
            jr.category || '_' ||
            REPLACE(LOWER(LEFT(jr.requirement_key, 80)), ' ', '_')
        )
        FROM jurisdictions j
        WHERE jr.jurisdiction_id = j.id
        AND jr.canonical_key IS NULL
    """)

    # Handle any duplicates from backfill by appending row number
    op.execute("""
        WITH dupes AS (
            SELECT id, canonical_key,
                   ROW_NUMBER() OVER (PARTITION BY canonical_key ORDER BY created_at) AS rn
            FROM jurisdiction_requirements
            WHERE canonical_key IS NOT NULL
        )
        UPDATE jurisdiction_requirements jr
        SET canonical_key = jr.canonical_key || '_' || d.rn
        FROM dupes d
        WHERE jr.id = d.id AND d.rn > 1
    """)

    # ── 5. Add indexes ────────────────────────────────────────────────────
    op.execute("CREATE INDEX IF NOT EXISTS ix_jurisdiction_requirements_category_id ON jurisdiction_requirements(category_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_jurisdiction_requirements_status ON jurisdiction_requirements(status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_jurisdiction_requirements_canonical_key ON jurisdiction_requirements(canonical_key)")

    # ── 6. Create policy_change_log table ─────────────────────────────────
    op.execute("""
        CREATE TABLE policy_change_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            requirement_id UUID NOT NULL REFERENCES jurisdiction_requirements(id) ON DELETE CASCADE,
            field_changed VARCHAR(100) NOT NULL,
            old_value TEXT,
            new_value TEXT,
            changed_at TIMESTAMP DEFAULT NOW(),
            change_source change_source_enum NOT NULL,
            change_reason TEXT
        )
    """)
    op.execute("CREATE INDEX ix_policy_change_log_requirement_id ON policy_change_log(requirement_id)")
    op.execute("CREATE INDEX ix_policy_change_log_changed_at ON policy_change_log(changed_at)")


def downgrade():
    # Drop policy_change_log
    op.execute("DROP TABLE IF EXISTS policy_change_log")

    # Drop indexes
    op.execute("DROP INDEX IF EXISTS ix_jurisdiction_requirements_canonical_key")
    op.execute("DROP INDEX IF EXISTS ix_jurisdiction_requirements_status")
    op.execute("DROP INDEX IF EXISTS ix_jurisdiction_requirements_category_id")

    # Revert source_tier: enum → integer
    op.execute("""
        ALTER TABLE jurisdiction_requirements
        ADD COLUMN IF NOT EXISTS source_tier_old INTEGER DEFAULT 3
    """)
    op.execute("""
        UPDATE jurisdiction_requirements SET source_tier_old =
            CASE source_tier::text
                WHEN 'tier_1_government' THEN 1
                WHEN 'tier_2_official_secondary' THEN 2
                ELSE 3
            END
        WHERE source_tier IS NOT NULL
    """)
    op.execute("ALTER TABLE jurisdiction_requirements DROP COLUMN IF EXISTS source_tier")
    op.execute("ALTER TABLE jurisdiction_requirements RENAME COLUMN source_tier_old TO source_tier")

    # Remove category_id NOT NULL constraint and column
    op.execute("ALTER TABLE jurisdiction_requirements ALTER COLUMN category_id DROP NOT NULL")

    # Drop new columns
    op.execute("ALTER TABLE jurisdiction_requirements DROP COLUMN IF EXISTS metadata")
    op.execute("ALTER TABLE jurisdiction_requirements DROP COLUMN IF EXISTS trigger_conditions")
    op.execute("ALTER TABLE jurisdiction_requirements DROP COLUMN IF EXISTS applicable_entity_types")
    op.execute("ALTER TABLE jurisdiction_requirements DROP COLUMN IF EXISTS superseded_by_id")
    op.execute("ALTER TABLE jurisdiction_requirements DROP COLUMN IF EXISTS status")
    op.execute("ALTER TABLE jurisdiction_requirements DROP COLUMN IF EXISTS fetch_hash")
    op.execute("ALTER TABLE jurisdiction_requirements DROP COLUMN IF EXISTS statute_citation")
    op.execute("ALTER TABLE jurisdiction_requirements DROP COLUMN IF EXISTS full_text_reference")
    op.execute("ALTER TABLE jurisdiction_requirements DROP COLUMN IF EXISTS summary")
    op.execute("ALTER TABLE jurisdiction_requirements DROP COLUMN IF EXISTS category_id")
    op.execute("ALTER TABLE jurisdiction_requirements DROP COLUMN IF EXISTS canonical_key")

    # Remove uncategorized fallback
    op.execute("DELETE FROM compliance_categories WHERE slug = 'uncategorized'")
