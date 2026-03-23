#!/usr/bin/env python3
"""Generate client/src/generated/complianceCategories.ts from the compliance registry.

Usage:
    python3 scripts/generate_compliance_ts.py

Reads the canonical compliance registry (server/app/core/compliance_registry.py)
and emits a TypeScript file so the frontend stays in sync without manual edits.
"""

import os
import sys

# ---------------------------------------------------------------------------
# Paths — all relative to this script's location
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
SERVER_DIR = os.path.join(PROJECT_ROOT, "server")
OUTPUT_PATH = os.path.join(
    PROJECT_ROOT, "client", "src", "generated", "complianceCategories.ts"
)

# Add server/ to sys.path so we can import app.core.compliance_registry
sys.path.insert(0, SERVER_DIR)

try:
    from app.core.compliance_registry import (
        CATEGORIES,
        REGULATIONS,
        REGULATIONS_BY_CATEGORY,
        EXPECTED_REGULATION_KEYS,
        _LABOR_REGULATION_KEYS,
        _ONCOLOGY_REGULATION_KEYS,
        LABOR_CATEGORIES,
        HEALTHCARE_CATEGORIES,
        ONCOLOGY_CATEGORIES,
        MEDICAL_COMPLIANCE_CATEGORIES,
    )
except ImportError as exc:
    print(
        f"ERROR: Could not import from app.core.compliance_registry.\n"
        f"  Make sure server/app/core/compliance_registry.py exists and is valid.\n"
        f"  Import error: {exc}",
        file=sys.stderr,
    )
    sys.exit(1)


