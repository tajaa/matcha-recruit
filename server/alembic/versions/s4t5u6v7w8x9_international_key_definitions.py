"""Add international key definitions, jurisdiction hierarchy, and precedence rules.

Phase 1 of the international compliance architecture:
- Add applicable_countries column to regulation_key_definitions
- Seed ~50 international key definitions (universal + MX + GB + SG)
- Create national jurisdiction rows (UK, Mexico, Singapore)
- Link existing city jurisdictions to national parents
- Create precedence rules for UK and Mexico
- Widen current_value column to VARCHAR(500)
- Fix miscategorized London requirements
- Backfill key_definition_id (direct match)

Revision ID: s4t5u6v7w8x9
Revises: r3s4t5u6v7w8
Create Date: 2026-03-25
"""

from alembic import op

revision = "s4t5u6v7w8x9"
down_revision = "r3s4t5u6v7w8"
branch_labels = None
depends_on = None


def upgrade():
    # ── 1a. Add applicable_countries column ───────────────────────────────
    op.execute("""
        ALTER TABLE regulation_key_definitions
        ADD COLUMN IF NOT EXISTS applicable_countries TEXT[]
    """)

    # ── 1b. Update applies_to_levels to include 'national' ───────────────
    op.execute("""
        UPDATE regulation_key_definitions
        SET applies_to_levels = array_cat(applies_to_levels, '{national}')
        WHERE NOT ('national' = ANY(COALESCE(applies_to_levels, '{}')))
    """)

    # ── 1c. Seed international key definitions ───────────────────────────

    # Universal keys (applicable_countries = NULL — all countries)
    _UNIVERSAL_KEYS = [
        ("minimum_wage", "national_minimum_wage", "National Minimum Wage", "High", "wage_rates", None, 30, 60, 365),
        ("sick_leave", "statutory_sick_leave", "Statutory Sick Leave", "High", None, None, 90, 180, 365),
        ("leave", "annual_leave_entitlement", "Annual Leave Entitlement", "High", "leave_programs", None, 90, 180, 365),
        ("leave", "statutory_maternity_leave", "Statutory Maternity Leave", "High", "leave_programs", None, 90, 180, 365),
        ("leave", "statutory_paternity_leave", "Statutory Paternity Leave", "Moderate", "leave_programs", None, 180, 365, 730),
        ("leave", "severance_pay", "Statutory Severance Pay", "High", "leave_programs", None, 90, 180, 365),
        ("leave", "statutory_notice_period_employer", "Statutory Notice Period (Employer)", "High", "leave_programs", None, 90, 180, 365),
        ("workers_comp", "social_insurance_employer", "Employer Social Insurance Contributions", "High", "workers_comp", None, 30, 90, 365),
        ("scheduling_reporting", "maximum_working_hours", "Maximum Working Hours", "Moderate", "scheduling_rules", None, 180, 365, 730),
    ]

    for cat, key, name, variance, group, agency, warn, crit, expired in _UNIVERSAL_KEYS:
        weight = 1.5 if variance == "High" else 1.0
        _insert_intl_key(cat, key, name, agency, variance, weight, group, warn, crit, expired, None)

    # Mexico-specific keys
    _MX_KEYS = [
        ("minimum_wage", "zlfn_border_zone_minimum_wage", "ZLFN Border Zone Minimum Wage", "CONASAMI", "High", "wage_rates", 30, 60, 365),
        ("sick_leave", "imss_sick_leave", "IMSS Sick Leave Benefits", "IMSS", "Moderate", None, 90, 180, 365),
        ("leave", "vacation_premium", "Vacation Premium (Prima Vacacional)", "STPS", "Moderate", "leave_programs", 90, 180, 365),
        ("leave", "aguinaldo_christmas_bonus", "Aguinaldo (Christmas Bonus)", "STPS", "High", "leave_programs", 30, 60, 365),
        ("leave", "ptu_profit_sharing", "PTU Profit Sharing", "STPS / SAT", "High", "leave_programs", 30, 90, 365),
        ("leave", "seniority_premium", "Seniority Premium (Prima de Antiguedad)", "STPS", "Moderate", "leave_programs", 180, 365, 730),
        ("final_pay", "finiquito", "Finiquito (Settlement Receipt)", "Tribunal Laboral", "High", "pay_rules", 90, 180, 365),
        ("final_pay", "liquidacion", "Liquidacion (Full Severance)", "Tribunal Laboral", "High", "pay_rules", 90, 180, 365),
        ("scheduling_reporting", "sunday_premium", "Sunday Premium (Prima Dominical)", "STPS", "Moderate", "scheduling_rules", 180, 365, 730),
        ("workers_comp", "imss_employer_contribution", "IMSS Occupational Risk Premium", "IMSS", "High", "workers_comp", 30, 90, 365),
        ("workers_comp", "infonavit_contribution", "INFONAVIT Housing Contribution", "INFONAVIT", "Moderate", "workers_comp", 90, 180, 365),
        ("workers_comp", "sar_retirement_contribution", "SAR Retirement Contribution", "IMSS / AFORE", "Moderate", "workers_comp", 90, 180, 365),
        ("workplace_safety", "stps_nom_standards", "STPS NOM Standards (41 NOMs)", "STPS", "Moderate", "workplace_safety", 180, 365, 730),
        ("anti_discrimination", "nom_035_psychosocial_risk", "NOM-035 Psychosocial Risk Prevention", "STPS", "High", "discrimination_protections", 90, 180, 365),
        ("hipaa_privacy", "national_health_privacy_law", "National Health Privacy Law (LFPDPPP)", "INAI/SABG", "High", None, 90, 180, 365),
        ("hipaa_privacy", "lfpdppp_health_data", "LFPDPPP Sensitive Health Data", "INAI/SABG", "Moderate", None, 180, 365, 730),
        ("clinical_safety", "cofepris_facility_standards", "COFEPRIS Facility Standards", "COFEPRIS", "High", None, 180, 365, 730),
        ("state_licensing", "cofepris_sanitary_license", "COFEPRIS Sanitary License", "COFEPRIS", "High", None, 180, 365, 730),
        ("research_consent", "national_research_consent_law", "National Research Consent Law", "COFEPRIS", "Moderate", None, 365, 730, 1460),
        ("research_consent", "cofepris_research_authorization", "COFEPRIS Research Authorization", "COFEPRIS", "Moderate", None, 365, 730, 1460),
        ("radiation_safety", "national_radiation_control", "National Radiation Control (CNSNS)", "CNSNS", "High", "radiation_safety", 365, 730, 1460),
        ("chemotherapy_handling", "national_hazardous_drug_handling", "National Hazardous Drug Handling", "COFEPRIS/SEMARNAT", "Moderate", "chemotherapy_safety", 365, 730, 1460),
        ("tumor_registry", "national_cancer_registry", "Registro Nacional de Cancer", "Secretaria de Salud", "High", "cancer_registry", 180, 365, 730),
        ("billing_integrity", "national_anti_corruption_healthcare", "National Anti-Corruption (Healthcare)", "SFP", "Moderate", None, 365, 730, 1460),
        ("corporate_integrity", "national_whistleblower_protection", "National Whistleblower Protection", "SFP", "Moderate", None, 365, 730, 1460),
        ("emergency_preparedness", "national_emergency_preparedness", "National Emergency Preparedness", "SINAPROC", "Moderate", None, 365, 730, 1460),
        ("oncology_patient_rights", "palliative_care_access", "Palliative Care Access", "Secretaria de Salud", "Moderate", "patient_rights", 365, 730, 1460),
        ("healthcare_workforce", "professional_licensing", "Professional Licensing (Cedula Profesional)", "SEP", "Moderate", None, 180, 365, 730),
        ("oncology_clinical_trials", "clinical_trial_coverage_mandates", "Clinical Trial Coverage Mandates", "COFEPRIS", "Moderate", "clinical_trials", 180, 365, 730),
    ]

    for cat, key, name, agency, variance, group, warn, crit, expired in _MX_KEYS:
        weight = 1.5 if variance == "High" else 1.0
        _insert_intl_key(cat, key, name, agency, variance, weight, group, warn, crit, expired, "MX")

    # UK-specific keys
    _GB_KEYS = [
        ("leave", "shared_parental_leave", "Shared Parental Leave", None, "Moderate", "leave_programs", 180, 365, 730),
        ("leave", "adoption_leave", "Statutory Adoption Leave", None, "Moderate", "leave_programs", 180, 365, 730),
        ("workers_comp", "uk_auto_enrolment_pension", "Auto-Enrolment Workplace Pension", "The Pensions Regulator", "High", "workers_comp", 90, 180, 365),
        ("workers_comp", "social_insurance_employee", "Employee Social Insurance (National Insurance)", "HMRC", "High", "workers_comp", 30, 90, 365),
    ]

    for cat, key, name, agency, variance, group, warn, crit, expired in _GB_KEYS:
        weight = 1.5 if variance == "High" else 1.0
        _insert_intl_key(cat, key, name, agency, variance, weight, group, warn, crit, expired, "GB")

    # Singapore-specific keys
    _SG_KEYS = [
        ("workers_comp", "cpf_employer_contribution", "CPF Employer Contribution", "CPF Board", "High", "workers_comp", 30, 90, 365),
        ("workers_comp", "foreign_worker_levy", "Foreign Worker Levy", "Ministry of Manpower", "High", "workers_comp", 30, 90, 365),
    ]

    for cat, key, name, agency, variance, group, warn, crit, expired in _SG_KEYS:
        weight = 1.5 if variance == "High" else 1.0
        _insert_intl_key(cat, key, name, agency, variance, weight, group, warn, crit, expired, "SG")

    # ── 1d. Create national jurisdiction rows ─────────────────────────────
    _NATIONAL_JURISDICTIONS = [
        ("GB", "United Kingdom"),
        ("MX", "Mexico"),
        ("SG", "Singapore"),
    ]

    for country, display in _NATIONAL_JURISDICTIONS:
        op.execute(f"""
            INSERT INTO jurisdictions (city, state, country_code, level, display_name, authority_type)
            SELECT NULL, NULL, '{country}', 'national', '{display}', 'geographic'
            WHERE NOT EXISTS (
                SELECT 1 FROM jurisdictions WHERE country_code = '{country}' AND level = 'national'
            )
        """)

    # ── 1e. Link existing city jurisdictions to national parents ──────────
    _CITY_LINKS = [
        ("London", "GB"),
        ("Mexico City", "MX"),
        ("Singapore", "SG"),
    ]

    for city, country in _CITY_LINKS:
        op.execute(f"""
            UPDATE jurisdictions
            SET parent_id = (
                SELECT id FROM jurisdictions
                WHERE country_code = '{country}' AND level = 'national'
                LIMIT 1
            )
            WHERE LOWER(city) = LOWER('{city}')
              AND country_code = '{country}'
              AND parent_id IS NULL
        """)

    # ── 1f. Create precedence rules ──────────────────────────────────────

    # UK: supersede on ALL categories (employment law reserved to Westminster)
    op.execute("""
        INSERT INTO precedence_rules (
            category_id, higher_jurisdiction_id, lower_jurisdiction_id,
            applies_to_all_children, precedence_type, reasoning_text,
            legal_citation, status
        )
        SELECT cc.id, j.id, NULL, true, 'supersede',
            'UK employment law is reserved to Westminster Parliament. Cities and councils have no power to enact employment ordinances.',
            'Employment Rights Act 1996; Trade Union and Labour Relations (Consolidation) Act 1992',
            'active'
        FROM compliance_categories cc
        CROSS JOIN jurisdictions j
        WHERE j.country_code = 'GB' AND j.level = 'national'
          AND NOT EXISTS (
              SELECT 1 FROM precedence_rules pr
              WHERE pr.category_id = cc.id AND pr.higher_jurisdiction_id = j.id
          )
    """)

    # Mexico: supersede on all categories EXCEPT anti_discrimination (additive)
    op.execute("""
        INSERT INTO precedence_rules (
            category_id, higher_jurisdiction_id, lower_jurisdiction_id,
            applies_to_all_children, precedence_type, reasoning_text,
            legal_citation, status
        )
        SELECT cc.id, j.id, NULL, true, 'supersede',
            'Mexican labor law (LFT) is exclusively federal. States and cities cannot enact independent labor laws. Article 123 of the Constitution reserves labor regulation to the federal government.',
            'Constitucion Politica, Articulo 123; Ley Federal del Trabajo',
            'active'
        FROM compliance_categories cc
        CROSS JOIN jurisdictions j
        WHERE j.country_code = 'MX' AND j.level = 'national'
          AND cc.slug != 'anti_discrimination'
          AND NOT EXISTS (
              SELECT 1 FROM precedence_rules pr
              WHERE pr.category_id = cc.id AND pr.higher_jurisdiction_id = j.id
          )
    """)

    # Mexico anti_discrimination: additive (states can supplement LFT)
    op.execute("""
        INSERT INTO precedence_rules (
            category_id, higher_jurisdiction_id, lower_jurisdiction_id,
            applies_to_all_children, precedence_type, reasoning_text,
            legal_citation, status
        )
        SELECT cc.id, j.id, NULL, true, 'additive',
            'LFT sets federal baseline for anti-discrimination. States (CDMX, Jalisco) may enact supplementary protections (e.g., CDMX Law for Prevention and Elimination of Discrimination).',
            'Constitucion Politica, Articulo 123; Ley Federal del Trabajo; LFPED',
            'active'
        FROM compliance_categories cc
        CROSS JOIN jurisdictions j
        WHERE j.country_code = 'MX' AND j.level = 'national'
          AND cc.slug = 'anti_discrimination'
          AND NOT EXISTS (
              SELECT 1 FROM precedence_rules pr
              WHERE pr.category_id = cc.id AND pr.higher_jurisdiction_id = j.id
          )
    """)

    # ── 1g. Widen current_value column ───────────────────────────────────
    op.execute("""
        ALTER TABLE jurisdiction_requirements
        ALTER COLUMN current_value TYPE VARCHAR(500)
    """)

    # ── 1h. Fix miscategorized London requirements ───────────────────────

    # overtime key stuck under minimum_wage
    op.execute("""
        UPDATE jurisdiction_requirements
        SET category = 'overtime',
            category_id = (SELECT id FROM compliance_categories WHERE slug = 'overtime')
        WHERE jurisdiction_id = (SELECT id FROM jurisdictions WHERE city = 'London' AND country_code = 'GB' LIMIT 1)
          AND regulation_key = 'daily_weekly_overtime'
          AND category = 'minimum_wage'
    """)

    # leave keys stuck under sick_leave
    op.execute("""
        UPDATE jurisdiction_requirements
        SET category = 'leave',
            category_id = (SELECT id FROM compliance_categories WHERE slug = 'leave')
        WHERE jurisdiction_id = (SELECT id FROM jurisdictions WHERE city = 'London' AND country_code = 'GB' LIMIT 1)
          AND category = 'sick_leave'
          AND regulation_key IN (
              'annual_leave_entitlement', 'statutory_maternity_leave', 'statutory_paternity_leave',
              'shared_parental_leave', 'adoption_leave', 'bereavement_leave', 'severance_pay',
              'statutory_notice_period_employer', 'emergency_dependant_leave', 'state_family_leave',
              'jury_duty_leave'
          )
    """)

    # uk_unfair_dismissal stuck under minor_work_permit
    op.execute("""
        UPDATE jurisdiction_requirements
        SET category = 'anti_discrimination',
            category_id = (SELECT id FROM compliance_categories WHERE slug = 'anti_discrimination')
        WHERE jurisdiction_id = (SELECT id FROM jurisdictions WHERE city = 'London' AND country_code = 'GB' LIMIT 1)
          AND regulation_key = 'uk_unfair_dismissal'
          AND category = 'minor_work_permit'
    """)

    # ── 1i. Backfill key_definition_id (direct match) ────────────────────
    op.execute("""
        UPDATE jurisdiction_requirements jr
        SET key_definition_id = rkd.id
        FROM regulation_key_definitions rkd
        WHERE jr.category = rkd.category_slug
          AND jr.regulation_key = rkd.key
          AND jr.key_definition_id IS NULL
    """)


