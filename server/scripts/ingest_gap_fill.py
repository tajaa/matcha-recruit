#!/usr/bin/env python3
"""
Batch-ingest gap-fill healthcare research markdown into jurisdiction_requirements.

Handles any *_healthcare_gaps.md file in server/scripts/. Designed for reuse:
  - Parses multiple markdown heading formats (####, **N. Title**, ### Title)
  - Applies state-level requirements to ALL city jurisdictions in that state
  - Upserts via ON CONFLICT — safe to rerun
  - Only ingests state-level requirements for the 8 thin healthcare categories
  - Links to regulation_key_definitions where possible

Usage:
    # Dry run — parse and preview, no DB writes
    python scripts/ingest_gap_fill.py --dry-run

    # Ingest all *_healthcare_gaps.md files
    python scripts/ingest_gap_fill.py

    # Ingest a specific file
    python scripts/ingest_gap_fill.py --file scripts/CA_west_healthcare_gaps.md

    # Ingest only specific states
    python scripts/ingest_gap_fill.py --states CA,CO,WA

    # Filter to specific categories
    python scripts/ingest_gap_fill.py --categories telehealth,cybersecurity
"""

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SKIP_REDIS", "1")

# ── State code → full name mapping ──────────────────────────────────────────
STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}

TARGET_CATEGORIES = {
    "telehealth", "cybersecurity", "language_access", "emerging_regulatory",
    "health_it", "marketing_comms", "tax_exempt", "transplant_organ",
}

