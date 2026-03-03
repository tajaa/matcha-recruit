"""add_industry_compliance_profiles

Revision ID: e6714d5d523f
Revises: 0a9bffab08a8
Create Date: 2026-03-03 12:07:43.569668

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY


# revision identifiers, used by Alembic.
revision: str = 'e6714d5d523f'
down_revision: Union[str, Sequence[str], None] = '0a9bffab08a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'industry_compliance_profiles',
        sa.Column('id', UUID(), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('focused_categories', ARRAY(sa.Text()), nullable=False),
        sa.Column('rate_types', ARRAY(sa.Text()), nullable=True),
        sa.Column('category_order', ARRAY(sa.Text()), nullable=False),
        sa.Column('category_evidence', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()')),
    )

    op.get_bind().exec_driver_sql("""
        INSERT INTO industry_compliance_profiles (name, description, focused_categories, rate_types, category_order, category_evidence) VALUES
        (
            'Restaurant / Hospitality',
            'Restaurants, hotels, and hospitality businesses',
            ARRAY['minimum_wage','meal_breaks','scheduling_reporting','overtime','minor_work_permit'],
            ARRAY['tipped','hotel','fast_food','general'],
            ARRAY['minimum_wage','meal_breaks','scheduling_reporting','overtime','minor_work_permit','sick_leave','pay_frequency','final_pay'],
            '{"minimum_wage":{"reason":"Tipped wage tip-credit mechanism is the #1 litigation area in restaurants. CA AB 1228 created $20/hr fast food minimum. DOL WHD recovered $31M in back wages from food service in FY2024.","confidence":95,"sources":["DOL WHD FY2024 Enforcement Data","CA AB 1228","Seyfarth Shaw 2025 Workplace Class Action Report"],"last_reviewed":"2026-03-03"},"meal_breaks":{"reason":"Rush-period break denial is systemic. CA premium pay penalty drives massive class action exposure. Donohue v. AMN Healthcare established strict timing rules.","confidence":92,"sources":["Seyfarth Shaw 2025 Class Action Report","Donohue v. AMN Healthcare (2021)"],"last_reviewed":"2026-03-03"},"scheduling_reporting":{"reason":"Predictive scheduling laws in NYC, Chicago, LA, Philadelphia, Seattle, San Francisco directly target food service. Show-up/reporting pay in 8+ states.","confidence":90,"sources":["NYC Fair Workweek Law","Chicago Fair Workweek Ordinance","LA Fair Work Week Ordinance"],"last_reviewed":"2026-03-03"},"overtime":{"reason":"Side work and tip-credit overtime calculations create unique exposure. DOL consistently targets restaurants for off-the-clock prep work.","confidence":88,"sources":["DOL WHD FY2024 Enforcement Data","FLSA Tip Credit Rules 29 CFR 531"],"last_reviewed":"2026-03-03"},"minor_work_permit":{"reason":"High teen employment rate in food service. State-specific hour restrictions and hazardous duty rules (grills, slicers) vary significantly.","confidence":85,"sources":["DOL YouthRules","State Child Labor Law Surveys"],"last_reviewed":"2026-03-03"},"sick_leave":{"reason":"Mandatory paid sick leave now in 15+ states and many cities. Restaurant turnover makes tracking accrual complex.","confidence":82,"sources":["National Conference of State Legislatures Paid Sick Leave Overview"],"last_reviewed":"2026-03-03"},"pay_frequency":{"reason":"Standard biweekly/weekly requirements. Less litigation risk than wage/hour categories.","confidence":75,"sources":["State Payday Requirements - DOL"],"last_reviewed":"2026-03-03"},"final_pay":{"reason":"High turnover means frequent final pay events. State deadlines range from immediate to 30 days.","confidence":78,"sources":["State Final Pay Requirements Survey"],"last_reviewed":"2026-03-03"}}'
        ),
        (
            'Healthcare',
            'Hospitals, clinics, and healthcare providers',
            ARRAY['overtime','scheduling_reporting','meal_breaks','sick_leave','minimum_wage'],
            ARRAY['healthcare'],
            ARRAY['overtime','scheduling_reporting','meal_breaks','sick_leave','minimum_wage','pay_frequency','final_pay','minor_work_permit'],
            '{"overtime":{"reason":"12-hour shifts and mandatory overtime create major FLSA exposure. 8/80 overtime rules for hospitals. CA daily OT compounds with long shifts.","confidence":93,"sources":["FLSA Section 7(j) 8/80 Rule","CA Labor Code Section 510","DOL WHD Healthcare Enforcement"],"last_reviewed":"2026-03-03"},"scheduling_reporting":{"reason":"Mandatory overtime bans in 7+ states (OR, NJ, etc.) specifically target healthcare. Nurse staffing ratio laws in CA, MA, NY.","confidence":90,"sources":["Oregon HB 2800","NJ Mandatory Overtime for Healthcare Workers Act","CA Nurse Staffing Ratios"],"last_reviewed":"2026-03-03"},"meal_breaks":{"reason":"Patient care interruptions make compliant breaks extremely difficult. Premium pay penalties in CA for missed breaks during emergencies.","confidence":88,"sources":["Gerard v. Orange Coast Memorial Medical Center","CA Labor Code Section 512"],"last_reviewed":"2026-03-03"},"sick_leave":{"reason":"Healthcare workers face unique exposure risk. Some jurisdictions have enhanced sick leave for healthcare (COVID-era laws made permanent).","confidence":85,"sources":["FFCRA Legacy Provisions","State Healthcare Worker Leave Laws"],"last_reviewed":"2026-03-03"},"minimum_wage":{"reason":"CA SB 525 creates $25/hr healthcare worker minimum wage by 2026. Other states considering similar carve-outs.","confidence":88,"sources":["CA SB 525","Healthcare Worker Minimum Wage Tracker"],"last_reviewed":"2026-03-03"},"pay_frequency":{"reason":"Standard pay frequency requirements. Per diem and travel nurse arrangements add complexity.","confidence":72,"sources":["State Payday Requirements - DOL"],"last_reviewed":"2026-03-03"},"final_pay":{"reason":"Standard final pay rules apply. Credential/license return adds slight complexity.","confidence":70,"sources":["State Final Pay Requirements Survey"],"last_reviewed":"2026-03-03"},"minor_work_permit":{"reason":"Low teen employment in clinical settings. Relevant mainly for administrative/support roles.","confidence":65,"sources":["General State Child Labor Laws"],"last_reviewed":"2026-03-03"}}'
        ),
        (
            'Retail',
            'Retail stores and consumer-facing businesses',
            ARRAY['scheduling_reporting','minor_work_permit','meal_breaks','minimum_wage'],
            ARRAY['general'],
            ARRAY['scheduling_reporting','minor_work_permit','meal_breaks','minimum_wage','overtime','sick_leave','pay_frequency','final_pay'],
            '{"scheduling_reporting":{"reason":"Fair workweek laws in NYC, Chicago, LA, Philadelphia, Seattle explicitly target retail. On-call scheduling bans and advance notice requirements.","confidence":93,"sources":["NYC Fair Workweek Law","Seattle Secure Scheduling Ordinance","Philadelphia Fair Workweek Law"],"last_reviewed":"2026-03-03"},"minor_work_permit":{"reason":"Retail is the largest employer of minors. State-specific hour caps during school year and prohibited tasks vary widely.","confidence":90,"sources":["DOL YouthRules","BLS Teen Employment Statistics"],"last_reviewed":"2026-03-03"},"meal_breaks":{"reason":"Short-staffed shifts lead to missed breaks. Customer-facing roles make compliant breaks difficult during peak hours.","confidence":85,"sources":["State Meal Break Requirements Overview"],"last_reviewed":"2026-03-03"},"minimum_wage":{"reason":"Large hourly workforce affected by local minimum wage variation. Commission-based pay creates additional compliance requirements.","confidence":85,"sources":["DOL Minimum Wage by State","Local Minimum Wage Ordinance Tracker"],"last_reviewed":"2026-03-03"},"overtime":{"reason":"Standard FLSA rules apply. Manager misclassification is the main risk area.","confidence":80,"sources":["FLSA Duties Test for Retail Exemptions"],"last_reviewed":"2026-03-03"},"sick_leave":{"reason":"Part-time heavy workforce makes accrual tracking complex. 15+ state mandates plus city ordinances.","confidence":82,"sources":["National Conference of State Legislatures Paid Sick Leave"],"last_reviewed":"2026-03-03"},"pay_frequency":{"reason":"Standard biweekly/weekly requirements. Commission payment timing adds slight complexity.","confidence":75,"sources":["State Payday Requirements - DOL"],"last_reviewed":"2026-03-03"},"final_pay":{"reason":"High turnover means frequent final pay events but standard rules apply.","confidence":75,"sources":["State Final Pay Requirements Survey"],"last_reviewed":"2026-03-03"}}'
        ),
        (
            'Tech / Professional Services',
            'Technology companies and professional services firms',
            ARRAY['overtime','sick_leave','pay_frequency','final_pay','minimum_wage'],
            ARRAY['exempt_salary'],
            ARRAY['overtime','sick_leave','pay_frequency','final_pay','minimum_wage','meal_breaks','scheduling_reporting','minor_work_permit'],
            '{"overtime":{"reason":"Exempt misclassification is the top risk. Salary threshold increases (DOL 2024 rule set $58,656) and state-specific tests (CA duties test stricter than federal).","confidence":95,"sources":["DOL 2024 Overtime Final Rule","CA Labor Code Exemption Tests","Encino Motorcars v. Navarro (2018)"],"last_reviewed":"2026-03-03"},"sick_leave":{"reason":"Remote/hybrid workforce across multiple jurisdictions triggers overlapping sick leave mandates. PTO policies must meet minimums in each location.","confidence":88,"sources":["Multi-State Paid Leave Compliance Guide","Remote Worker Nexus Analysis"],"last_reviewed":"2026-03-03"},"pay_frequency":{"reason":"Biweekly standard but state variation matters for multi-state employers. Bonus/commission timing for sales roles.","confidence":78,"sources":["State Payday Requirements - DOL"],"last_reviewed":"2026-03-03"},"final_pay":{"reason":"CA immediate pay on termination is the main risk. Stock option and equity vesting adds complexity not seen in other industries.","confidence":82,"sources":["CA Labor Code Section 201-203","State Final Pay Penalty Surveys"],"last_reviewed":"2026-03-03"},"minimum_wage":{"reason":"Exempt salary thresholds effectively act as minimum wage for tech. CA $66,560/yr, NYC $62,400/yr exempt minimums. Non-exempt contractors in gig economy.","confidence":85,"sources":["DOL 2024 Salary Threshold Rule","CA Exempt Salary Threshold","NYC Exempt Salary Threshold"],"last_reviewed":"2026-03-03"},"meal_breaks":{"reason":"CA daily meal/rest break rules apply to non-exempt tech workers. Lower risk than shift-based industries but still relevant.","confidence":70,"sources":["CA Labor Code Section 512"],"last_reviewed":"2026-03-03"},"scheduling_reporting":{"reason":"Low relevance for salaried exempt workers. Only applies to non-exempt hourly roles in covered jurisdictions.","confidence":68,"sources":["Fair Workweek Law Coverage Analysis"],"last_reviewed":"2026-03-03"},"minor_work_permit":{"reason":"Minimal teen employment in tech. Only relevant for internship programs.","confidence":60,"sources":["General State Child Labor Laws"],"last_reviewed":"2026-03-03"}}'
        ),
        (
            'Fast Food',
            'Fast food chains and quick-service restaurants',
            ARRAY['minimum_wage','scheduling_reporting','meal_breaks','minor_work_permit'],
            ARRAY['fast_food'],
            ARRAY['minimum_wage','scheduling_reporting','meal_breaks','minor_work_permit','overtime','sick_leave','pay_frequency','final_pay'],
            '{"minimum_wage":{"reason":"CA AB 1228 created $20/hr fast food minimum — highest industry-specific rate in US. Fast Food Council can raise it annually. NYC fast food premium also applies.","confidence":96,"sources":["CA AB 1228 (FAST Recovery Act)","CA Fast Food Council","NYC Fast Food Worker Minimum Wage"],"last_reviewed":"2026-03-03"},"scheduling_reporting":{"reason":"NYC, Chicago, LA, Philadelphia fair workweek laws explicitly cover fast food. Clopening bans and 14-day advance scheduling. Penalties for last-minute changes.","confidence":93,"sources":["NYC Fair Workweek Law","Chicago Fair Workweek Ordinance","LA Fair Work Week Ordinance"],"last_reviewed":"2026-03-03"},"meal_breaks":{"reason":"High-volume rush periods make compliant breaks extremely difficult. Short shifts may not trigger break requirements but overlap with minor rules.","confidence":88,"sources":["State Meal Break Requirements Overview","Fast Food Industry Compliance Surveys"],"last_reviewed":"2026-03-03"},"minor_work_permit":{"reason":"Fast food is the single largest employer of minors in the US. Hazardous equipment (fryers, slicers) plus late-night hour restrictions create dense compliance requirements.","confidence":92,"sources":["DOL YouthRules","BLS Teen Employment by Industry","State Hazardous Occupation Orders"],"last_reviewed":"2026-03-03"},"overtime":{"reason":"Standard FLSA rules. Assistant manager misclassification is the main risk.","confidence":80,"sources":["DOL FLSA Coverage Analysis"],"last_reviewed":"2026-03-03"},"sick_leave":{"reason":"High turnover, part-time heavy workforce. Accrual tracking is operationally complex.","confidence":80,"sources":["National Conference of State Legislatures Paid Sick Leave"],"last_reviewed":"2026-03-03"},"pay_frequency":{"reason":"Standard weekly/biweekly requirements. Low litigation risk.","confidence":72,"sources":["State Payday Requirements - DOL"],"last_reviewed":"2026-03-03"},"final_pay":{"reason":"Extremely high turnover means constant final pay events. Standard state deadlines apply.","confidence":75,"sources":["State Final Pay Requirements Survey"],"last_reviewed":"2026-03-03"}}'
        ),
        (
            'Construction / Manufacturing',
            'Construction sites, factories, and manufacturing',
            ARRAY['overtime','meal_breaks','pay_frequency','minimum_wage'],
            ARRAY['general'],
            ARRAY['overtime','meal_breaks','pay_frequency','minimum_wage','minor_work_permit','scheduling_reporting','sick_leave','final_pay'],
            '{"overtime":{"reason":"Heavy overtime culture with 50-60hr weeks common. Prevailing wage on public projects adds Davis-Bacon OT calculations. DOL recovered $22M from construction in FY2024.","confidence":95,"sources":["DOL WHD FY2024 Enforcement Data","Davis-Bacon Act","State Prevailing Wage Laws"],"last_reviewed":"2026-03-03"},"meal_breaks":{"reason":"Physically demanding work makes break compliance critical. Remote job sites complicate break timing and documentation.","confidence":85,"sources":["OSHA Rest Requirements","State Meal Break Laws"],"last_reviewed":"2026-03-03"},"pay_frequency":{"reason":"Many states require weekly pay for construction specifically. Prevailing wage certified payroll requirements add compliance layer.","confidence":90,"sources":["State Construction Pay Frequency Requirements","Davis-Bacon Certified Payroll Rules"],"last_reviewed":"2026-03-03"},"minimum_wage":{"reason":"Prevailing wage on public projects often well above minimum wage. Private projects in high-cost cities affected by local minimums.","confidence":82,"sources":["Davis-Bacon Wage Determinations","Local Minimum Wage Ordinances"],"last_reviewed":"2026-03-03"},"minor_work_permit":{"reason":"Extensive hazardous occupation restrictions (HO 12, 14, 17) for construction. Limited to 16+ for most tasks. Important but narrow applicability.","confidence":78,"sources":["DOL Hazardous Occupation Orders","State Construction Minor Restrictions"],"last_reviewed":"2026-03-03"},"scheduling_reporting":{"reason":"Shift-based manufacturing may trigger reporting pay in some states. Construction largely exempt from predictive scheduling laws.","confidence":70,"sources":["State Reporting Pay Requirements"],"last_reviewed":"2026-03-03"},"sick_leave":{"reason":"Standard state mandates apply. Seasonal/project-based work complicates accrual tracking.","confidence":75,"sources":["National Conference of State Legislatures Paid Sick Leave"],"last_reviewed":"2026-03-03"},"final_pay":{"reason":"Project-based employment means frequent separations. Standard state deadlines apply.","confidence":75,"sources":["State Final Pay Requirements Survey"],"last_reviewed":"2026-03-03"}}'
        )
    """)


def downgrade() -> None:
    op.drop_table('industry_compliance_profiles')
