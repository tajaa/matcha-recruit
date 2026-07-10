"""backfill jurisdiction_requirements.regulation_key + key_definition_id

The store-side codify keys were frozen at migration p1q2r3s4t5u6 (a one-time
split of requirement_key) and never maintained since — the app writer
_upsert_requirements_additive wrote only the composite requirement_key. Result:
every row created after that backfill has regulation_key NULL, so the
scope↔store codified join (resolve_scope / labor_scope, keyed on
regulation_key) is blind to all recent research.

This re-runs the backfill for the NULL rows and unifies the minimum_wage
rate_type dialect into the registry vocabulary (matching read-side
compliance_evals/keys.normalize_key), so old and new rows share one key
vocabulary and the codified join finally works. The companion code change makes
_upsert_requirements_additive keep both columns current going forward.

Idempotent — every statement is gated on IS NULL and safe to re-run. NOTE:
scripts/ingest_research_md.py still writes regulation_key without
key_definition_id; statement 3 (and the reconcile endpoint) heals those.

Revision ID: codify01
Revises: scoperg01
Create Date: 2026-07-10
"""
from typing import Sequence, Union

from alembic import op


revision: str = "codify01"
down_revision: Union[str, Sequence[str], None] = "scoperg01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Bare key = last segment of the composite requirement_key. Matches the
    #    read side (_bare_key: requirement_key.rsplit(':', 1)[-1]); correct for
    #    all three shapes (category:regkey, minimum_wage:rate_type,
    #    aet:category:regkey).
    conn.exec_driver_sql(
        """
        UPDATE jurisdiction_requirements
        SET regulation_key = regexp_replace(requirement_key, '^.*:', '')
        WHERE regulation_key IS NULL
        """
    )

    # 2. Normalize the minimum_wage rate_type dialect into registry vocabulary
    #    (mirrors compliance_evals/keys.normalize_key, incl. the level-sensitivity
    #    of 'general'). Also unifies the pre-migration dialect rows so the column
    #    speaks ONE vocabulary. Read-safe: normalize_key is idempotent over
    #    registry vocab, so completeness/core_spine results are unchanged — the
    #    codified join only gains matches.
    conn.exec_driver_sql(
        """
        UPDATE jurisdiction_requirements
        SET regulation_key = CASE regulation_key
            WHEN 'general' THEN CASE
                WHEN LOWER(COALESCE(jurisdiction_level, '')) IN ('city', 'county', 'special_district')
                    THEN 'local_minimum_wage'
                WHEN LOWER(COALESCE(jurisdiction_level, '')) IN ('federal', 'national')
                    THEN 'national_minimum_wage'
                ELSE 'state_minimum_wage' END
            WHEN 'tipped' THEN 'tipped_minimum_wage'
            WHEN 'exempt_salary' THEN 'exempt_salary_threshold'
            WHEN 'fast_food' THEN 'fast_food_minimum_wage'
            WHEN 'healthcare' THEN 'healthcare_minimum_wage'
            WHEN 'large_employer' THEN 'large_employer_minimum_wage'
            WHEN 'small_employer' THEN 'small_employer_minimum_wage'
            ELSE regulation_key END
        WHERE category = 'minimum_wage'
          AND regulation_key IN ('general', 'tipped', 'exempt_salary', 'fast_food',
                                 'healthcare', 'large_employer', 'small_employer')
        """
    )

    # 3. RKD link (same join as p1q2r3s4t5u6). Only rows missing the link.
    conn.exec_driver_sql(
        """
        UPDATE jurisdiction_requirements jr
        SET key_definition_id = rkd.id
        FROM regulation_key_definitions rkd
        WHERE jr.category = rkd.category_slug
          AND jr.regulation_key = rkd.key
          AND jr.key_definition_id IS NULL
        """
    )


def downgrade() -> None:
    # No-op: the columns predate this revision and the backfill is not
    # meaningfully reversible (the prior NULLs carried no information).
    pass