# ── Research key → canonical key remapping ──────────────────────────────────
# Maps state-specific research keys to existing canonical keys in
# EXPECTED_REGULATION_KEYS. Built from KEY_MAPPING.md review.
CANONICAL_KEY_MAP: Dict[str, str] = {
    # telehealth
    "az_telehealth_definition": "state_telehealth_practice_standards",
    "az_telehealth_insurance_parity": "state_telehealth_parity_laws",
    "az_telehealth_interstate_registration": "interstate_medical_licensure_compact",
    "ca_telehealth_ab_744_payment_parity": "state_telehealth_parity_laws",
    "ca_telehealth_bpc_2290_5": "state_telehealth_practice_standards",
    "ca_telehealth_licensure_requirement": "state_telehealth_practice_standards",
    "ca_telehealth_sb_184_medi_cal_parity": "state_telehealth_parity_laws",
    "co_telehealth_parity_crs_10_16_123": "state_telehealth_parity_laws",
    "co_telehealth_oos_registration_sb_24_141": "interstate_medical_licensure_compact",
    "co_telehealth_medicaid_10_ccr_2505_10_8095": "state_telehealth_parity_laws",
    "hi_telehealth_practice": "state_telehealth_practice_standards",
    "hi_telehealth_insurance_parity": "state_telehealth_parity_laws",
    "hi_telehealth_audio_only": "state_telehealth_parity_laws",
    "hi_telehealth_controlled_substances": "ryan_haight_act",
    "id_telehealth_virtual_care_access_act": "state_telehealth_practice_standards",
    "id_telehealth_prescribing_restrictions": "state_telehealth_practice_standards",
    "id_telehealth_informed_consent": "state_telehealth_practice_standards",
    "id_telehealth_continuity_of_care": "state_telehealth_practice_standards",
    "id_telehealth_interstate_mental_health": "psypact",
    "nv_telehealth_licensure": "state_telehealth_practice_standards",
    "nv_telehealth_payment_parity": "state_telehealth_parity_laws",
    "nv_telehealth_patient_relationship": "state_telehealth_practice_standards",
    "or_telehealth_payment_parity": "state_telehealth_parity_laws",
    "or_telemedicine_cross_state_license": "interstate_medical_licensure_compact",
    "ut_telehealth_scope_prescribing": "state_telehealth_practice_standards",
    "ut_telehealth_coverage_parity": "state_telehealth_parity_laws",
    "wa_telehealth_audio_only_coverage": "state_telehealth_parity_laws",
    # cybersecurity
    "ca_cybersecurity_sb_446_breach_notification": "state_data_breach_notification_laws",
    "ca_cybersecurity_cmia_civil_code_56": "state_cybersecurity_requirements",
    "ca_cybersecurity_ccpa_audit_requirements": "state_cybersecurity_requirements",
    "co_breach_notification_crs_6_1_716": "state_data_breach_notification_laws",
    "co_privacy_act_crs_6_1_1301": "state_cybersecurity_requirements",
    "or_breach_notification_ocipa": "state_data_breach_notification_laws",
    "or_consumer_privacy_act_health_data": "state_cybersecurity_requirements",
    "ut_breach_notification_13_44": "state_data_breach_notification_laws",
    "ut_ucpa_sensitive_health_data": "state_cybersecurity_requirements",
    "wa_breach_notification_health_data": "state_data_breach_notification_laws",
    "wa_mhmda_geofencing_enforcement": "state_cybersecurity_requirements",
    "nv_consumer_health_data_privacy": "state_cybersecurity_requirements",
    "nv_sb220_data_sale_optout": "state_cybersecurity_requirements",
    "hi_insurance_data_security": "state_cybersecurity_requirements",
    "id_personal_information_definition": "state_data_breach_notification_laws",
    "az_data_breach_penalties": "state_data_breach_notification_laws",
    "texas_medical_records_privacy_act": "state_cybersecurity_requirements",
    "texas_sb_1188_ehr_storage": "state_cybersecurity_requirements",
    # language_access
    "ca_language_access_hsc_1259": "state_language_access_laws",
    "ca_language_access_dymally_alatorre_gov_7290": "state_language_access_laws",
    "ca_language_access_sb_1078_office": "state_language_access_laws",
    "co_language_access_facility_licensure_6_ccr_1011_1": "state_language_access_laws",
    "co_language_access_assessment_hb_25_1153": "state_language_access_laws",
    "co_language_access_workers_comp_interpreter": "state_language_access_laws",
    "hi_language_access_law": "state_language_access_laws",
    "hi_sign_language_healthcare": "state_language_access_laws",
    "id_sign_language_interpreter_license": "state_language_access_laws",
    "nv_healthcare_language_access": "state_language_access_laws",
    "or_healthcare_interpreter_certification": "state_language_access_laws",
    "or_interpretation_service_company": "state_language_access_laws",
    "ut_medical_language_interpreter_act": "state_language_access_laws",
    "wa_healthcare_interpreter_certification": "state_language_access_laws",
    "wa_medicaid_interpreter_services": "state_language_access_laws",
    "az_ahcccs_language_access": "state_language_access_laws",
    "az_sign_language_interpreter_licensure": "state_language_access_laws",
    # emerging_regulatory
    "az_ai_healthcare_claims_review": "ai_algorithmic_decisionmaking",
    "ca_emerging_regulatory_ab_489_ai_healthcare": "ai_algorithmic_decisionmaking",
    "ca_emerging_regulatory_ccpa_admt": "ai_algorithmic_decisionmaking",
    "co_ai_act_sb_24_205": "ai_algorithmic_decisionmaking",
    "nv_ai_healthcare_disclosure": "ai_algorithmic_decisionmaking",
    "nv_ai_mental_health_prohibition": "ai_algorithmic_decisionmaking",
    "ut_ai_policy_act_healthcare_disclosure": "ai_algorithmic_decisionmaking",
    "wa_ai_task_force_healthcare_prior_auth": "ai_algorithmic_decisionmaking",
    "id_ai_innovation_protection": "ai_algorithmic_decisionmaking",
    # health_it
    "az_hie_opt_out_requirements": "state_hie_requirements",
    "az_hie_interoperability_standards": "state_hie_requirements",
    "ca_health_it_ab_133_dxf": "state_hie_requirements",
    "ca_health_it_ab_352_sensitive_services": "state_hie_requirements",
    "co_hie_opt_out_consent_corhio": "state_hie_requirements",
    "hi_health_data_exchange_framework": "state_hie_requirements",
    "hi_hie_designation": "state_hie_requirements",
    "id_health_data_exchange_participation": "state_hie_requirements",
    "nv_hie_opt_in_consent": "state_hie_requirements",
    "or_hitoc_hie_governance": "state_hie_requirements",
    "ut_chie_medicaid_enrollment": "state_hie_requirements",
    "wa_my_health_my_data_act": "state_hie_requirements",
    "co_pdmp_mandatory_check_ehr_integration": "eprescribing_for_controlled_substances",
    "wa_pmp_ehr_integration_mandate": "eprescribing_for_controlled_substances",
    "texas_ehr_data_localization_and_ai": "state_hie_requirements",
    "tx_ehr_data_localization_and_security": "state_hie_requirements",
    # marketing_comms
    "az_medical_advertising_rules": "state_consumer_protection_deceptive_practices",
    "az_health_insurance_advertising": "state_consumer_protection_deceptive_practices",
    "ca_marketing_comms_bpc_651": "state_consumer_protection_deceptive_practices",
    "ca_marketing_comms_hsc_119402": "state_consumer_protection_deceptive_practices",
    "co_medical_advertising_crs_12_240_121_rule_290": "state_consumer_protection_deceptive_practices",
    "co_pharma_marketing_hb_19_1131": "state_consumer_protection_deceptive_practices",
    "hi_false_advertising_drugs_devices": "state_consumer_protection_deceptive_practices",
    "hi_deceptive_trade_practices": "state_consumer_protection_deceptive_practices",
    "id_physician_advertising_discipline": "state_consumer_protection_deceptive_practices",
    "nv_healthcare_advertising_disclosure": "state_consumer_protection_deceptive_practices",
    "or_medical_advertising_false_claims": "state_consumer_protection_deceptive_practices",
    "or_insurance_marketing_restrictions": "state_consumer_protection_deceptive_practices",
    "ut_cosmetic_medical_advertising": "state_consumer_protection_deceptive_practices",
    "wa_controlled_substance_advertising_ban": "state_consumer_protection_deceptive_practices",
    "wa_health_plan_marketing_antidiscrimination": "state_consumer_protection_deceptive_practices",
    "ny_healthcare_advertising": "state_consumer_protection_deceptive_practices",
    "texas_healthcare_advertising_rules": "state_consumer_protection_deceptive_practices",
    "tx_medical_advertising_rules": "state_consumer_protection_deceptive_practices",
    # tax_exempt
    "ca_tax_exempt_sb_697_community_benefit": "state_community_benefit_requirements",
    "ca_tax_exempt_ab_204_reporting_penalties": "state_community_benefit_requirements",
    "co_hospital_community_benefit_hb_19_1320": "state_community_benefit_requirements",
    "nv_nonprofit_hospital_community_benefit": "state_community_benefit_requirements",
    "or_hospital_community_benefit_hb3076": "state_community_benefit_requirements",
    "or_hospital_charity_care_sliding_scale": "state_community_benefit_requirements",
    "id_hospital_property_tax_exemption_community_benefit": "state_property_tax_exemptions",
    "hi_nonprofit_hospital_tax_exemption": "state_property_tax_exemptions",
    "az_qualifying_healthcare_org_exemption": "state_property_tax_exemptions",
    "ut_nonprofit_hospital_tax_exempt_charity_care": "state_property_tax_exemptions",
    "wa_charity_care_expanded_fpl_thresholds": "state_community_benefit_requirements",
    # transplant_organ
    "az_revised_uniform_anatomical_gift_act": "optnunos_policies_bylaws",
    "ca_transplant_organ_hsc_7150_uaga": "optnunos_policies_bylaws",
    "co_anatomical_gift_act_crs_15_19": "optnunos_policies_bylaws",
    "hi_anatomical_gift_act": "optnunos_policies_bylaws",
    "nv_anatomical_gift_act": "optnunos_policies_bylaws",
    "or_anatomical_gift_act": "optnunos_policies_bylaws",
    "ut_anatomical_gift_act": "optnunos_policies_bylaws",
    "wa_anatomical_gift_act": "optnunos_policies_bylaws",
    "ny_anatomical_gift_act": "optnunos_policies_bylaws",
    "tx_revised_uniform_anatomical_gift_act": "optnunos_policies_bylaws",
    "id_anatomical_gift_hospital_procurement": "opo_conditions_for_coverage",
    "az_donor_registry_requirements": "optnunos_policies_bylaws",
    "id_donor_registry": "optnunos_policies_bylaws",
    "ca_transplant_organ_dmv_registry_integration": "optnunos_policies_bylaws",
    "wa_donor_registry_dol_integration": "optnunos_policies_bylaws",
}


