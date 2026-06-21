"""Pay-equity study register (workforce_compliance)

Revision ID: payequity01
Revises: extintake01
Create Date: 2026-06-20

A business-first pay-equity audit register (WTW p.85 — underwriters ask about
pay equity; markets have a separate questionnaire). Logging a current study
flips the broker EPL `pay_equity` factor from attested → derived, like the
AI-audit register. next_due computed on write; overdue computed read-time.
"""

from alembic import op


revision = "payequity01"
down_revision = "extintake01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pay_equity_reviews (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id    UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            review_date   DATE,
            scope         VARCHAR(255),
            methodology   VARCHAR(255),
            gap_pct       NUMERIC(5,2),     -- adjusted pay gap %, if measured
            remediation   TEXT,
            cadence_days  INTEGER NOT NULL DEFAULT 365,
            next_due_date DATE,
            notes         TEXT,
            created_by    UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_pay_equity_reviews_company ON pay_equity_reviews(company_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS pay_equity_reviews")
