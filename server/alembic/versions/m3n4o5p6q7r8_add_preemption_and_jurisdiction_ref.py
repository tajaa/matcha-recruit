"""Add state preemption rules and jurisdiction reference tables

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-02-04

"""
from typing import Sequence, Union

from alembic import op

revision = 'm3n4o5p6q7r8'
down_revision = 'l2m3n4o5p6q7'
branch_labels = None
depends_on = None
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'm3n4o5p6q7r8'
down_revision: Union[str, None] = 'l2m3n4o5p6q7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── State Preemption Rules ──
    op.execute("""
        CREATE TABLE state_preemption_rules (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            state VARCHAR(2) NOT NULL,
            category VARCHAR(50) NOT NULL,
            allows_local_override BOOLEAN NOT NULL,
            notes TEXT,
            source_url TEXT,
            last_verified_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),

            UNIQUE(state, category)
        )
    """)

    # Seed minimum_wage preemption data
    op.execute("""
        INSERT INTO state_preemption_rules (state, category, allows_local_override, notes) VALUES
        ('CA', 'minimum_wage', true, 'Many cities have local minimums (SF, LA, Berkeley, etc.)'),
        ('CA', 'sick_leave', true, 'SF, LA, and others have local sick leave ordinances'),
        ('TX', 'minimum_wage', false, 'Preempted by state law - no local minimum wage ordinances allowed'),
        ('FL', 'minimum_wage', false, 'Preempted by Florida Statutes section 218.077'),
        ('GA', 'minimum_wage', false, 'Preempted by state law'),
        ('AL', 'minimum_wage', false, 'Preempted by SB 25 (2016)'),
        ('AZ', 'minimum_wage', false, 'Preempted by state law'),
        ('CO', 'minimum_wage', true, 'Denver has local minimum wage'),
        ('WA', 'minimum_wage', true, 'Seattle, SeaTac, Tukwila have local minimums'),
        ('NY', 'minimum_wage', true, 'NYC has different rate than rest of state'),
        ('MO', 'minimum_wage', false, 'Preempted by SB 722 (2015) - Kansas City minimum repealed'),
        ('OH', 'minimum_wage', false, 'Preempted - state constitutional amendment sets statewide rate'),
        ('IA', 'minimum_wage', false, 'Preempted by SF 295 (2017) - rolled back local minimums'),
        ('KY', 'minimum_wage', false, 'Preempted - Lexington minimum overturned by state law'),
        ('NC', 'minimum_wage', false, 'Preempted by state law'),
        ('SC', 'minimum_wage', false, 'Preempted by state law'),
        ('TN', 'minimum_wage', false, 'Preempted by state law'),
        ('MS', 'minimum_wage', false, 'Preempted by state law'),
        ('IN', 'minimum_wage', false, 'Preempted by state law'),
        ('WI', 'minimum_wage', false, 'Preempted by Act 10-related legislation'),
        ('MI', 'minimum_wage', false, 'Preempted by state law'),
        ('OR', 'minimum_wage', false, 'State sets tiered rates by region, no local override'),
        ('IL', 'minimum_wage', true, 'Chicago and Cook County have local minimums'),
        ('MN', 'minimum_wage', true, 'Minneapolis and St. Paul have local minimums'),
        ('NJ', 'minimum_wage', false, 'Statewide rate, no local override'),
        ('CT', 'minimum_wage', false, 'Statewide rate, no local override'),
        ('MA', 'minimum_wage', false, 'Statewide rate, no local override'),
        ('MD', 'minimum_wage', true, 'Montgomery County and Howard County have local rates'),
        ('ME', 'minimum_wage', true, 'Portland has had local minimum wage'),
        ('NM', 'minimum_wage', true, 'Santa Fe, Albuquerque, Las Cruces have local rates'),
        ('VA', 'minimum_wage', false, 'Preempted by state law (Dillon Rule state)')
        ON CONFLICT (state, category) DO NOTHING
    """)

    # ── Jurisdiction Reference ──
    op.execute("""
        CREATE TABLE jurisdiction_reference (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            city VARCHAR(100) NOT NULL,
            state VARCHAR(2) NOT NULL,
            county VARCHAR(100) NOT NULL,
            has_local_ordinance BOOLEAN DEFAULT false,
            aliases TEXT[],

            UNIQUE(city, state)
        )
    """)

    op.execute("CREATE INDEX idx_jref_state ON jurisdiction_reference(state)")
    op.execute("CREATE INDEX idx_jref_county ON jurisdiction_reference(county, state)")

    # Seed cities known to have local minimum wage ordinances
    op.execute("""
        INSERT INTO jurisdiction_reference (city, state, county, has_local_ordinance, aliases) VALUES
        -- California cities with local minimums
        ('san francisco', 'CA', 'San Francisco', true, ARRAY['SF']),
        ('los angeles', 'CA', 'Los Angeles', true, ARRAY['LA']),
        ('san jose', 'CA', 'Santa Clara', true, NULL),
        ('san diego', 'CA', 'San Diego', true, NULL),
        ('oakland', 'CA', 'Alameda', true, NULL),
        ('berkeley', 'CA', 'Alameda', true, NULL),
        ('emeryville', 'CA', 'Alameda', true, NULL),
        ('long beach', 'CA', 'Los Angeles', true, NULL),
        ('santa monica', 'CA', 'Los Angeles', true, NULL),
        ('west hollywood', 'CA', 'Los Angeles', true, ARRAY['WeHo']),
        ('malibu', 'CA', 'Los Angeles', true, NULL),
        ('pasadena', 'CA', 'Los Angeles', true, NULL),
        ('el cerrito', 'CA', 'Contra Costa', true, NULL),
        ('richmond', 'CA', 'Contra Costa', true, NULL),
        ('milpitas', 'CA', 'Santa Clara', true, NULL),
        ('mountain view', 'CA', 'Santa Clara', true, NULL),
        ('palo alto', 'CA', 'Santa Clara', true, NULL),
        ('sunnyvale', 'CA', 'Santa Clara', true, NULL),
        ('santa clara', 'CA', 'Santa Clara', true, NULL),
        ('cupertino', 'CA', 'Santa Clara', true, NULL),
        ('redwood city', 'CA', 'San Mateo', true, NULL),
        ('south san francisco', 'CA', 'San Mateo', true, NULL),
        ('san mateo', 'CA', 'San Mateo', true, NULL),
        ('belmont', 'CA', 'San Mateo', true, NULL),
        ('half moon bay', 'CA', 'San Mateo', true, NULL),
        ('menlo park', 'CA', 'San Mateo', true, NULL),
        ('daly city', 'CA', 'San Mateo', true, NULL),
        ('novato', 'CA', 'Marin', true, NULL),
        ('petaluma', 'CA', 'Sonoma', true, NULL),
        ('sonoma', 'CA', 'Sonoma', true, NULL),
        ('santa rosa', 'CA', 'Sonoma', true, NULL),
        ('fremont', 'CA', 'Alameda', true, NULL),
        ('hayward', 'CA', 'Alameda', true, NULL),
        ('alameda', 'CA', 'Alameda', true, NULL),
        ('san leandro', 'CA', 'Alameda', true, NULL),
        ('los altos', 'CA', 'Santa Clara', true, NULL),
        -- California cities without local ordinance (county mapping)
        ('del mar', 'CA', 'San Diego', false, NULL),
        ('fresno', 'CA', 'Fresno', false, NULL),
        ('sacramento', 'CA', 'Sacramento', false, NULL),
        ('anaheim', 'CA', 'Orange', false, NULL),
        ('irvine', 'CA', 'Orange', false, NULL),
        ('riverside', 'CA', 'Riverside', false, NULL),
        ('bakersfield', 'CA', 'Kern', false, NULL),
        ('stockton', 'CA', 'San Joaquin', false, NULL),
        ('modesto', 'CA', 'Stanislaus', false, NULL),
        ('glendale', 'CA', 'Los Angeles', false, NULL),
        ('huntington beach', 'CA', 'Orange', false, NULL),
        ('burbank', 'CA', 'Los Angeles', false, NULL),
        ('torrance', 'CA', 'Los Angeles', false, NULL),

        -- Washington state
        ('seattle', 'WA', 'King', true, NULL),
        ('seatac', 'WA', 'King', true, NULL),
        ('tukwila', 'WA', 'King', true, NULL),
        ('tacoma', 'WA', 'Pierce', false, NULL),
        ('spokane', 'WA', 'Spokane', false, NULL),
        ('bellevue', 'WA', 'King', false, NULL),

        -- New York
        ('new york', 'NY', 'New York', true, ARRAY['NYC', 'New York City', 'Manhattan']),
        ('buffalo', 'NY', 'Erie', false, NULL),
        ('rochester', 'NY', 'Monroe', false, NULL),
        ('albany', 'NY', 'Albany', false, NULL),
        ('yonkers', 'NY', 'Westchester', false, NULL),

        -- Colorado
        ('denver', 'CO', 'Denver', true, NULL),
        ('colorado springs', 'CO', 'El Paso', false, NULL),
        ('aurora', 'CO', 'Arapahoe', false, NULL),
        ('boulder', 'CO', 'Boulder', false, NULL),
        ('fort collins', 'CO', 'Larimer', false, NULL),

        -- Illinois
        ('chicago', 'IL', 'Cook', true, NULL),
        ('springfield', 'IL', 'Sangamon', false, NULL),
        ('naperville', 'IL', 'DuPage', false, NULL),

        -- Minnesota
        ('minneapolis', 'MN', 'Hennepin', true, NULL),
        ('st. paul', 'MN', 'Ramsey', true, ARRAY['Saint Paul']),
        ('rochester', 'MN', 'Olmsted', false, NULL),

        -- Maryland
        ('baltimore', 'MD', 'Baltimore City', false, NULL),
        ('bethesda', 'MD', 'Montgomery', true, NULL),
        ('silver spring', 'MD', 'Montgomery', true, NULL),
        ('columbia', 'MD', 'Howard', true, NULL),

        -- New Mexico
        ('santa fe', 'NM', 'Santa Fe', true, NULL),
        ('albuquerque', 'NM', 'Bernalillo', true, NULL),
        ('las cruces', 'NM', 'Dona Ana', true, NULL),

        -- Maine
        ('portland', 'ME', 'Cumberland', true, NULL),
        ('bangor', 'ME', 'Penobscot', false, NULL),

        -- Texas (preempted, but county mapping useful)
        ('austin', 'TX', 'Travis', false, NULL),
        ('houston', 'TX', 'Harris', false, NULL),
        ('dallas', 'TX', 'Dallas', false, NULL),
        ('san antonio', 'TX', 'Bexar', false, NULL),
        ('fort worth', 'TX', 'Tarrant', false, NULL),
        ('el paso', 'TX', 'El Paso', false, NULL),

        -- Florida (preempted, but county mapping useful)
        ('miami', 'FL', 'Miami-Dade', false, NULL),
        ('orlando', 'FL', 'Orange', false, NULL),
        ('tampa', 'FL', 'Hillsborough', false, NULL),
        ('jacksonville', 'FL', 'Duval', false, NULL),
        ('fort lauderdale', 'FL', 'Broward', false, NULL),

        -- Other major cities for county mapping
        ('phoenix', 'AZ', 'Maricopa', false, NULL),
        ('tucson', 'AZ', 'Pima', false, NULL),
        ('atlanta', 'GA', 'Fulton', false, NULL),
        ('birmingham', 'AL', 'Jefferson', false, NULL),
        ('charlotte', 'NC', 'Mecklenburg', false, NULL),
        ('raleigh', 'NC', 'Wake', false, NULL),
        ('nashville', 'TN', 'Davidson', false, NULL),
        ('memphis', 'TN', 'Shelby', false, NULL),
        ('charleston', 'SC', 'Charleston', false, NULL),
        ('jackson', 'MS', 'Hinds', false, NULL),
        ('indianapolis', 'IN', 'Marion', false, NULL),
        ('milwaukee', 'WI', 'Milwaukee', false, NULL),
        ('detroit', 'MI', 'Wayne', false, NULL),
        ('portland', 'OR', 'Multnomah', false, NULL),
        ('eugene', 'OR', 'Lane', false, NULL),
        ('boston', 'MA', 'Suffolk', false, NULL),
        ('hartford', 'CT', 'Hartford', false, NULL),
        ('newark', 'NJ', 'Essex', false, NULL),
        ('jersey city', 'NJ', 'Hudson', false, NULL),
        ('richmond', 'VA', 'Richmond City', false, NULL),
        ('virginia beach', 'VA', 'Virginia Beach City', false, NULL),
        ('philadelphia', 'PA', 'Philadelphia', false, NULL),
        ('pittsburgh', 'PA', 'Allegheny', false, NULL),
        ('columbus', 'OH', 'Franklin', false, NULL),
        ('cleveland', 'OH', 'Cuyahoga', false, NULL),
        ('cincinnati', 'OH', 'Hamilton', false, NULL),
        ('des moines', 'IA', 'Polk', false, NULL),
        ('louisville', 'KY', 'Jefferson', false, NULL),
        ('las vegas', 'NV', 'Clark', false, NULL),
        ('reno', 'NV', 'Washoe', false, NULL),
        ('salt lake city', 'UT', 'Salt Lake', false, NULL),
        ('omaha', 'NE', 'Douglas', false, NULL),
        ('kansas city', 'MO', 'Jackson', false, NULL),
        ('st. louis', 'MO', 'St. Louis City', false, ARRAY['Saint Louis']),
        ('honolulu', 'HI', 'Honolulu', false, NULL),
        ('anchorage', 'AK', 'Anchorage', false, NULL),
        ('boise', 'ID', 'Ada', false, NULL),
        ('little rock', 'AR', 'Pulaski', false, NULL),
        ('oklahoma city', 'OK', 'Oklahoma', false, NULL),
        ('tulsa', 'OK', 'Tulsa', false, NULL)
        ON CONFLICT (city, state) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_jref_county")
    op.execute("DROP INDEX IF EXISTS idx_jref_state")
    op.execute("DROP TABLE IF EXISTS jurisdiction_reference")
    op.execute("DROP TABLE IF EXISTS state_preemption_rules")
