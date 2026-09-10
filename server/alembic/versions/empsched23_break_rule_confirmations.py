"""Record organization decisions on system-expected scheduling break rules.

The decision is bound to a hash of the rule payload and the organization,
location, jurisdiction, industry, and effective-date context. A stable context
change therefore makes the old decision inapplicable without deleting its
audit record. Existing approved mappings are grandfathered without fabricating
a tenant confirmation so the new gate cannot remove requirements already live.
"""

from sqlalchemy import text

from alembic import op

revision = "empsched23"
down_revision = "empsched22"
branch_labels = None
depends_on = None


def _grandfathered_rows(candidates, resolve_industry):
    """Return every pre-existing rule a location can select for any shift date."""

    rows = []
    grandfathered_rules = set()
    for candidate in candidates:
        naics = str(candidate["naics"] or "").strip()
        industry_code = (
            naics
            if naics
            else resolve_industry(candidate["company_industry"] or "") or None
        )
        rule_industry = candidate["rule_industry_code"]
        if rule_industry is not None and rule_industry != industry_code:
            continue
        rule_scope = (
            candidate["company_id"], candidate["location_id"], candidate["rule_set_id"],
        )
        if rule_scope in grandfathered_rules:
            continue
        grandfathered_rules.add(rule_scope)
        rows.append({
            "company_id": candidate["company_id"],
            "location_id": candidate["location_id"],
            "rule_set_id": candidate["rule_set_id"],
        })
    return rows


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE company_schedule_break_rule_confirmations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
            rule_set_id UUID NOT NULL REFERENCES schedule_break_rule_sets(id) ON DELETE CASCADE,
            context_hash VARCHAR(64)
                CHECK (context_hash IS NULL OR context_hash ~ '^[0-9a-f]{64}$'),
            decision VARCHAR(20) NOT NULL
                CHECK (decision IN ('confirmed', 'rejected', 'grandfathered')),
            confirmed_by UUID REFERENCES users(id) ON DELETE RESTRICT,
            confirmed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT company_schedule_break_rule_confirmations_shape CHECK (
                (decision = 'grandfathered' AND context_hash IS NULL AND confirmed_by IS NULL)
                OR
                (decision IN ('confirmed', 'rejected')
                 AND context_hash IS NOT NULL AND confirmed_by IS NOT NULL)
            ),
            CONSTRAINT company_schedule_break_rule_confirmations_unique
                UNIQUE (company_id, location_id, rule_set_id, context_hash)
        )
        """
    )

    # Before this table existed, every approved structured rule set was used
    # without a second tenant decision. Preserve every rule that the existing
    # company/location can select for any shift date, and name the compatibility
    # state honestly instead of attributing a decision to the rule reviewer.
    from app.core.services.scope_registry.categories import resolve_legacy_industry

    conn = op.get_bind()
    candidates = conn.execute(text("""
        WITH RECURSIVE location_jurisdictions AS (
            SELECT bl.company_id,
                   bl.id AS location_id,
                   bl.jurisdiction_id AS ancestor_id,
                   0 AS depth,
                   bl.naics,
                   c.industry AS company_industry
            FROM business_locations bl
            JOIN companies c ON c.id = bl.company_id
            WHERE bl.jurisdiction_id IS NOT NULL
            UNION ALL
            SELECT lj.company_id,
                   lj.location_id,
                   j.parent_id,
                   lj.depth + 1,
                   lj.naics,
                   lj.company_industry
            FROM location_jurisdictions lj
            JOIN jurisdictions j ON j.id = lj.ancestor_id
            WHERE j.parent_id IS NOT NULL
        )
        SELECT
               lj.company_id,
               lj.location_id,
               lj.naics,
               lj.company_industry,
               lj.depth,
               r.id AS rule_set_id,
               r.industry_code AS rule_industry_code,
               r.effective_from,
               r.effective_to
        FROM location_jurisdictions lj
        JOIN schedule_break_rule_sets r ON r.jurisdiction_id = lj.ancestor_id
        WHERE r.review_status = 'approved'
          AND r.is_active = true
        ORDER BY lj.company_id, lj.location_id, lj.depth ASC,
                 (r.industry_code IS NULL) ASC, r.effective_from DESC
    """)).mappings().all()

    rows = _grandfathered_rows(candidates, resolve_legacy_industry)

    if rows:
        conn.execute(text("""
            INSERT INTO company_schedule_break_rule_confirmations
                (company_id, location_id, rule_set_id, decision)
            VALUES
                (:company_id, :location_id, :rule_set_id, 'grandfathered')
        """), rows)
    op.execute(
        """
        CREATE UNIQUE INDEX company_schedule_break_rule_confirmations_grandfathered
        ON company_schedule_break_rule_confirmations
            (company_id, location_id, rule_set_id)
        WHERE decision = 'grandfathered'
        """
    )
    op.execute(
        """
        CREATE INDEX idx_company_schedule_break_rule_confirmations_lookup
        ON company_schedule_break_rule_confirmations
            (company_id, location_id, confirmed_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS company_schedule_break_rule_confirmations")
