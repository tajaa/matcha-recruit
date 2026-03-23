"""Add regulation_key_definitions table, history table, repository_alerts,
split requirement_key column, and seed ~355 key definitions.

Implements Phases 1-2 of the First-Class Regulation Key System plan.

Revision ID: p1q2r3s4t5u6
Revises: zm0n1o2p3q4r
Create Date: 2026-03-23
"""

from alembic import op

revision = "p1q2r3s4t5u6"
down_revision = "zm0n1o2p3q4r"
branch_labels = None
depends_on = None


def upgrade():
    # ── Phase 1: regulation_key_definitions table ────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS regulation_key_definitions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

            -- IDENTITY
            key VARCHAR(100) NOT NULL,
            category_slug VARCHAR(50) NOT NULL,
            category_id UUID NOT NULL REFERENCES compliance_categories(id),
            UNIQUE(category_slug, key),

            -- DISPLAY
            name VARCHAR(200) NOT NULL,
            description TEXT,

            -- ENFORCEMENT
            enforcing_agency VARCHAR(200),
            authority_source_urls TEXT[],

            -- VARIANCE & WEIGHT
            state_variance VARCHAR(20) NOT NULL DEFAULT 'Moderate',
            base_weight NUMERIC(3,1) NOT NULL DEFAULT 1.0,

            -- APPLICABILITY SCOPE
            applies_to_levels TEXT[] DEFAULT '{state,city}',
            min_employee_threshold INTEGER,
            applicable_entity_types TEXT[],
            applicable_industries TEXT[],

            -- STALENESS SLA
            update_frequency VARCHAR(100),
            staleness_warning_days INTEGER DEFAULT 90,
            staleness_critical_days INTEGER DEFAULT 180,
            staleness_expired_days INTEGER DEFAULT 365,

            -- DEPENDENCIES
            key_group VARCHAR(100),

            -- AUDIT
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            created_by UUID REFERENCES users(id),
            notes TEXT
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_rkd_category
        ON regulation_key_definitions(category_slug)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_rkd_key_group
        ON regulation_key_definitions(key_group)
    """)

    # ── Phase 1: regulation_key_definition_history table ─────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS regulation_key_definition_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            key_definition_id UUID NOT NULL REFERENCES regulation_key_definitions(id) ON DELETE CASCADE,
            field_changed VARCHAR(100) NOT NULL,
            old_value TEXT,
            new_value TEXT,
            changed_at TIMESTAMP DEFAULT NOW(),
            changed_by UUID REFERENCES users(id),
            change_reason TEXT
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_rkdh_key_def
        ON regulation_key_definition_history(key_definition_id, changed_at)
    """)

    # ── Phase 1: repository_alerts table ─────────────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS repository_alerts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            alert_type VARCHAR(30) NOT NULL,
            severity VARCHAR(20) NOT NULL,
            jurisdiction_id UUID REFERENCES jurisdictions(id) ON DELETE CASCADE,
            key_definition_id UUID REFERENCES regulation_key_definitions(id) ON DELETE CASCADE,
            requirement_id UUID REFERENCES jurisdiction_requirements(id) ON DELETE SET NULL,
            category VARCHAR(50),
            regulation_key VARCHAR(100),
            message TEXT NOT NULL,
            days_overdue INTEGER,
            status VARCHAR(20) NOT NULL DEFAULT 'open',
            created_at TIMESTAMP DEFAULT NOW(),
            acknowledged_at TIMESTAMP,
            acknowledged_by UUID REFERENCES users(id),
            resolved_at TIMESTAMP,
            resolved_by UUID REFERENCES users(id),
            resolution_note TEXT
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_repo_alerts_status
        ON repository_alerts(status)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_repo_alerts_jurisdiction
        ON repository_alerts(jurisdiction_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_repo_alerts_severity
        ON repository_alerts(severity)
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_repo_alerts_dedup
        ON repository_alerts(jurisdiction_id, key_definition_id, alert_type)
        WHERE status = 'open'
    """)

    # ── Phase 1: Seed key definitions from Python registry ───────────────

    _seed_key_definitions()

    # ── Phase 2: Split requirement_key into separate column ──────────────

    op.execute("""
        ALTER TABLE jurisdiction_requirements
        ADD COLUMN IF NOT EXISTS regulation_key TEXT
    """)
    op.execute("""
        ALTER TABLE jurisdiction_requirements
        ADD COLUMN IF NOT EXISTS key_definition_id UUID REFERENCES regulation_key_definitions(id)
    """)

    # Backfill regulation_key from composite requirement_key
    op.execute("""
        UPDATE jurisdiction_requirements
        SET regulation_key = CASE
            WHEN position(':' in requirement_key) > 0
            THEN substring(requirement_key from position(':' in requirement_key) + 1)
            ELSE requirement_key
        END
        WHERE regulation_key IS NULL
    """)

    # Verify backfill completeness
    op.execute("""
        DO $$
        DECLARE
            total_rows INTEGER;
            filled_rows INTEGER;
        BEGIN
            SELECT count(*) INTO total_rows FROM jurisdiction_requirements;
            SELECT count(*) INTO filled_rows FROM jurisdiction_requirements WHERE regulation_key IS NOT NULL;
            IF total_rows > 0 AND total_rows != filled_rows THEN
                RAISE EXCEPTION 'Backfill mismatch: % rows total but only % got regulation_key',
                    total_rows, filled_rows;
            END IF;
        END $$
    """)

    # Backfill key_definition_id by linking to regulation_key_definitions
    op.execute("""
        UPDATE jurisdiction_requirements jr
        SET key_definition_id = rkd.id
        FROM regulation_key_definitions rkd
        WHERE jr.category = rkd.category_slug
          AND jr.regulation_key = rkd.key
          AND jr.key_definition_id IS NULL
    """)

    # Indexes
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_jr_regulation_key
        ON jurisdiction_requirements(regulation_key)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_jr_category_regulation_key
        ON jurisdiction_requirements(category, regulation_key)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_jr_key_definition_id
        ON jurisdiction_requirements(key_definition_id)
    """)