def parse_gap_fill_md(filepath: str) -> List[Dict]:
    """Parse a gap-fill markdown file into requirement dicts.

    Handles three formats produced by research agents:
      Format A (CA, AZ, CO, HI, OR): ## category / #### Title / - **field**: value
      Format B (NV, UT, ID):         ## category / **N. Title** / - **field**: value
      Format C (WA-style):           ## N. `category` / ### Title / - **Field Name**: value
    """
    with open(filepath) as f:
        content = f.read()

    requirements: List[Dict] = []
    current_category: Optional[str] = None
    current_req: Optional[Dict] = None

    def _flush():
        if current_req and current_req.get("regulation_key"):
            requirements.append(current_req)

    for line in content.split("\n"):
        line = line.rstrip()

        # ── Category detection ──────────────────────────────────────────
        # Format A/B: ## telehealth
        cat_a = re.match(r"^##\s+(\w+)\s*$", line)
        if cat_a:
            candidate = cat_a.group(1).lower()
            if candidate in TARGET_CATEGORIES:
                _flush()
                current_req = None
                current_category = candidate
                continue

        # Format C: ## 1. `telehealth` — Label
        cat_c = re.match(r"^##\s+\d+\.\s+`(\w+)`", line)
        if cat_c:
            candidate = cat_c.group(1).lower()
            if candidate in TARGET_CATEGORIES:
                _flush()
                current_req = None
                current_category = candidate
                continue

        if not current_category:
            continue

        # ── Requirement title detection ─────────────────────────────────
        # Format A: #### Title
        title_a = re.match(r"^####\s+(.+)$", line)
        # Format B: **N. Title**  or  **Title**
        title_b = re.match(r"^\*\*(?:\d+\.\s*)?(.+?)\*\*\s*$", line)
        # Format C: ### Title (but NOT ### State-Level ...)
        title_c = re.match(r"^###\s+(.+)$", line)

        title_match = None
        if title_a:
            title_match = title_a.group(1).strip()
        elif title_b:
            title_match = title_b.group(1).strip()
        elif title_c:
            t = title_c.group(1).strip()
            # Skip sub-section headers like "### State-Level (...)"
            if not re.match(r"^State-Level", t, re.IGNORECASE):
                title_match = t

        if title_match:
            # Skip if it looks like a category slug
            if title_match == title_match.lower() and "_" in title_match and " " not in title_match:
                continue
            _flush()
            current_req = {"category": current_category, "title": title_match}
            continue

        # ── Field extraction ────────────────────────────────────────────
        # - **field_name**: value  OR  - **Field Name**: value
        field_match = re.match(r"^-\s+\*\*([^*]+)\*\*:\s*(.+)$", line)
        if field_match and current_req is not None:
            raw_field = field_match.group(1).strip()
            value = field_match.group(2).strip().strip("`")

            # Normalize field name: "Regulation Key" → "regulation_key"
            field = raw_field.lower().replace(" ", "_")

            if field == "regulation_key":
                current_req["regulation_key"] = value
            elif field == "jurisdiction_level":
                current_req["jurisdiction_level"] = value
            elif field == "jurisdiction_name":
                current_req["jurisdiction_name"] = value
            elif field == "title":
                current_req["title"] = value
            elif field == "description":
                current_req["description"] = value
            elif field == "current_value":
                current_req["current_value"] = value
            elif field == "numeric_value":
                try:
                    current_req["numeric_value"] = float(value)
                except (ValueError, TypeError):
                    pass
            elif field == "effective_date":
                # Handle "(amended ...)" suffix
                date_val = re.match(r"(\d{4}-\d{2}-\d{2})", value)
                current_req["effective_date"] = date_val.group(1) if date_val else None
            elif field == "source_url":
                current_req["source_url"] = value
            elif field == "source_name":
                current_req["source_name"] = value
            elif field == "requires_written_policy":
                current_req["requires_written_policy"] = value.lower() in ("true", "yes")
            elif field == "applicable_industries":
                current_req["applicable_industries"] = value
            elif field == "category":
                # Format C puts category as a field — override if valid
                cat_val = value.lower().strip()
                if cat_val in TARGET_CATEGORIES:
                    current_req["category"] = cat_val

    _flush()
    return requirements


