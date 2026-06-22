"""Venue / nuclear-verdict severity reference (casualty exposure dimension)

Revision ID: venuesev01
Revises: ctrlev01
Create Date: 2026-06-21

Venue is the single biggest severity lever in casualty (nuclear verdicts, social
inflation). We already own the exposure geography (business_locations.state/county);
this adds the severity side: a curated reference of plaintiff-friendly /
nuclear-verdict venues, seeded from FREE public sources (ATRA "Judicial
Hellholes", US Chamber ILR, published nuclear-verdict reporting). Joined to a
company's locations and surfaced in the submission packet + risk profile.

`county = ''` is the STATE baseline; a non-empty county overrides it. Severity is
a directional reputational flag (the underlying lists are advocacy-flavored), not
an actuarial price — sources are labeled on every row.
"""

from alembic import op


revision = "venuesev01"
down_revision = "ctrlev01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS venue_severity (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            state       VARCHAR(2)  NOT NULL,
            county      VARCHAR(100) NOT NULL DEFAULT '',  -- '' = state baseline
            tier        VARCHAR(12) NOT NULL
                          CHECK (tier IN ('severe','high','elevated','moderate','low')),
            score       INTEGER NOT NULL DEFAULT 10,       -- severity 0-100, higher = worse
            source      VARCHAR(80) NOT NULL,
            note        TEXT,
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_venue_severity UNIQUE (state, county)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_venue_severity_state ON venue_severity(state)")

    # Curated starter set from free public sources. Score: severe 90 / high 70 /
    # elevated 50 / moderate 30 / low 10. State baselines (county='') + notable
    # county overrides. Editable; refresh annually from the same free reports.
    op.execute(
        """
        INSERT INTO venue_severity (state, county, tier, score, source, note) VALUES
        -- state baselines
        ('GA','', 'severe',  90, 'ATRA Judicial Hellholes 2024', 'Ranked #1 judicial hellhole; large verdicts statewide'),
        ('LA','', 'high',    70, 'ATRA Judicial Hellholes',      'Plaintiff-friendly; coastal/industrial litigation'),
        ('CA','', 'high',    70, 'ATRA / nuclear-verdict data',  'PAGA + high verdicts; LA County severe'),
        ('NY','', 'high',    70, 'ATRA Judicial Hellholes',      'NYC severe; Labor Law 240/241 exposure'),
        ('SC','', 'high',    70, 'ATRA Judicial Hellholes',      'Asbestos docket + venue concerns'),
        ('PA','', 'elevated',50, 'ATRA Judicial Hellholes',      'Philadelphia CCP severe'),
        ('IL','', 'elevated',50, 'ATRA Judicial Hellholes',      'Cook + Madison/St. Clair severe'),
        ('KY','', 'elevated',50, 'ATRA Judicial Hellholes',      'Plaintiff-friendly trends'),
        ('NJ','', 'elevated',50, 'ATRA Judicial Hellholes',      'Consumer-litigation exposure'),
        ('MO','', 'elevated',50, 'ATRA Judicial Hellholes',      'St. Louis severe'),
        ('MI','', 'moderate',30, 'US Chamber ILR',               'Wayne County elevated'),
        ('WA','', 'moderate',30, 'US Chamber ILR',               'King County elevated'),
        ('TX','', 'moderate',30, 'ATRA / nuclear-verdict data',  'Defense-friendly post-reform; Harris/Midland elevated'),
        ('FL','', 'moderate',30, 'post-2023 tort reform',        'Improved after 2023 tort reform'),
        -- county overrides (store WITHOUT the word "County"; matched case-insensitively)
        ('GA','Fulton',          'severe', 90, 'nuclear-verdict venue', 'Atlanta — frequent large verdicts'),
        ('PA','Philadelphia',    'severe', 90, 'nuclear-verdict venue', 'Philadelphia Court of Common Pleas'),
        ('IL','Cook',            'severe', 90, 'nuclear-verdict venue', 'Cook County'),
        ('IL','Madison',         'elevated',50, 'asbestos docket',       'Madison County asbestos'),
        ('CA','Los Angeles',     'severe', 90, 'nuclear-verdict venue', 'LA County'),
        ('NY','Bronx',           'high',   70, 'plaintiff-friendly venue','Bronx County'),
        ('TX','Harris',          'high',   70, 'nuclear-verdict venue', 'Houston / Harris County'),
        ('TX','Midland',         'elevated',50, 'energy-sector verdicts', 'Oilfield/energy verdicts'),
        ('LA','Orleans',         'high',   70, 'plaintiff-friendly venue','New Orleans'),
        ('MO','St. Louis City',  'severe', 90, 'nuclear-verdict venue', 'City of St. Louis')
        ON CONFLICT ON CONSTRAINT uq_venue_severity DO NOTHING
        """
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS venue_severity")