def _seed_key_definitions():
    """Seed regulation_key_definitions from the Python registry.

    Imports at call time to avoid import-time DB dependencies.
    """
    from app.core.compliance_registry import (
        REGULATIONS,
        _LABOR_REGULATION_KEYS,
        CATEGORY_MAP,
    )

    # ── 1. Healthcare/Medical RegulationDef entries (229) ────────────────
    for reg in REGULATIONS:
        cat_def = CATEGORY_MAP.get(reg.category)
        if not cat_def:
            continue

        sources = []
        for src in (reg.authority_sources or ()):
            if isinstance(src, dict) and src.get("domain"):
                sources.append(src["domain"])

        weight = 1.5 if reg.state_variance == "High" else 1.0

        _insert_key_def(
            key=reg.key,
            category_slug=reg.category,
            name=reg.name,
            description=reg.description,
            enforcing_agency=reg.enforcing_agency,
            authority_source_urls=sources,
            state_variance=reg.state_variance,
            base_weight=weight,
            update_frequency=reg.update_frequency,
            key_group=None,
            staleness_warning=90,
            staleness_critical=180,
            staleness_expired=365,
        )

    # ── 2. Labor keys (99) ───────────────────────────────────────────────

    _LABOR_KEY_METADATA = {
        # minimum_wage (10)
        "state_minimum_wage": ("State Minimum Wage", "High", "wage_rates", "WHD (Wage and Hour Division)", 30, 60, 365),
        "tipped_minimum_wage": ("Tipped Minimum Wage", "High", "wage_rates", "WHD (Wage and Hour Division)", 30, 60, 365),
        "exempt_salary_threshold": ("Exempt Salary Threshold", "Moderate", "wage_rates", "WHD (Wage and Hour Division)", 90, 180, 365),
        "fast_food_minimum_wage": ("Fast Food Minimum Wage", "High", "wage_rates", "WHD (Wage and Hour Division)", 30, 60, 365),
        "healthcare_minimum_wage": ("Healthcare Minimum Wage", "High", "wage_rates", "WHD (Wage and Hour Division)", 30, 60, 365),
        "large_employer_minimum_wage": ("Large Employer Minimum Wage", "High", "wage_rates", "WHD (Wage and Hour Division)", 30, 60, 365),
        "small_employer_minimum_wage": ("Small Employer Minimum Wage", "High", "wage_rates", "WHD (Wage and Hour Division)", 30, 60, 365),
        "youth_minimum_wage": ("Youth Minimum Wage", "Moderate", "wage_rates", "WHD (Wage and Hour Division)", 90, 180, 365),
        "tip_credit_prohibition": ("Tip Credit Prohibition", "High", None, "WHD (Wage and Hour Division)", 90, 180, 365),
        "local_minimum_wage": ("Local Minimum Wage", "High", "wage_rates", "Local government", 30, 60, 365),
        # overtime (8)
        "daily_weekly_overtime": ("Daily/Weekly Overtime", "High", "overtime_rules", "WHD (Wage and Hour Division)", 90, 180, 365),
        "double_time": ("Double Time", "High", "overtime_rules", "WHD (Wage and Hour Division)", 90, 180, 365),
        "seventh_day_overtime": ("Seventh Day Overtime", "High", "overtime_rules", "WHD (Wage and Hour Division)", 90, 180, 365),
        "alternative_workweek": ("Alternative Workweek", "Moderate", "overtime_rules", "WHD (Wage and Hour Division)", 180, 365, 730),
        "healthcare_overtime": ("Healthcare Overtime", "Moderate", "overtime_rules", "WHD (Wage and Hour Division)", 90, 180, 365),
        "mandatory_overtime_restrictions": ("Mandatory Overtime Restrictions", "High", "overtime_rules", "WHD (Wage and Hour Division)", 90, 180, 365),
        "comp_time": ("Compensatory Time", "Moderate", None, "WHD (Wage and Hour Division)", 180, 365, 730),
        # leave (15)
        "fmla": ("FMLA", "Low/None", "leave_programs", "WHD (Wage and Hour Division)", 180, 365, 730),
        "state_family_leave": ("State Family Leave", "High", "leave_programs", "State labor agency", 90, 180, 365),
        "state_paid_family_leave": ("State Paid Family Leave", "High", "leave_programs", "State labor agency", 90, 180, 365),
        "state_disability_insurance": ("State Disability Insurance", "High", "leave_programs", "State labor agency", 90, 180, 365),
        "pregnancy_disability_leave": ("Pregnancy Disability Leave", "High", "leave_programs", "State labor agency", 90, 180, 365),
        "paid_sick_leave": ("Paid Sick Leave", "High", None, "State/local labor agency", 90, 180, 365),
        "bereavement_leave": ("Bereavement Leave", "Moderate", None, "State labor agency", 180, 365, 730),
        "organ_donor_leave": ("Organ Donor Leave", "Moderate", None, "State labor agency", 180, 365, 730),
        "domestic_violence_leave": ("Domestic Violence Leave", "Moderate", None, "State labor agency", 180, 365, 730),
        "jury_duty_leave": ("Jury Duty Leave", "Low/None", None, "State labor agency", 365, 730, 1095),
        "military_leave": ("Military Leave", "Low/None", None, "State labor agency", 365, 730, 1095),
        "voting_leave": ("Voting Leave", "Moderate", None, "State labor agency", 365, 730, 1095),
        "school_activity_leave": ("School Activity Leave", "Moderate", None, "State labor agency", 180, 365, 730),
        "reproductive_loss_leave": ("Reproductive Loss Leave", "Moderate", None, "State labor agency", 180, 365, 730),
        "bone_marrow_donor_leave": ("Bone Marrow Donor Leave", "Moderate", None, "State labor agency", 365, 730, 1095),
        # sick_leave (3)
        "state_paid_sick_leave": ("State Paid Sick Leave", "High", None, "State labor agency", 90, 180, 365),
        "accrual_and_usage_caps": ("Accrual and Usage Caps", "High", None, "State labor agency", 90, 180, 365),
        "local_sick_leave": ("Local Sick Leave", "High", None, "Local government", 90, 180, 365),
        # meal_breaks (6)
        "meal_break": ("Meal Break", "High", "break_requirements", "WHD / State labor agency", 180, 365, 730),
        "rest_break": ("Rest Break", "High", "break_requirements", "WHD / State labor agency", 180, 365, 730),
        "lactation_break": ("Lactation Break", "Moderate", "break_requirements", "WHD / State labor agency", 180, 365, 730),
        "on_duty_meal_agreement": ("On-Duty Meal Agreement", "Moderate", "break_requirements", "WHD / State labor agency", 365, 730, 1095),
        "healthcare_meal_waiver": ("Healthcare Meal Waiver", "Moderate", "break_requirements", "WHD / State labor agency", 365, 730, 1095),
        "missed_break_penalty": ("Missed Break Penalty", "High", "break_requirements", "WHD / State labor agency", 180, 365, 730),
        # pay_frequency (6)
        "standard_pay_frequency": ("Standard Pay Frequency", "Moderate", "pay_rules", "State labor agency", 180, 365, 730),
        "final_pay_termination": ("Final Pay — Termination", "High", "pay_rules", "State labor agency", 90, 180, 365),
        "final_pay_resignation": ("Final Pay — Resignation", "High", "pay_rules", "State labor agency", 90, 180, 365),
        "exempt_monthly_pay": ("Exempt Monthly Pay", "Moderate", "pay_rules", "State labor agency", 365, 730, 1095),
        "payday_posting": ("Payday Posting Requirements", "Low/None", "pay_rules", "State labor agency", 365, 730, 1095),
        "wage_notice": ("Wage Notice", "Moderate", "pay_rules", "State labor agency", 180, 365, 730),
        # final_pay (4)
        "final_pay_layoff": ("Final Pay — Layoff", "High", "pay_rules", "State labor agency", 90, 180, 365),
        "waiting_time_penalty": ("Waiting Time Penalty", "High", None, "State labor agency", 90, 180, 365),
        # minor_work_permit (6)
        "work_permit": ("Work Permit", "Moderate", "youth_employment", "State labor agency", 180, 365, 730),
        "hour_limits_14_15": ("Hour Limits — Ages 14-15", "Moderate", "youth_employment", "WHD / State labor agency", 180, 365, 730),
        "hour_limits_16_17": ("Hour Limits — Ages 16-17", "Moderate", "youth_employment", "WHD / State labor agency", 180, 365, 730),
        "prohibited_occupations": ("Prohibited Occupations", "Moderate", "youth_employment", "WHD / State labor agency", 365, 730, 1095),
        "entertainment_permits": ("Entertainment Permits", "Moderate", "youth_employment", "State labor agency", 365, 730, 1095),
        "recordkeeping": ("Youth Employment Recordkeeping", "Low/None", "youth_employment", "State labor agency", 365, 730, 1095),
        # scheduling_reporting (5)
        "reporting_time_pay": ("Reporting Time Pay", "High", "scheduling_rules", "State labor agency", 90, 180, 365),
        "predictive_scheduling": ("Predictive Scheduling", "High", "scheduling_rules", "Local/State labor agency", 90, 180, 365),
        "split_shift_premium": ("Split Shift Premium", "High", "scheduling_rules", "State labor agency", 90, 180, 365),
        "on_call_pay": ("On-Call Pay", "Moderate", "scheduling_rules", "State labor agency", 180, 365, 730),
        "spread_of_hours": ("Spread of Hours", "High", "scheduling_rules", "State labor agency", 90, 180, 365),
        # workplace_safety (5)
        "osha_general_duty": ("OSHA General Duty Clause", "Moderate", "workplace_safety", "OSHA / State OSHA plan", 180, 365, 730),
        "injury_illness_recordkeeping": ("Injury/Illness Recordkeeping", "Moderate", "workplace_safety", "OSHA / State OSHA plan", 180, 365, 730),
        "heat_illness_prevention": ("Heat Illness Prevention", "High", "workplace_safety", "OSHA / State OSHA plan", 90, 180, 365),
        "workplace_violence_prevention": ("Workplace Violence Prevention", "Moderate", "workplace_safety", "OSHA / State OSHA plan", 180, 365, 730),
        "hazard_communication": ("Hazard Communication", "Low/None", "workplace_safety", "OSHA / State OSHA plan", 365, 730, 1095),
        # workers_comp (5)
        "mandatory_coverage": ("Mandatory Coverage", "High", "workers_comp", "State workers comp board", 90, 180, 365),
        "claim_filing": ("Claim Filing", "Moderate", "workers_comp", "State workers comp board", 180, 365, 730),
        "return_to_work": ("Return to Work", "Moderate", "workers_comp", "State workers comp board", 180, 365, 730),
        "anti_retaliation": ("Anti-Retaliation", "Moderate", "workers_comp", "State workers comp board", 180, 365, 730),
        "posting_requirements": ("Posting Requirements", "Low/None", "workers_comp", "State workers comp board", 365, 730, 1095),
        # anti_discrimination (6)
        "protected_classes": ("Protected Classes", "High", "discrimination_protections", "EEOC / State civil rights agency", 90, 180, 365),
        "pay_transparency": ("Pay Transparency", "High", "discrimination_protections", "State labor agency", 90, 180, 365),
        "salary_history_ban": ("Salary History Ban", "High", "discrimination_protections", "State labor agency", 90, 180, 365),
        "harassment_prevention_training": ("Harassment Prevention Training", "Moderate", "discrimination_protections", "State civil rights agency", 180, 365, 730),
        "reasonable_accommodation": ("Reasonable Accommodation", "Moderate", "discrimination_protections", "EEOC / State civil rights agency", 180, 365, 730),
        "whistleblower_protection": ("Whistleblower Protection", "Moderate", None, "State labor agency", 180, 365, 730),
        # business_license (4)
        "state_business_registration": ("State Business Registration", "Moderate", None, "Secretary of State", 365, 730, 1095),
        "local_business_license": ("Local Business License", "Moderate", None, "Local government", 365, 730, 1095),
        "professional_licensing": ("Professional Licensing", "Moderate", None, "State licensing board", 180, 365, 730),
        "dba_registration": ("DBA Registration", "Low/None", None, "Secretary of State / County clerk", 365, 730, 1095),
        # tax_rate (7)
        "corporate_income_tax": ("Corporate Income Tax", "High", "tax_obligations", "State revenue agency", 30, 90, 365),
        "franchise_tax": ("Franchise Tax", "Moderate", "tax_obligations", "State revenue agency", 90, 180, 365),
        "unemployment_insurance_tax": ("Unemployment Insurance Tax", "High", "tax_obligations", "State workforce agency", 30, 90, 365),
        "disability_insurance_tax": ("Disability Insurance Tax", "High", "tax_obligations", "State workforce agency", 30, 90, 365),
        "employment_training_tax": ("Employment Training Tax", "Moderate", "tax_obligations", "State workforce agency", 90, 180, 365),
        "sales_use_tax": ("Sales/Use Tax", "Moderate", "tax_obligations", "State revenue agency", 90, 180, 365),
        "local_tax": ("Local Tax", "Moderate", "tax_obligations", "Local government", 90, 180, 365),
        # posting_requirements (9)
        "minimum_wage_poster": ("Minimum Wage Poster", "Low/None", "posting_compliance", "WHD / State labor agency", 365, 730, 1095),
        "discrimination_poster": ("Discrimination Poster", "Low/None", "posting_compliance", "EEOC / State agency", 365, 730, 1095),
        "osha_poster": ("OSHA Poster", "Low/None", "posting_compliance", "OSHA / State OSHA plan", 365, 730, 1095),
        "workers_comp_poster": ("Workers Comp Poster", "Low/None", "posting_compliance", "State workers comp board", 365, 730, 1095),
        "paid_sick_leave_poster": ("Paid Sick Leave Poster", "Low/None", "posting_compliance", "State labor agency", 365, 730, 1095),
        "family_leave_poster": ("Family Leave Poster", "Low/None", "posting_compliance", "WHD / State labor agency", 365, 730, 1095),
        "whistleblower_poster": ("Whistleblower Poster", "Low/None", "posting_compliance", "State labor agency", 365, 730, 1095),
        "wage_order_poster": ("Wage Order Poster", "Low/None", "posting_compliance", "State labor agency", 365, 730, 1095),
        "workplace_violence_poster": ("Workplace Violence Poster", "Low/None", "posting_compliance", "OSHA / State agency", 365, 730, 1095),
    }

    for cat_slug, key_set in _LABOR_REGULATION_KEYS.items():
        for key in sorted(key_set):
            meta = _LABOR_KEY_METADATA.get(key)
            if meta:
                name, variance, group, agency, warn, crit, expired = meta
            else:
                # Fallback for any key not explicitly listed
                name = key.replace("_", " ").title()
                variance = "Moderate"
                group = None
                agency = None
                warn, crit, expired = 90, 180, 365

            weight = 1.5 if variance == "High" else 1.0

            _insert_key_def(
                key=key,
                category_slug=cat_slug,
                name=name,
                description=None,
                enforcing_agency=agency,
                authority_source_urls=[],
                state_variance=variance,
                base_weight=weight,
                update_frequency=None,
                key_group=group,
                staleness_warning=warn,
                staleness_critical=crit,
                staleness_expired=expired,
            )

    # ── 3. Oncology keys (~25 new) ───────────────────────────────────────

    _ONCOLOGY_KEYS = {
        "radiation_safety": [
            ("state_radiation_control_programs", "State Radiation Control Programs", "High", "radiation_safety", "NRC / State radiation control", 365, 730, 1460),
            ("radiation_safety_officer", "Radiation Safety Officer Requirements", "Moderate", "radiation_safety", "NRC / State radiation control", 365, 730, 1460),
            ("linear_accelerator_qa", "Linear Accelerator QA Requirements", "Moderate", "radiation_safety", "NRC / State radiation control", 365, 730, 1460),
            ("brachytherapy_safety", "Brachytherapy Safety Standards", "Moderate", "radiation_safety", "NRC / State radiation control", 365, 730, 1460),
            ("radiation_oncology_safety_team", "Radiation Oncology Safety Team", "Moderate", "radiation_safety", "NRC / State radiation control", 365, 730, 1460),
            ("radioactive_materials_license", "Radioactive Materials License", "High", "radiation_safety", "NRC / State radiation control", 365, 730, 1460),
        ],
        "chemotherapy_handling": [
            ("usp_compounding_standards", "USP Compounding Standards (USP 800)", "High", "chemotherapy_safety", "State Board of Pharmacy", 180, 365, 730),
            ("closed_system_transfer", "Closed System Transfer Devices", "Moderate", "chemotherapy_safety", "State Board of Pharmacy / OSHA", 365, 730, 1460),
            ("hazardous_drug_assessment", "Hazardous Drug Assessment of Risk", "High", "chemotherapy_safety", "State Board of Pharmacy", 180, 365, 730),
            ("spill_management", "Spill Management Protocol", "Moderate", "chemotherapy_safety", "State Board of Pharmacy / OSHA", 365, 730, 1460),
            ("hazardous_waste_disposal", "Hazardous Waste Disposal", "Moderate", "chemotherapy_safety", "EPA / State environmental agency", 365, 730, 1460),
        ],
        "tumor_registry": [
            ("cancer_registry_reporting", "Cancer Registry Reporting", "High", "cancer_registry", "State health department / CDC NPCR", 180, 365, 730),
            ("reporting_timelines", "Registry Reporting Timelines", "High", "cancer_registry", "State health department", 90, 180, 365),
            ("electronic_reporting_format", "Electronic Reporting Format", "Moderate", "cancer_registry", "State health department / CDC NPCR", 365, 730, 1460),
            ("registry_data_quality", "Registry Data Quality Standards", "Moderate", "cancer_registry", "State health department / NAACCR", 365, 730, 1460),
        ],
        "oncology_clinical_trials": [
            ("clinical_trial_coverage_mandates", "Clinical Trial Insurance Coverage Mandates", "High", "clinical_trials", "State insurance commissioner", 90, 180, 365),
            ("right_to_try", "Right to Try Laws", "Moderate", "clinical_trials", "State legislature / FDA", 180, 365, 730),
            ("protocol_deviation_reporting", "Protocol Deviation Reporting", "Moderate", "clinical_trials", "FDA / State IRB", 365, 730, 1460),
            ("adverse_event_reporting", "Adverse Event Reporting", "Moderate", "clinical_trials", "FDA / State health department", 180, 365, 730),
            ("investigational_drug_access", "Investigational Drug Access", "Moderate", "clinical_trials", "FDA / State legislature", 180, 365, 730),
        ],
        "oncology_patient_rights": [
            ("patient_rights_declarations", "Patient Rights Declarations", "Moderate", "patient_rights", "State health department", 180, 365, 730),
            ("hospice_palliative_care", "Hospice and Palliative Care Access", "Moderate", "patient_rights", "State health department / CMS", 180, 365, 730),
            ("advance_directives", "Advance Directives / Right to Natural Death", "Moderate", "patient_rights", "State legislature", 365, 730, 1460),
            ("fertility_preservation_counseling", "Fertility Preservation Counseling", "Moderate", "patient_rights", "State legislature / ASCO", 365, 730, 1460),
            ("cancer_treatment_consent", "Cancer Treatment Informed Consent", "Moderate", "patient_rights", "State medical board", 180, 365, 730),
        ],
    }

    for cat_slug, keys in _ONCOLOGY_KEYS.items():
        for key, name, variance, group, agency, warn, crit, expired in keys:
            weight = 1.5 if variance == "High" else 1.0
            _insert_key_def(
                key=key,
                category_slug=cat_slug,
                name=name,
                description=None,
                enforcing_agency=agency,
                authority_source_urls=[],
                state_variance=variance,
                base_weight=weight,
                update_frequency=None,
                key_group=group,
                staleness_warning=warn,
                staleness_critical=crit,
                staleness_expired=expired,
            )