def extract_state_code(filepath: str) -> Optional[str]:
    """Extract 2-letter state code from filename like CA_west_healthcare_gaps.md."""
    name = Path(filepath).stem.upper()
    match = re.match(r"^([A-Z]{2})_", name)
    if match and match.group(1) in STATE_NAMES:
        return match.group(1)
    return None


def filter_state_level(reqs: List[Dict], state_code: str) -> List[Dict]:
    """Keep only state-level requirements for target categories.

    Drops national/federal-level entries and non-target categories.
    """
    state_name = STATE_NAMES.get(state_code, "").lower()
    filtered = []
    for r in reqs:
        cat = r.get("category", "")
        if cat not in TARGET_CATEGORIES:
            continue
        level = (r.get("jurisdiction_level") or "").lower()
        jname = (r.get("jurisdiction_name") or "").lower()
        # Keep state-level, or if level isn't set but jurisdiction_name matches the state
        if level == "state" or (level not in ("national", "federal") and jname == state_name):
            filtered.append(r)
    return filtered


async def main():
    parser = argparse.ArgumentParser(description="Batch-ingest gap-fill research into jurisdiction_requirements")
    parser.add_argument("--file", help="Ingest a single file instead of all *_healthcare_gaps.md")
    parser.add_argument("--states", help="Comma-separated state codes to process (e.g., CA,CO,WA)")
    parser.add_argument("--categories", help="Comma-separated categories to limit (e.g., telehealth,cybersecurity)")
    parser.add_argument("--mapped-only", action="store_true", help="Only ingest requirements whose regulation_key maps to a canonical key")
    parser.add_argument("--dry-run", action="store_true", help="Parse and preview, no DB writes")
    args = parser.parse_args()

    scripts_dir = Path(__file__).resolve().parent

    # Discover files
    if args.file:
        files = [Path(args.file)]
    else:
        files = sorted(scripts_dir.glob("*_healthcare_gaps.md"))

    if not files:
        print("No *_healthcare_gaps.md files found.")
        return

    # Optional filters
    state_filter = set(args.states.upper().split(",")) if args.states else None
    cat_filter = set(args.categories.lower().split(",")) if args.categories else None

    # Parse all files
    all_state_reqs: Dict[str, List[Dict]] = {}  # state_code → [reqs]
    for f in files:
        state_code = extract_state_code(str(f))
        if not state_code:
            print(f"  SKIP {f.name}: can't extract state code from filename")
            continue
        if state_filter and state_code not in state_filter:
            continue

        reqs = parse_gap_fill_md(str(f))
        state_reqs = filter_state_level(reqs, state_code)

        if cat_filter:
            state_reqs = [r for r in state_reqs if r.get("category") in cat_filter]

        # Remap regulation_keys to canonical keys
        for r in state_reqs:
            rk = r.get("regulation_key", "")
            if rk in CANONICAL_KEY_MAP:
                r["regulation_key"] = CANONICAL_KEY_MAP[rk]

        # --mapped-only: drop requirements whose regulation_key is NOT a canonical key
        if args.mapped_only:
            from app.core.compliance_registry import EXPECTED_REGULATION_KEYS
            def _is_canonical(r):
                rk = r.get("regulation_key", "")
                cat = r.get("category", "")
                known = EXPECTED_REGULATION_KEYS.get(cat, frozenset())
                return rk in known
            before = len(state_reqs)
            state_reqs = [r for r in state_reqs if _is_canonical(r)]
            dropped = before - len(state_reqs)
            if dropped:
                print(f"    ({dropped} unmapped requirements skipped)")

        # Merge duplicates: when multiple research entries map to the same
        # canonical key, merge descriptions and pick best metadata.
        merged: Dict[str, Dict] = {}
        for r in state_reqs:
            merge_key = f"{r.get('category')}:{r.get('regulation_key')}"
            if merge_key not in merged:
                merged[merge_key] = dict(r)
            else:
                existing = merged[merge_key]
                # Append description
                old_desc = existing.get("description") or ""
                new_desc = r.get("description") or ""
                if new_desc and new_desc not in old_desc:
                    existing["description"] = f"{old_desc}\n\n---\n\n{new_desc}".strip()
                # Append title detail
                old_title = existing.get("title") or ""
                new_title = r.get("title") or ""
                if new_title and new_title != old_title and len(old_title) + len(new_title) < 490:
                    existing["title"] = f"{old_title}; {new_title}"
                # Pick most recent effective_date
                if r.get("effective_date") and (not existing.get("effective_date") or r["effective_date"] > existing["effective_date"]):
                    existing["effective_date"] = r["effective_date"]
                # Combine source info
                old_src = existing.get("source_name") or ""
                new_src = r.get("source_name") or ""
                if new_src and new_src not in old_src:
                    existing["source_name"] = f"{old_src}; {new_src}"[:100]
                # requires_written_policy: true wins
                if r.get("requires_written_policy"):
                    existing["requires_written_policy"] = True
        state_reqs = list(merged.values())

        if state_reqs:
            all_state_reqs[state_code] = state_reqs
            print(f"  {state_code}: {len(state_reqs)} state-level requirements from {f.name}")
        else:
            print(f"  {state_code}: 0 parseable state-level requirements from {f.name}")

    total_reqs = sum(len(v) for v in all_state_reqs.values())
    print(f"\nTotal: {total_reqs} requirements across {len(all_state_reqs)} states")

    if not all_state_reqs:
        print("Nothing to ingest.")
        return

    # Show category breakdown
    cat_counts: Dict[str, int] = {}
    for reqs in all_state_reqs.values():
        for r in reqs:
            c = r.get("category", "?")
            cat_counts[c] = cat_counts.get(c, 0) + 1
    for c, n in sorted(cat_counts.items()):
        print(f"    {c}: {n}")

    if args.dry_run:
        print("\n[DRY RUN] Would insert:")
        for state, reqs in sorted(all_state_reqs.items()):
            print(f"\n  {state} ({STATE_NAMES[state]}):")
            for r in reqs:
                print(f"    {r['category']}:{r.get('regulation_key','?')} — {r.get('title','?')}")
        return

    # ── Database ingestion ──────────────────────────────────────────────────
    import hashlib
    from datetime import date as dt_date

    from app.config import load_settings
    from app.database import init_pool, close_pool, get_pool
    from app.core.services.compliance_service import _compute_requirement_key

    settings = load_settings()
    await init_pool(settings.database_url)
    pool = await get_pool()

    # Fields we compare for change detection
    TRACKED_FIELDS = ["title", "description", "current_value", "effective_date", "source_url", "source_name"]

    def _compute_hash(r: Dict) -> str:
        """Content hash for quick change detection."""
        parts = [str(r.get(f) or "") for f in TRACKED_FIELDS]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]

    try:
        async with pool.acquire() as conn:
            # Pre-fetch category_id map
            cat_rows = await conn.fetch("SELECT id, slug FROM compliance_categories")
            cat_id_map = {r["slug"]: r["id"] for r in cat_rows}

            stats = {"new": 0, "changed": 0, "unchanged": 0, "skipped": 0}

            for state_code, reqs in sorted(all_state_reqs.items()):
                state_name = STATE_NAMES[state_code]

                # Target the STATE-LEVEL jurisdiction (city IS NULL)
                state_jrow = await conn.fetchrow(
                    "SELECT id FROM jurisdictions WHERE state = $1 AND city IS NULL AND country_code = 'US'",
                    state_code,
                )
                if not state_jrow:
                    print(f"\n  {state_code}: No state-level jurisdiction in DB — skipping")
                    continue

                jurisdiction_id = state_jrow["id"]
                print(f"\n  {state_code} ({state_name}) → state jurisdiction {str(jurisdiction_id)[:8]}...")

                for r in reqs:
                    category = r.get("category", "")
                    category_id = cat_id_map.get(category)
                    if not category_id:
                        print(f"    SKIP {category}:{r.get('regulation_key')}: unknown category slug")
                        stats["skipped"] += 1
                        continue

                    req_key = _compute_requirement_key(r)

                    effective_date = None
                    if r.get("effective_date"):
                        try:
                            effective_date = dt_date.fromisoformat(r["effective_date"])
                        except (ValueError, TypeError):
                            pass

                    new_title = r.get("title", "Untitled")
                    new_desc = r.get("description")
                    new_value = r.get("current_value")
                    new_source_url = r.get("source_url")
                    new_source_name = r.get("source_name")
                    new_hash = _compute_hash(r)

                    # ── Read existing row ────────────────────────────────
                    existing = await conn.fetchrow(
                        "SELECT id, title, description, current_value, effective_date, "
                        "source_url, source_name, fetch_hash FROM jurisdiction_requirements "
                        "WHERE jurisdiction_id = $1 AND requirement_key = $2",
                        jurisdiction_id, req_key,
                    )

                    try:
                        if existing is None:
                            # ── NEW: insert ──────────────────────────────
                            await conn.execute("""
                                INSERT INTO jurisdiction_requirements
                                    (jurisdiction_id, requirement_key, category, category_id,
                                     jurisdiction_level, jurisdiction_name, title, description,
                                     current_value, numeric_value, source_url, source_name,
                                     effective_date, requires_written_policy, regulation_key,
                                     change_status, fetch_hash)
                                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,'new',$16)
                            """,
                                jurisdiction_id, req_key, category, category_id,
                                r.get("jurisdiction_level", "state"),
                                r.get("jurisdiction_name", state_name),
                                new_title, new_desc, new_value,
                                r.get("numeric_value"),
                                new_source_url, new_source_name,
                                effective_date,
                                r.get("requires_written_policy", False),
                                r.get("regulation_key"),
                                new_hash,
                            )
                            stats["new"] += 1
                            print(f"    NEW  {category}:{r.get('regulation_key')}")

                        elif existing["fetch_hash"] == new_hash:
                            # ── UNCHANGED: just verify ───────────────────
                            await conn.execute(
                                "UPDATE jurisdiction_requirements SET last_verified_at = NOW(), "
                                "change_status = 'unchanged' WHERE id = $1",
                                existing["id"],
                            )
                            stats["unchanged"] += 1

                        else:
                            # ── CHANGED: track diff, update ──────────────
                            old = dict(existing)

                            # Write policy_change_log entries for each changed field
                            for field in TRACKED_FIELDS:
                                old_val = str(old.get(field) or "")
                                new_val = str(r.get(field) or "")
                                if field == "effective_date":
                                    new_val = str(effective_date or "")
                                if old_val != new_val:
                                    await conn.execute(
                                        "INSERT INTO policy_change_log "
                                        "(requirement_id, field_changed, old_value, new_value, change_source) "
                                        "VALUES ($1, $2, $3, $4, 'ai_fetch')",
                                        existing["id"], field,
                                        old_val[:2000] if old_val else None,
                                        new_val[:2000] if new_val else None,
                                    )

                            # Update the row with new data, preserving old in previous_*
                            await conn.execute("""
                                UPDATE jurisdiction_requirements SET
                                    title = $2, description = $3,
                                    current_value = $4, source_url = $5, source_name = $6,
                                    effective_date = $7,
                                    previous_value = current_value,
                                    previous_description = description,
                                    change_status = 'changed',
                                    last_changed_at = NOW(),
                                    last_verified_at = NOW(),
                                    updated_at = NOW(),
                                    fetch_hash = $8,
                                    requires_written_policy = $9,
                                    regulation_key = $10
                                WHERE id = $1
                            """,
                                existing["id"],
                                new_title, new_desc, new_value,
                                new_source_url, new_source_name,
                                effective_date, new_hash,
                                r.get("requires_written_policy", False),
                                r.get("regulation_key"),
                            )
                            stats["changed"] += 1
                            print(f"    CHG  {category}:{r.get('regulation_key')}")

                    except Exception as e:
                        print(f"    ERR  {category}:{r.get('regulation_key')}: {e}")
                        stats["skipped"] += 1

                # Update requirement_count
                count = await conn.fetchval(
                    "SELECT count(*) FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                    jurisdiction_id,
                )
                await conn.execute(
                    "UPDATE jurisdictions SET requirement_count = $1, last_verified_at = NOW(), updated_at = NOW() WHERE id = $2",
                    count, jurisdiction_id,
                )

                # Link to regulation_key_definitions
                await conn.execute("""
                    UPDATE jurisdiction_requirements jr
                    SET key_definition_id = rkd.id
                    FROM regulation_key_definitions rkd, jurisdictions j
                    WHERE j.id = jr.jurisdiction_id
                      AND jr.jurisdiction_id = $1
                      AND jr.category = rkd.category_slug
                      AND jr.regulation_key = rkd.key
                      AND jr.key_definition_id IS NULL
                      AND (rkd.applicable_countries IS NULL
                           OR j.country_code = ANY(rkd.applicable_countries))
                """, jurisdiction_id)

            print(f"\n{'='*60}")
            print(f"NEW:       {stats['new']}")
            print(f"CHANGED:   {stats['changed']}")
            print(f"UNCHANGED: {stats['unchanged']}")
            print(f"SKIPPED:   {stats['skipped']}")

    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
