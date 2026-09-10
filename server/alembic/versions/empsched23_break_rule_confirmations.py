"""Record organization decisions on system-expected scheduling break rules.

The decision is bound to a hash of the rule payload and the organization,
location, jurisdiction, industry, headcount, and effective-date context. A
context change therefore makes the old decision inapplicable without deleting
its audit record.
"""

from alembic import op


revision = "empsched23"
down_revision = "empsched22"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE company_schedule_break_rule_confirmations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
            rule_set_id UUID NOT NULL REFERENCES schedule_break_rule_sets(id) ON DELETE CASCADE,
            context_hash VARCHAR(64) NOT NULL
                CHECK (context_hash ~ '^[0-9a-f]{64}$'),
            decision VARCHAR(20) NOT NULL CHECK (decision IN ('confirmed', 'rejected')),
            confirmed_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            confirmed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT company_schedule_break_rule_confirmations_unique
                UNIQUE (company_id, location_id, rule_set_id, context_hash)
        )
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
