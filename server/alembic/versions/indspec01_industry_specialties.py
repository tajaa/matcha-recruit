"""add industry_specialties registry

The admin Industry Requirements sidebar rendered its specialty checkboxes from a
hardcoded frontend constant (`client/src/data/industryConstants.ts`). Seven of
its sixteen healthcare entries — primary_care, cardiology, orthopedics,
neurology, dermatology, emergency, surgery — had **no `compliance_categories`
row tagged `healthcare:<slug>` behind them**, so ticking them changed nothing at
all. Meanwhile there is no way to add a real specialty short of writing a
migration, because `compliance_categories` is only ever populated by migrations.

This table makes the specialty list data, so an admin can derive and confirm a
new one (e.g. ophthalmology) at runtime. It is seeded from the subtags that
actually exist today rather than from the frontend's aspirational list — the
dead checkboxes simply stop being offered.

Revision ID: indspec01
Revises: jureval01
Create Date: 2026-07-09

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'indspec01'
down_revision: Union[str, Sequence[str], None] = 'jureval01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS industry_specialties (
            industry_tag     TEXT PRIMARY KEY,
            parent_industry  TEXT NOT NULL,
            slug             TEXT NOT NULL,
            label            TEXT NOT NULL,
            research_context TEXT,
            status           TEXT NOT NULL DEFAULT 'active',
            discovered_by    TEXT NOT NULL DEFAULT 'seed',
            confirmed_by     UUID REFERENCES users(id) ON DELETE SET NULL,
            confirmed_at     TIMESTAMP,
            created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (parent_industry, slug)
        )
    """)
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_industry_specialties_parent "
        "ON industry_specialties(parent_industry, status)"
    )

    # Seed from the live category tags, not a hand-typed list: whatever
    # `compliance_categories.industry_tag` actually carries as `parent:slug` is
    # by definition a specialty that resolves to at least one category. Label is
    # derived from the slug (`behavioral_health` -> `Behavioral Health`).
    conn.exec_driver_sql("""
        INSERT INTO industry_specialties (
            industry_tag, parent_industry, slug, label, discovered_by, confirmed_at
        )
        SELECT DISTINCT
            industry_tag,
            split_part(industry_tag, ':', 1),
            split_part(industry_tag, ':', 2),
            initcap(replace(split_part(industry_tag, ':', 2), '_', ' ')),
            'seed',
            NOW()
        FROM compliance_categories
        WHERE industry_tag LIKE '%:%'
          AND split_part(industry_tag, ':', 2) <> ''
        ON CONFLICT (industry_tag) DO NOTHING
    """)


def downgrade() -> None:
    op.get_bind().exec_driver_sql("DROP TABLE IF EXISTS industry_specialties")