def _ts_string(s: str) -> str:
    """Escape a string for safe inclusion in a TypeScript single-quoted literal."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def generate() -> str:
    lines: list[str] = []

    lines.append(
        "// Auto-generated from server/app/core/compliance_registry.py"
    )
    lines.append(
        "// Do not edit manually — run: python3 scripts/generate_compliance_ts.py"
    )
    lines.append("")

    # -----------------------------------------------------------------------
    # CATEGORY_LABELS
    # -----------------------------------------------------------------------
    lines.append("export const CATEGORY_LABELS: Record<string, string> = {")
    for cat in CATEGORIES:
        lines.append(f"  '{_ts_string(cat.key)}': '{_ts_string(cat.label)}',")
    lines.append("};")
    lines.append("")

    # -----------------------------------------------------------------------
    # CATEGORY_SHORT_LABELS
    # -----------------------------------------------------------------------
    lines.append(
        "export const CATEGORY_SHORT_LABELS: Record<string, string> = {"
    )
    for cat in CATEGORIES:
        lines.append(
            f"  '{_ts_string(cat.key)}': '{_ts_string(cat.short_label)}',"
        )
    lines.append("};")
    lines.append("")

    # -----------------------------------------------------------------------
    # CategoryGroup type + CATEGORY_GROUPS map
    # -----------------------------------------------------------------------
    groups = sorted({cat.group for cat in CATEGORIES})
    group_union = " | ".join(f"'{g}'" for g in groups)
    lines.append(f"export type CategoryGroup = {group_union};")
    lines.append("")
    lines.append(
        "export const CATEGORY_GROUPS: Record<string, CategoryGroup> = {"
    )
    for cat in CATEGORIES:
        lines.append(
            f"  '{_ts_string(cat.key)}': '{_ts_string(cat.group)}',"
        )
    lines.append("};")
    lines.append("")

    # -----------------------------------------------------------------------
    # Per-group Sets
    # -----------------------------------------------------------------------
    def _emit_set(name: str, keys: frozenset | set) -> None:
        sorted_keys = sorted(keys)
        items = ", ".join(f"'{_ts_string(k)}'" for k in sorted_keys)
        lines.append(f"export const {name} = new Set([{items}]);")

    _emit_set("LABOR_CATEGORIES", LABOR_CATEGORIES)
    _emit_set("HEALTHCARE_CATEGORIES", HEALTHCARE_CATEGORIES)
    _emit_set("ONCOLOGY_CATEGORIES", ONCOLOGY_CATEGORIES)
    _emit_set("MEDICAL_COMPLIANCE_CATEGORIES", MEDICAL_COMPLIANCE_CATEGORIES)

    # Supplementary — anything not in the other groups
    supplementary_keys = {
        cat.key
        for cat in CATEGORIES
        if cat.group == "supplementary"
    }
    if supplementary_keys:
        _emit_set("SUPPLEMENTARY_CATEGORIES", supplementary_keys)

    lines.append("")

    # -----------------------------------------------------------------------
    # ALL_CATEGORY_KEYS
    # -----------------------------------------------------------------------
    all_keys = [cat.key for cat in CATEGORIES]
    items_str = ", ".join(f"'{_ts_string(k)}'" for k in all_keys)
    lines.append(f"export const ALL_CATEGORY_KEYS: string[] = [{items_str}];")
    lines.append("")

    # -----------------------------------------------------------------------
    # REGULATION_NAMES — reg_key -> display name (all 353 keys)
    # -----------------------------------------------------------------------
    # Build a complete name map: healthcare RegulationDefs + labor + oncology
    all_names: dict[str, str] = {}
    for reg in REGULATIONS:
        all_names[reg.key] = reg.name
    # Labor keys: derive display name from key if not in RegulationDef
    _LABOR_KEY_NAMES = {
        "state_minimum_wage": "State Minimum Wage",
        "tipped_minimum_wage": "Tipped Minimum Wage",
        "exempt_salary_threshold": "Exempt Salary Threshold",
        "fast_food_minimum_wage": "Fast Food Minimum Wage",
        "healthcare_minimum_wage": "Healthcare Minimum Wage",
        "large_employer_minimum_wage": "Large Employer Minimum Wage",
        "small_employer_minimum_wage": "Small Employer Minimum Wage",
        "youth_minimum_wage": "Youth Minimum Wage",
        "tip_credit_prohibition": "Tip Credit Prohibition",
        "local_minimum_wage": "Local Minimum Wage",
        "daily_weekly_overtime": "Daily/Weekly Overtime",
        "double_time": "Double Time",
        "seventh_day_overtime": "Seventh Day Overtime",
        "alternative_workweek": "Alternative Workweek",
        "healthcare_overtime": "Healthcare Overtime",
        "mandatory_overtime_restrictions": "Mandatory Overtime Restrictions",
        "comp_time": "Compensatory Time",
        "fmla": "FMLA",
        "state_family_leave": "State Family Leave",
        "state_paid_family_leave": "State Paid Family Leave",
        "state_disability_insurance": "State Disability Insurance",
        "pregnancy_disability_leave": "Pregnancy Disability Leave",
        "paid_sick_leave": "Paid Sick Leave",
        "bereavement_leave": "Bereavement Leave",
        "organ_donor_leave": "Organ Donor Leave",
        "domestic_violence_leave": "Domestic Violence Leave",
        "jury_duty_leave": "Jury Duty Leave",
        "military_leave": "Military Leave",
        "voting_leave": "Voting Leave",
        "school_activity_leave": "School Activity Leave",
        "reproductive_loss_leave": "Reproductive Loss Leave",
        "bone_marrow_donor_leave": "Bone Marrow Donor Leave",
        "state_paid_sick_leave": "State Paid Sick Leave",
        "accrual_and_usage_caps": "Accrual and Usage Caps",
        "local_sick_leave": "Local Sick Leave",
        "meal_break": "Meal Break",
        "rest_break": "Rest Break",
        "lactation_break": "Lactation Break",
        "on_duty_meal_agreement": "On-Duty Meal Agreement",
        "healthcare_meal_waiver": "Healthcare Meal Waiver",
        "missed_break_penalty": "Missed Break Penalty",
        "standard_pay_frequency": "Standard Pay Frequency",
        "final_pay_termination": "Final Pay — Termination",
        "final_pay_resignation": "Final Pay — Resignation",
        "exempt_monthly_pay": "Exempt Monthly Pay",
        "payday_posting": "Payday Posting Requirements",
        "wage_notice": "Wage Notice",
        "final_pay_layoff": "Final Pay — Layoff",
        "waiting_time_penalty": "Waiting Time Penalty",
        "work_permit": "Work Permit",
        "hour_limits_14_15": "Hour Limits — Ages 14-15",
        "hour_limits_16_17": "Hour Limits — Ages 16-17",
        "prohibited_occupations": "Prohibited Occupations",
        "entertainment_permits": "Entertainment Permits",
        "recordkeeping": "Youth Employment Recordkeeping",
        "reporting_time_pay": "Reporting Time Pay",
        "predictive_scheduling": "Predictive Scheduling",
        "split_shift_premium": "Split Shift Premium",
        "on_call_pay": "On-Call Pay",
        "spread_of_hours": "Spread of Hours",
        "osha_general_duty": "OSHA General Duty Clause",
        "injury_illness_recordkeeping": "Injury/Illness Recordkeeping",
        "heat_illness_prevention": "Heat Illness Prevention",
        "workplace_violence_prevention": "Workplace Violence Prevention",
        "hazard_communication": "Hazard Communication",
        "mandatory_coverage": "Mandatory Coverage",
        "claim_filing": "Claim Filing",
        "return_to_work": "Return to Work",
        "anti_retaliation": "Anti-Retaliation",
        "posting_requirements": "Posting Requirements",
        "protected_classes": "Protected Classes",
        "pay_transparency": "Pay Transparency",
        "salary_history_ban": "Salary History Ban",
        "harassment_prevention_training": "Harassment Prevention Training",
        "reasonable_accommodation": "Reasonable Accommodation",
        "whistleblower_protection": "Whistleblower Protection",
        "state_business_registration": "State Business Registration",
        "local_business_license": "Local Business License",
        "professional_licensing": "Professional Licensing",
        "dba_registration": "DBA Registration",
        "corporate_income_tax": "Corporate Income Tax",
        "franchise_tax": "Franchise Tax",
        "unemployment_insurance_tax": "Unemployment Insurance Tax",
        "disability_insurance_tax": "Disability Insurance Tax",
        "employment_training_tax": "Employment Training Tax",
        "sales_use_tax": "Sales/Use Tax",
        "local_tax": "Local Tax",
        "minimum_wage_poster": "Minimum Wage Poster",
        "discrimination_poster": "Discrimination Poster",
        "osha_poster": "OSHA Poster",
        "workers_comp_poster": "Workers Comp Poster",
        "paid_sick_leave_poster": "Paid Sick Leave Poster",
        "family_leave_poster": "Family Leave Poster",
        "whistleblower_poster": "Whistleblower Poster",
        "wage_order_poster": "Wage Order Poster",
        "workplace_violence_poster": "Workplace Violence Poster",
    }
    all_names.update(_LABOR_KEY_NAMES)
    # Oncology keys
    _ONCOLOGY_KEY_NAMES = {
        "state_radiation_control_programs": "State Radiation Control Programs",
        "radiation_safety_officer": "Radiation Safety Officer Requirements",
        "linear_accelerator_qa": "Linear Accelerator QA Requirements",
        "brachytherapy_safety": "Brachytherapy Safety Standards",
        "radiation_oncology_safety_team": "Radiation Oncology Safety Team",
        "radioactive_materials_license": "Radioactive Materials License",
        "usp_compounding_standards": "USP Compounding Standards (USP 800)",
        "closed_system_transfer": "Closed System Transfer Devices",
        "hazardous_drug_assessment": "Hazardous Drug Assessment of Risk",
        "spill_management": "Spill Management Protocol",
        "hazardous_waste_disposal": "Hazardous Waste Disposal",
        "cancer_registry_reporting": "Cancer Registry Reporting",
        "reporting_timelines": "Registry Reporting Timelines",
        "electronic_reporting_format": "Electronic Reporting Format",
        "registry_data_quality": "Registry Data Quality Standards",
        "clinical_trial_coverage_mandates": "Clinical Trial Insurance Coverage Mandates",
        "right_to_try": "Right to Try Laws",
        "protocol_deviation_reporting": "Protocol Deviation Reporting",
        "adverse_event_reporting": "Adverse Event Reporting",
        "investigational_drug_access": "Investigational Drug Access",
        "patient_rights_declarations": "Patient Rights Declarations",
        "hospice_palliative_care": "Hospice and Palliative Care Access",
        "advance_directives": "Advance Directives / Right to Natural Death",
        "fertility_preservation_counseling": "Fertility Preservation Counseling",
        "cancer_treatment_consent": "Cancer Treatment Informed Consent",
    }
    all_names.update(_ONCOLOGY_KEY_NAMES)

    lines.append(
        "export const REGULATION_NAMES: Record<string, string> = {"
    )
    for key in sorted(all_names.keys()):
        lines.append(
            f"  '{_ts_string(key)}': '{_ts_string(all_names[key])}',"
        )
    lines.append("};")
    lines.append("")

    # -----------------------------------------------------------------------
    # REGULATION_KEYS_BY_CATEGORY — category_key -> [reg_key, ...]
    # Now covers ALL categories (labor + healthcare + oncology + supplementary)
    # -----------------------------------------------------------------------
    lines.append(
        "export const REGULATION_KEYS_BY_CATEGORY: Record<string, string[]> = {"
    )
    for cat_key in sorted(EXPECTED_REGULATION_KEYS.keys()):
        reg_keys = sorted(EXPECTED_REGULATION_KEYS[cat_key])
        reg_keys_str = ", ".join(
            f"'{_ts_string(k)}'" for k in reg_keys
        )
        lines.append(f"  '{_ts_string(cat_key)}': [{reg_keys_str}],")
    lines.append("};")
    lines.append("")

    # -----------------------------------------------------------------------
    # REGULATION_KEY_WEIGHTS — reg_key -> base_weight
    # -----------------------------------------------------------------------
    all_weights: dict[str, float] = {}
    for reg in REGULATIONS:
        all_weights[reg.key] = 1.5 if reg.state_variance == "High" else 1.0
    # Labor: use same variance logic from the seed migration
    _HIGH_VARIANCE_LABOR = {
        "state_minimum_wage", "tipped_minimum_wage", "fast_food_minimum_wage",
        "healthcare_minimum_wage", "large_employer_minimum_wage",
        "small_employer_minimum_wage", "local_minimum_wage", "tip_credit_prohibition",
        "daily_weekly_overtime", "double_time", "seventh_day_overtime",
        "mandatory_overtime_restrictions",
        "state_family_leave", "state_paid_family_leave", "state_disability_insurance",
        "pregnancy_disability_leave", "paid_sick_leave",
        "state_paid_sick_leave", "accrual_and_usage_caps", "local_sick_leave",
        "meal_break", "rest_break", "missed_break_penalty",
        "final_pay_termination", "final_pay_resignation", "final_pay_layoff",
        "waiting_time_penalty",
        "reporting_time_pay", "predictive_scheduling", "split_shift_premium",
        "spread_of_hours", "heat_illness_prevention",
        "mandatory_coverage",
        "protected_classes", "pay_transparency", "salary_history_ban",
        "corporate_income_tax", "unemployment_insurance_tax", "disability_insurance_tax",
    }
    for cat_keys in _LABOR_REGULATION_KEYS.values():
        for k in cat_keys:
            all_weights[k] = 1.5 if k in _HIGH_VARIANCE_LABOR else 1.0
    # Oncology
    _HIGH_VARIANCE_ONCOLOGY = {
        "state_radiation_control_programs", "radioactive_materials_license",
        "usp_compounding_standards", "hazardous_drug_assessment",
        "cancer_registry_reporting", "reporting_timelines",
        "clinical_trial_coverage_mandates",
    }
    for cat_keys in _ONCOLOGY_REGULATION_KEYS.values():
        for k in cat_keys:
            all_weights[k] = 1.5 if k in _HIGH_VARIANCE_ONCOLOGY else 1.0

    lines.append(
        "export const REGULATION_KEY_WEIGHTS: Record<string, number> = {"
    )
    for key in sorted(all_weights.keys()):
        lines.append(f"  '{_ts_string(key)}': {all_weights[key]},")
    lines.append("};")
    lines.append("")

    # -----------------------------------------------------------------------
    # REGULATION_KEY_GROUPS — reg_key -> key_group (only keys with groups)
    # -----------------------------------------------------------------------
    # Import group assignments from the seed migration metadata
    lines.append(
        "export const REGULATION_KEY_GROUPS: Record<string, string> = {"
    )
    # We don't have groups in the Python registry yet — they're in the DB.
    # For now, emit a placeholder that the DB-backed approach will replace.
    # The key-coverage API returns group data dynamically anyway.
    lines.append("};")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    ts_source = generate()

    # Ensure output directory exists
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(ts_source)

    n_categories = len(CATEGORIES)
    n_total_keys = sum(len(v) for v in EXPECTED_REGULATION_KEYS.values())
    # Use a relative path for the printed message
    rel_output = os.path.relpath(OUTPUT_PATH, PROJECT_ROOT)
    print(
        f"Generated {rel_output} "
        f"({n_categories} categories, {n_total_keys} regulation keys)"
    )


if __name__ == "__main__":
    main()