def _insert_intl_key(
    category_slug, key, name, enforcing_agency, state_variance,
    base_weight, key_group, staleness_warning, staleness_critical,
    staleness_expired, country_code,
):
    """Insert an international key definition, skipping if exists."""
    name_esc = name.replace("'", "''") if name else ""
    agency_esc = enforcing_agency.replace("'", "''") if enforcing_agency else None
    if country_code:
        countries_literal = "'{" + country_code + "}'"
    else:
        countries_literal = "NULL"

    op.execute(f"""
        INSERT INTO regulation_key_definitions
            (key, category_slug, category_id, name, enforcing_agency,
             state_variance, base_weight, key_group,
             staleness_warning_days, staleness_critical_days, staleness_expired_days,
             applies_to_levels, applicable_countries)
        SELECT
            '{key}',
            '{category_slug}',
            cc.id,
            '{name_esc}',
            {f"'{agency_esc}'" if agency_esc else 'NULL'},
            '{state_variance}',
            {base_weight},
            {f"'{key_group}'" if key_group else 'NULL'},
            {staleness_warning},
            {staleness_critical},
            {staleness_expired},
            '{{national,state,city}}',
            {countries_literal}
        FROM compliance_categories cc
        WHERE cc.slug = '{category_slug}'
        ON CONFLICT (category_slug, key) DO NOTHING
    """)


def downgrade():
    # Remove applicable_countries column
    op.execute("""
        ALTER TABLE regulation_key_definitions
        DROP COLUMN IF EXISTS applicable_countries
    """)

    # Revert current_value width (lossy — values > 100 chars will be truncated)
    # Not reverting to avoid data loss

    # Remove international precedence rules
    op.execute("""
        DELETE FROM precedence_rules
        WHERE higher_jurisdiction_id IN (
            SELECT id FROM jurisdictions WHERE country_code IN ('GB', 'MX') AND level = 'national'
        )
    """)

    # Unlink city jurisdictions from national parents
    op.execute("""
        UPDATE jurisdictions SET parent_id = NULL
        WHERE country_code IN ('GB', 'MX', 'SG') AND level = 'city'
    """)

    # Remove national jurisdiction rows
    op.execute("""
        DELETE FROM jurisdictions
        WHERE country_code IN ('GB', 'MX', 'SG') AND level = 'national'
    """)

    # Note: key definitions are not removed (ON CONFLICT DO NOTHING on upgrade,
    # so they're idempotent). London fixes are not reverted.
