from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple  # noqa: F401


# ---------------------------------------------------------------------------
# SEVERITY — how bad non-compliance is (imminent physical harm / severe
# statutory liability), NOT how much the rule varies by state (that's
# state_variance). Seeds regulation_key_definitions.severity via the rkdsev01
# migration, the same way base_weight is derived from state_variance in the
# initial seed — the DB column is the runtime source, this map is the authority.
#
# ⚠ CURATED STARTER SET — needs compliance-domain review before it drives any
# customer-facing prioritization. Everything not listed defaults to 'moderate';
# add rows deliberately. Keyed (category, key).
# ---------------------------------------------------------------------------
_SEVERITY_CRITICAL: frozenset = frozenset({
    # imminent physical-harm safety
    ("workplace_safety", "osha_general_duty"),
    ("workplace_safety", "injury_illness_recordkeeping"),
    ("workplace_safety", "heat_illness_prevention"),
    ("workplace_safety", "workplace_violence_prevention"),
    ("workplace_safety", "hazard_communication"),
    ("machine_safety", "lockout_tagout"),
    ("machine_safety", "machine_guarding"),
    ("machine_safety", "confined_space"),
    ("machine_safety", "electrical_safety"),
    ("process_safety", "osha_psm"),
    ("process_safety", "process_hazard_analysis"),
    ("process_safety", "mechanical_integrity"),
    ("process_safety", "emergency_action_plan"),
    ("chemical_safety", "hazcom_ghs"),
    ("chemical_safety", "sds_management"),
    ("chemical_safety", "hazardous_substance_storage"),
    ("radiation_safety", "radioactive_materials_license"),
    ("radiation_safety", "radiation_safety_officer"),
    # child labor — prohibited work / hour caps for the youngest
    ("minor_work_permit", "prohibited_occupations"),
    ("minor_work_permit", "hour_limits_14_15"),
    # core wage / workers-comp coverage (statutory penalties)
    ("minimum_wage", "state_minimum_wage"),
    ("overtime", "daily_weekly_overtime"),
    ("final_pay", "final_pay_termination"),
    ("final_pay", "waiting_time_penalty"),
    ("workers_comp", "mandatory_coverage"),
    # core anti-discrimination
    ("anti_discrimination", "protected_classes"),
    ("anti_discrimination", "harassment_prevention_training"),
    ("anti_discrimination", "reasonable_accommodation"),
    # patient-safety / PHI
    ("clinical_safety", "emtala"),
    ("clinical_safety", "medication_management_controlled_substances"),
    ("clinical_safety", "infection_control_prevention_standards"),
    ("hipaa_privacy", "hipaa_privacy_rule"),
    ("hipaa_privacy", "hipaa_security_rule"),
    ("hipaa_privacy", "hipaa_breach_notification_rule"),
})
_SEVERITY_HIGH: frozenset = frozenset({
    ("workers_comp", "claim_filing"),
    ("workers_comp", "anti_retaliation"),
    ("workers_comp", "posting_requirements"),
    ("minor_work_permit", "work_permit"),
    ("minor_work_permit", "hour_limits_16_17"),
    ("minimum_wage", "tipped_minimum_wage"),
    ("minimum_wage", "exempt_salary_threshold"),
    ("overtime", "double_time"),
    ("overtime", "mandatory_overtime_restrictions"),
    ("final_pay", "final_pay_resignation"),
    ("anti_discrimination", "pay_transparency"),
    ("anti_discrimination", "whistleblower_protection"),
    ("machine_safety", "powered_industrial_trucks"),
    ("machine_safety", "crane_hoist_safety"),
    ("radiation_safety", "linear_accelerator_qa"),
    ("radiation_safety", "brachytherapy_safety"),
    ("clinical_safety", "sentinel_event_reporting"),
    ("clinical_safety", "informed_consent_requirements"),
    ("clinical_safety", "restraint_seclusion_standards"),
})

SEVERITY_LEVELS = ("critical", "high", "moderate", "low")


def resolve_severity(category: str, key: str) -> str:
    """Seed severity for one (category, key). Curated overrides → else 'moderate'."""
    if (category, key) in _SEVERITY_CRITICAL:
        return "critical"
    if (category, key) in _SEVERITY_HIGH:
        return "high"
    return "moderate"
