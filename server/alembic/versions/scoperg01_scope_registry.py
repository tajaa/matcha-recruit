"""add scope registry schema (business categories, authority indexes, strata)

The authority-anchored scoping layer of SCOPE_REGISTRY_PLAN.md §4. Nothing
here is read at request time yet — commit 2 ships the schema plus the
canonical taxonomy; ingest/classify/resolve land in later commits.

Tables:
  * business_categories             — the one canonical taxonomy every legacy
                                      vocabulary maps into (seeded below; code
                                      twin in scope_registry/categories.py,
                                      parity pinned by test)
  * authority_indexes               — enumerable (eCFR) or curated (CA/LAMC)
                                      authority sources
  * authority_index_items           — one row per enumerated citation
                                      (subpart AND section, parent-linked)
  * authority_item_classifications  — THE primitive: one disposition per item.
                                      regulation_key NULL = applicable but not
                                      yet codified, i.e. the fetch queue
  * scope_strata                    — derived, materialized coordinates;
                                      never hand-edited
  * scope_resolutions               — resolution cache ("second warehouse =
                                      zero work")
  * scope_shadow_log                — resolve_scope vs expand_scope diffs
                                      during the shadow period

Plan §4 says ``down_revision = 'jureval01'`` — that is stale: ``indspec01``
already revises ``jureval01``, so this chains off ``indspec01`` to keep the
history linear.

Not auto-applied — the user runs ./scripts/migrate-dev.sh.

Revision ID: scoperg01
Revises: indspec01
Create Date: 2026-07-10

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'scoperg01'
down_revision: Union[str, Sequence[str], None] = 'indspec01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS business_categories (
            slug            TEXT PRIMARY KEY,
            label           TEXT NOT NULL,
            parent_slug     TEXT REFERENCES business_categories(slug) ON DELETE RESTRICT,
            naics_codes     TEXT[] NOT NULL DEFAULT '{}',
            aliases         TEXT[] NOT NULL DEFAULT '{}',
            legacy_industry TEXT,
            created_at      TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_business_categories_parent "
        "ON business_categories(parent_slug)"
    )

    # Seed — snapshot of scope_registry/categories.py:_SEED, parents before
    # children (self-FK). tests/scope_registry/test_migration_parity.py pins
    # this block against the code taxonomy.
    conn.exec_driver_sql("""
        INSERT INTO business_categories (slug, label, parent_slug, naics_codes, aliases, legacy_industry) VALUES
        ('hospitality', 'Restaurant / Hospitality', NULL, '{72}',
         '{restaurant,food,hotel,"restaurant / hospitality",restaurant_hospitality}', 'hospitality'),
        ('fast_food', 'Fast Food', 'hospitality', '{722513}', '{"fast food"}', 'fast food'),
        ('healthcare', 'Healthcare', NULL, '{62}',
         '{health,medical,clinic,hospital,nursing,pharmacy,dental,physician,outpatient,ambulatory,oncology,primary_care,cardiology,pediatric,behavioral_health,telehealth,managed_care,devices,transplant,orthopedics,neurology,dermatology,emergency,surgery}',
         'healthcare'),
        ('medical_offices', 'Medical Offices', 'healthcare', '{621}',
         '{"medical office","medical offices","doctors office"}', 'healthcare'),
        ('ophthalmology', 'Ophthalmology', 'medical_offices', '{621111,621320}',
         '{ophthalmology,optometry,"eye care"}', 'healthcare'),
        ('biotech', 'Biotech / Life Sciences', NULL, '{3254,5417}',
         '{pharma,pharmaceutical,pharmaceuticals,life_sciences,"life sciences",biopharma}', 'biotech'),
        ('retail', 'Retail', NULL, '{44,45}', '{store,shop}', 'retail'),
        ('manufacturing', 'Manufacturing', NULL, '{31,32,33}',
         '{industrial,factory,"construction / manufacturing",construction_manufacturing}', 'manufacturing'),
        ('construction', 'Construction', NULL, '{23}', '{contractor,builder}', 'manufacturing'),
        ('warehousing', 'Warehousing & Storage', NULL, '{493}',
         '{warehouse,"distribution center","distribution centre","fulfillment center","fulfilment center",logistics,3pl}',
         NULL),
        ('transportation', 'Transportation', NULL, '{48,49}',
         '{shipping,trucking,freight,delivery,transit}', NULL),
        ('technology', 'Tech / Professional Services', NULL, '{51,5415}',
         '{software,saas,"professional services",consulting,tech,"tech / professional services",tech_professional}',
         'technology'),
        ('education', 'Education', NULL, '{61}', '{school,university}', NULL),
        ('legal', 'Legal Services', NULL, '{5411}', '{"law firm",attorney}', NULL),
        ('financial_services', 'Financial Services', NULL, '{52}',
         '{finance,banking,insurance}', NULL),
        ('real_estate', 'Real Estate', NULL, '{53}', '{realty,"property management"}', NULL),
        ('nonprofit', 'Nonprofit', NULL, '{813}', '{non-profit,"not for profit",charity}', NULL)
        ON CONFLICT (slug) DO NOTHING
    """)

    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS authority_indexes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug VARCHAR(80) NOT NULL UNIQUE,
            name TEXT NOT NULL,
            level VARCHAR(20) NOT NULL,
            jurisdiction_id UUID REFERENCES jurisdictions(id) ON DELETE CASCADE,
            source_type VARCHAR(20) NOT NULL
                CHECK (source_type IN ('ecfr', 'federal_register', 'curated')),
            source_ref JSONB,
            domain_categories TEXT[] NOT NULL DEFAULT '{}',
            domain_excludes TEXT[] NOT NULL DEFAULT '{}',
            enumerable BOOLEAN NOT NULL DEFAULT false,
            item_count INTEGER NOT NULL DEFAULT 0,
            unclassified_count INTEGER NOT NULL DEFAULT 0,
            last_ingested_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_authority_indexes_jur "
        "ON authority_indexes(jurisdiction_id)"
    )

    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS authority_index_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            authority_index_id UUID NOT NULL
                REFERENCES authority_indexes(id) ON DELETE CASCADE,
            citation TEXT NOT NULL,
            heading TEXT,
            hierarchy JSONB,
            parent_item_id UUID REFERENCES authority_index_items(id) ON DELETE SET NULL,
            source_url TEXT,
            amendment_date DATE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (authority_index_id, citation)
        )
    """)
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_authority_items_parent "
        "ON authority_index_items(parent_item_id)"
    )

    # The primitive. Items with NO row here are `unclassified` — the definitive
    # remaining-work counter. regulation_key NULL = applicable-but-not-yet-
    # codified = the fetch queue.
    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS authority_item_classifications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            item_id UUID NOT NULL UNIQUE
                REFERENCES authority_index_items(id) ON DELETE CASCADE,
            disposition VARCHAR(30) NOT NULL CHECK (disposition IN
                ('universal_in_domain', 'category_specific', 'conditional', 'excluded')),
            applies_to_categories TEXT[] NOT NULL DEFAULT '{}',
            excludes_categories TEXT[] NOT NULL DEFAULT '{}',
            entity_condition JSONB,
            excluded_reason TEXT,
            regulation_key TEXT,
            key_definition_id UUID
                REFERENCES regulation_key_definitions(id) ON DELETE SET NULL,
            inherits_from_item_id UUID
                REFERENCES authority_index_items(id) ON DELETE SET NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'provisional'
                CHECK (status IN ('provisional', 'confirmed')),
            proposed_by VARCHAR(20) NOT NULL
                CHECK (proposed_by IN ('gemini', 'seed', 'admin')),
            confirmed_by UUID REFERENCES users(id) ON DELETE SET NULL,
            confirmed_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_item_classifications_key "
        "ON authority_item_classifications(regulation_key)"
    )
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_item_classifications_status "
        "ON authority_item_classifications(status)"
    )
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_item_classifications_applies "
        "ON authority_item_classifications USING GIN (applies_to_categories)"
    )

    # Derived, materialized, never hand-edited. Rebuilt by recompute_strata().
    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS scope_strata (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            level VARCHAR(20) NOT NULL,
            jurisdiction_id UUID REFERENCES jurisdictions(id) ON DELETE CASCADE,
            category_slug TEXT REFERENCES business_categories(slug) ON DELETE CASCADE,
            entity_condition JSONB,
            label TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            coverage_pct NUMERIC(5,2),
            item_count INTEGER NOT NULL DEFAULT 0,
            key_count INTEGER NOT NULL DEFAULT 0,
            refreshed_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    # jurisdiction_id NULL iff federal; category_slug NULL = ALL; entity_condition
    # NULL = base stratum. A plain UNIQUE lets duplicate NULL coordinates
    # through, so key on sentinel-coalesced expressions (jureval01 pattern).
    conn.exec_driver_sql("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_scope_strata_coordinate
        ON scope_strata (
            level,
            COALESCE(jurisdiction_id::text, ''),
            COALESCE(category_slug, ''),
            COALESCE(md5(entity_condition::text), '')
        )
    """)

    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS scope_resolutions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            coordinate_hash TEXT NOT NULL UNIQUE,
            stratum_ids UUID[] NOT NULL DEFAULT '{}',
            key_count INTEGER NOT NULL DEFAULT 0,
            uncodified_count INTEGER NOT NULL DEFAULT 0,
            provisional_count INTEGER NOT NULL DEFAULT 0,
            computed_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)

    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS scope_shadow_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID,
            company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
            resolve_keys TEXT[] NOT NULL DEFAULT '{}',
            expand_keys TEXT[] NOT NULL DEFAULT '{}',
            only_in_resolve TEXT[] NOT NULL DEFAULT '{}',
            only_in_expand TEXT[] NOT NULL DEFAULT '{}',
            unmodeled_coordinates JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_scope_shadow_company "
        "ON scope_shadow_log(company_id, created_at DESC)"
    )

    # Scheduler row — seeded DISABLED. The hourly worker restart must never
    # sweep .gov unattended (jureval01 pattern).
    conn.exec_driver_sql("""
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES (
            'scope_registry_authority',
            'Scope Registry Authority Sync',
            'Re-ingest enumerable authority indexes (eCFR) and flag structural drift.',
            false,
            1
        )
        ON CONFLICT (task_key) DO NOTHING
    """)


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        "DELETE FROM scheduler_settings WHERE task_key = 'scope_registry_authority'"
    )
    conn.exec_driver_sql("DROP TABLE IF EXISTS scope_shadow_log")
    conn.exec_driver_sql("DROP TABLE IF EXISTS scope_resolutions")
    conn.exec_driver_sql("DROP TABLE IF EXISTS scope_strata")
    conn.exec_driver_sql("DROP TABLE IF EXISTS authority_item_classifications")
    conn.exec_driver_sql("DROP TABLE IF EXISTS authority_index_items")
    conn.exec_driver_sql("DROP TABLE IF EXISTS authority_indexes")
    conn.exec_driver_sql("DROP TABLE IF EXISTS business_categories")
