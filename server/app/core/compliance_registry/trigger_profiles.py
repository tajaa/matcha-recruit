from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple  # noqa: F401

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Trigger profiles — drive targeted Gemini research passes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TriggerProfileDef:
    key: str                          # "fqhc", "medi_cal"
    label: str                        # "Federally Qualified Health Center"
    trigger_condition: dict           # JSON condition document
    applicable_categories: tuple      # Categories this trigger adds requirements to
    research_instruction: str         # Gemini prompt fragment
    attribute_key: str                # facility_attributes key to check
    attribute_match: Any              # Expected value


TRIGGER_PROFILES: Tuple[TriggerProfileDef, ...] = (
    TriggerProfileDef(
        key="fqhc",
        label="Federally Qualified Health Center",
        trigger_condition={"type": "entity_type", "value": "fqhc"},
        applicable_categories=(
            "billing_integrity", "clinical_safety", "healthcare_workforce",
            "quality_reporting", "payer_relations",
        ),
        research_instruction=(
            "Research ADDITIONAL requirements that apply SPECIFICALLY to "
            "Federally Qualified Health Centers (FQHCs) under HRSA Section 330 "
            "and 42 CFR Part 51c. Include HRSA's 19 program requirements, "
            "UDS reporting obligations, sliding fee discount policies, "
            "and scope-of-project limitations. Only return requirements that "
            "are UNIQUE to FQHCs — do not repeat general healthcare rules."
        ),
        attribute_key="entity_type",
        attribute_match="fqhc",
    ),
    TriggerProfileDef(
        key="medi_cal",
        label="Medi-Cal Participation",
        trigger_condition={
            "type": "attribute", "key": "payer_contracts",
            "operator": "contains", "value": "medi_cal",
        },
        applicable_categories=(
            "billing_integrity", "payer_relations", "quality_reporting",
        ),
        research_instruction=(
            "Research ADDITIONAL billing and payer requirements that apply "
            "SPECIFICALLY to facilities that accept Medi-Cal (California Medicaid). "
            "Include Medi-Cal provider enrollment rules, DHCS billing manual "
            "requirements, Treatment Authorization Requests (TARs), "
            "and Medi-Cal managed care contract obligations. Only return "
            "requirements SPECIFIC to Medi-Cal participation."
        ),
        attribute_key="payer_contracts",
        attribute_match="medi_cal",
    ),
    TriggerProfileDef(
        key="medicare",
        label="Medicare Participation",
        trigger_condition={
            "type": "attribute", "key": "payer_contracts",
            "operator": "contains", "value": "medicare",
        },
        applicable_categories=(
            "billing_integrity", "payer_relations", "quality_reporting",
        ),
        research_instruction=(
            "Research ADDITIONAL requirements that apply SPECIFICALLY to "
            "Medicare-participating providers. Include CMS Conditions of "
            "Participation (CoPs), Medicare billing rules under 42 CFR 424, "
            "MIPS/APM quality reporting, and Medicare Advantage contract "
            "requirements. Only return requirements SPECIFIC to Medicare participation."
        ),
        attribute_key="payer_contracts",
        attribute_match="medicare",
    ),
    TriggerProfileDef(
        key="critical_access_hospital",
        label="Critical Access Hospital",
        trigger_condition={"type": "entity_type", "value": "critical_access_hospital"},
        applicable_categories=(
            "billing_integrity", "clinical_safety", "emergency_preparedness",
        ),
        research_instruction=(
            "Research ADDITIONAL requirements that apply SPECIFICALLY to "
            "Critical Access Hospitals (CAHs) under 42 CFR 485 Subpart F. "
            "Include 25-bed limit compliance, 96-hour length-of-stay "
            "requirements, cost-based reimbursement rules, and CAH-specific "
            "Conditions of Participation. Only return requirements UNIQUE to CAHs."
        ),
        attribute_key="entity_type",
        attribute_match="critical_access_hospital",
    ),
    TriggerProfileDef(
        key="behavioral_health",
        label="Behavioral Health Facility",
        trigger_condition={"type": "entity_type", "value": "behavioral_health"},
        applicable_categories=(
            "reproductive_behavioral", "state_licensing", "healthcare_workforce",
            "clinical_safety", "hipaa_privacy", "corporate_integrity",
            "quality_reporting",
        ),
        research_instruction=(
            "Research ADDITIONAL requirements for BEHAVIORAL HEALTH facilities. "
            "Include state behavioral health facility licensing (DHCS or equivalent), "
            "42 CFR Part 2 substance use disorder confidentiality, Joint Commission "
            "behavioral health accreditation, SAMHSA certification for opioid treatment "
            "programs, mental health parity compliance (MHPAEA), seclusion & restraint "
            "regulations (42 CFR 482.13), state involuntary commitment procedures, and "
            "behavioral health workforce credentialing (LCSW, LMFT, LPC, BCBA). Only "
            "return requirements UNIQUE to behavioral health facilities."
        ),
        attribute_key="entity_type",
        attribute_match="behavioral_health",
    ),
)


def get_activated_profiles(facility_attributes: dict) -> List[TriggerProfileDef]:
    """Return trigger profiles activated by the given facility attributes."""
    if not facility_attributes:
        return []
    activated = []
    for profile in TRIGGER_PROFILES:
        actual = facility_attributes.get(profile.attribute_key)
        if actual is None:
            continue
        if profile.attribute_key == "payer_contracts":
            if isinstance(actual, (list, set)) and profile.attribute_match in actual:
                activated.append(profile)
        else:
            if actual == profile.attribute_match:
                activated.append(profile)
    return activated