def _insert_key_def(
    key, category_slug, name, description, enforcing_agency,
    authority_source_urls, state_variance, base_weight, update_frequency,
    key_group, staleness_warning, staleness_critical, staleness_expired,
):
    """Insert a single regulation_key_definition, skipping if exists."""
    import json

    sources_literal = (
        "'{" + ",".join(f'"{u}"' for u in authority_source_urls) + "}'"
        if authority_source_urls
        else "NULL"
    )

    # Escape single quotes in text fields
    name_esc = name.replace("'", "''") if name else ""
    desc_esc = description.replace("'", "''") if description else None
    agency_esc = enforcing_agency.replace("'", "''") if enforcing_agency else None
    freq_esc = update_frequency.replace("'", "''") if update_frequency else None

    op.execute(f"""
        INSERT INTO regulation_key_definitions
            (key, category_slug, category_id, name, description, enforcing_agency,
             authority_source_urls, state_variance, base_weight, update_frequency,
             key_group, staleness_warning_days, staleness_critical_days, staleness_expired_days)
        SELECT
            '{key}',
            '{category_slug}',
            cc.id,
            '{name_esc}',
            {f"'{desc_esc}'" if desc_esc else 'NULL'},
            {f"'{agency_esc}'" if agency_esc else 'NULL'},
            {sources_literal},
            '{state_variance}',
            {base_weight},
            {f"'{freq_esc}'" if freq_esc else 'NULL'},
            {f"'{key_group}'" if key_group else 'NULL'},
            {staleness_warning},
            {staleness_critical},
            {staleness_expired}
        FROM compliance_categories cc
        WHERE cc.slug = '{category_slug}'
        ON CONFLICT (category_slug, key) DO NOTHING
    """)


def downgrade():
    # Drop indexes on jurisdiction_requirements
    op.execute("DROP INDEX IF EXISTS idx_jr_key_definition_id")
    op.execute("DROP INDEX IF EXISTS idx_jr_category_regulation_key")
    op.execute("DROP INDEX IF EXISTS idx_jr_regulation_key")

    # Drop new columns
    op.execute("ALTER TABLE jurisdiction_requirements DROP COLUMN IF EXISTS key_definition_id")
    op.execute("ALTER TABLE jurisdiction_requirements DROP COLUMN IF EXISTS regulation_key")

    # Drop tables (reverse order of creation)
    op.execute("DROP TABLE IF EXISTS repository_alerts")
    op.execute("DROP TABLE IF EXISTS regulation_key_definition_history")
    op.execute("DROP TABLE IF EXISTS regulation_key_definitions")
