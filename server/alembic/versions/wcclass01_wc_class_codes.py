"""WC class-code dimension: reference class codes + per-client class exposures

Revision ID: wcclass01
Revises: wfcomp01
Create Date: 2026-06-20

Class-level WC underwriting (WTW p.32–33 "class-level underwriting discipline").
Licensed NCCI class-rate data isn't available, so this ships the schema + broker
manual entry + a small illustrative reference seed (source='seed (demo)').
- wc_class_codes            — reference: state + NCCI class code + base rate.
- company_wc_class_exposures — broker-entered payroll/headcount per class per client.
"""

from alembic import op


revision = "wcclass01"
down_revision = "wfcomp01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wc_class_codes (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            state       VARCHAR(2) NOT NULL DEFAULT 'US',
            class_code  VARCHAR(8) NOT NULL,
            description VARCHAR(255) NOT NULL,
            base_rate   NUMERIC(8,2),           -- manual rate per $100 of payroll
            source      VARCHAR(64) NOT NULL DEFAULT 'seed (demo)',
            created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_wc_class_code UNIQUE (state, class_code)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS company_wc_class_exposures (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id  UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            broker_id   UUID REFERENCES brokers(id) ON DELETE SET NULL,
            class_code  VARCHAR(8) NOT NULL,
            state       VARCHAR(2) NOT NULL DEFAULT 'US',
            payroll     NUMERIC(14,2),
            headcount   INTEGER,
            note        TEXT,
            created_by  UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_wc_class_exposures_company ON company_wc_class_exposures(company_id)"
    )

    # Illustrative national reference seed (flagged 'seed (demo)' — replace with a
    # licensed NCCI/state-bureau feed). Rates are per $100 of payroll, rough order-of-magnitude.
    op.execute(
        """
        INSERT INTO wc_class_codes (state, class_code, description, base_rate, source) VALUES
          ('US','8810','Clerical office employees',0.14,'seed (demo)'),
          ('US','8742','Outside sales / messengers',0.40,'seed (demo)'),
          ('US','8868','Professional employees / college staff',0.30,'seed (demo)'),
          ('US','9082','Restaurant / food service',1.50,'seed (demo)'),
          ('US','8835','Home health / nursing care',3.00,'seed (demo)'),
          ('US','8833','Hospital professional employees',1.20,'seed (demo)'),
          ('US','5403','Carpentry / construction',8.50,'seed (demo)'),
          ('US','5022','Masonry',7.00,'seed (demo)'),
          ('US','7228','Trucking / local hauling',9.00,'seed (demo)'),
          ('US','8017','Retail store',1.80,'seed (demo)')
        ON CONFLICT ON CONSTRAINT uq_wc_class_code DO NOTHING
        """
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS company_wc_class_exposures")
    op.execute("DROP TABLE IF EXISTS wc_class_codes")
