"""Master-admin onboarding wizard — Gemini scope expansion + SQL bank reconciliation.

Two public functions:

* ``expand_scope(basics, locations) -> dict`` — single Gemini call (JSON-strict
  response_schema). Industry + specialty + per-location facility attrs in,
  ``AIScope`` shape out (compliance_categories, certifications, licenses,
  applicable_jurisdictions).

* ``map_to_bank(ai_scope, conn) -> dict`` — pure SQL. Resolves AI-emitted
  category slugs + (state, county, city) tuples against the shared
  ``jurisdiction_requirements`` bank. Returns
  ``{existing, missing, ambiguous}`` lists. No Gemini.

Plus the ``INDUSTRY_SPECIALTIES`` controlled vocab — feeds the Step 1
typeahead so the admin can't free-type three variants of "cardiology".
"""

import asyncio
import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Controlled vocab ────────────────────────────────────────────────────
#
# Step 1 UI uses this for an industry+specialty typeahead. The Gemini
# expand call ALSO sees these as soft hints (specialty narrows the
# applicable categories without forcing the AI into a closed enum).
INDUSTRY_SPECIALTIES: dict[str, list[str]] = {
    "healthcare": [
        "primary_care", "cardiology", "oncology", "pediatrics", "obgyn",
        "dermatology", "psychiatry", "behavioral_health", "dental",
        "urgent_care", "rehabilitation", "home_health", "hospice",
        "laboratory", "imaging", "surgery_center",
    ],
    "hospitality": [
        "full_service_restaurant", "fast_casual", "quick_service",
        "bar", "hotel", "motel", "bed_and_breakfast", "catering",
        "food_truck", "brewery", "winery",
    ],
    "manufacturing": [
        "food_processing", "chemical", "pharmaceutical", "biotech",
        "metal_fabrication", "automotive", "electronics", "textile",
        "plastics", "general_assembly",
    ],
    "retail": [
        "grocery", "convenience", "apparel", "electronics", "auto_parts",
        "pharmacy_retail", "specialty",
    ],
    "construction": [
        "residential", "commercial", "specialty_trade", "highway_heavy",
        "electrical", "plumbing", "hvac", "roofing",
    ],
    "professional_services": [
        "legal", "accounting", "consulting", "engineering", "architecture",
        "marketing_agency", "staffing",
    ],
    "tech": [
        "saas", "fintech", "biotech_software", "ai_ml", "ecommerce_platform",
        "hardware", "gaming",
    ],
    "agriculture": [
        "crop_production", "livestock", "dairy", "poultry", "aquaculture",
        "viticulture",
    ],
    "transportation": [
        "trucking", "warehousing", "logistics", "delivery_last_mile",
        "rideshare", "courier",
    ],
    "education": [
        "k12_public", "k12_private", "higher_ed", "early_childhood",
        "trade_school", "tutoring",
    ],
    "nonprofit": [
        "social_services", "advocacy", "religious", "arts",
    ],
    "general": [],
}


GEMINI_EXPAND_TIMEOUT_SECONDS = 150  # was 90; sat between GAP_CHECK_TIMEOUT=120 and SECTION_EXTRACT_TIMEOUT=180
GEMINI_GAPCHECK_TIMEOUT_SECONDS = 60


# ── Few-shot examples for the expand prompt ────────────────────────────
#
# Three deliberately different business shapes prime the model so it
# generalizes instead of pattern-matching only to common industries. Each
# example walks from input → expected output, using realistic slugs even
# when the slug doesn't yet exist in the bank (the bank filter in
# expand_scope strips unknown categories at the end). The point of the
# examples is to shape the SHAPE — the AI then maps to whatever slugs
# the live bank actually offers.
FEW_SHOT_EXAMPLES: list[dict[str, Any]] = [
    {
        "input": {
            "business_name": "ProTherapy Sports Medicine",
            "industry": "healthcare",
            "specialty": "rehabilitation",
            "description": (
                "Outpatient sports medicine clinic. Staff: 3 sports-medicine MDs, "
                "8 physical therapists, 4 athletic trainers, 2 medical assistants. "
                "In-house CLIA-waived lab for rapid strep + drug screens. Single "
                "location in Los Angeles, CA. Treats high-school athletes through "
                "pro players."
            ),
            "location": {"state": "CA", "county": "Los Angeles", "city": "Los Angeles"},
        },
        "output": {
            "naics_sector": "62",
            "compliance_categories": [
                {"category_slug": "hipaa_privacy", "scope": "federal", "reason": "PHI handling"},
                {"category_slug": "osha_general", "scope": "federal", "reason": "general duty clause"},
                {"category_slug": "osha_bloodborne", "scope": "federal", "reason": "clinical specimen handling"},
                {"category_slug": "ada_accessibility", "scope": "federal", "reason": "outpatient public access"},
                {"category_slug": "ca_medical_waste", "scope": "state", "reason": "CA Medical Waste Management Act"},
                {"category_slug": "ca_workers_comp", "scope": "state", "reason": "CA WC mandate"},
                {"category_slug": "ca_sick_leave", "scope": "state", "reason": "CA Healthy Workplaces Healthy Families Act"},
                {"category_slug": "la_business_tax", "scope": "city", "reason": "LA business tax registration"},
            ],
            "required_certifications": [
                {"slug": "clia_waived", "name": "CLIA Certificate of Waiver", "issuing_authority": "CMS", "scope_level": "federal", "renewal_period_months": 24},
                {"slug": "atc_boc", "name": "Athletic Trainer (BOC)", "issuing_authority": "Board of Certification", "scope_level": "specialty", "renewal_period_months": 24},
                {"slug": "bls_aha", "name": "Basic Life Support (AHA)", "issuing_authority": "American Heart Association", "scope_level": "specialty", "renewal_period_months": 24},
            ],
            "required_licenses": [
                {"slug": "ca_medical_board", "name": "CA Medical Board Physician License", "issuing_authority": "Medical Board of California", "scope_level": "state", "renewal_period_months": 24},
                {"slug": "ca_pt_board", "name": "CA Physical Therapy License", "issuing_authority": "Physical Therapy Board of California", "scope_level": "state", "renewal_period_months": 24},
                {"slug": "ca_athletic_trainer_voluntary", "name": "CA Athletic Trainer (voluntary, where required)", "issuing_authority": "CA Department of Consumer Affairs", "scope_level": "state", "renewal_period_months": 24},
                {"slug": "la_business_license", "name": "LA City Business License", "issuing_authority": "LA Office of Finance", "scope_level": "specialty", "renewal_period_months": 12},
            ],
            "applicable_jurisdictions": [
                {"state": None, "county": None, "city": None},
                {"state": "CA", "county": None, "city": None},
                {"state": "CA", "county": "Los Angeles", "city": "Los Angeles"},
            ],
        },
    },
    {
        "input": {
            "business_name": "Helix Biotech R&D",
            "industry": "manufacturing",
            "specialty": "biotech",
            "description": (
                "BSL-2 wet lab. 12 FTEs + 8 rotational UCSF grad students on F-1/J-1 "
                "visas. Handles human tissue samples and de-identified clinical "
                "specimens. Ships frozen samples to partner labs. No animal work. "
                "Late-night work allowed; no minors. SF, CA."
            ),
            "location": {"state": "CA", "county": "San Francisco", "city": "San Francisco"},
        },
        "output": {
            "naics_sector": "54",
            "compliance_categories": [
                {"category_slug": "osha_general", "scope": "federal", "reason": "general duty"},
                {"category_slug": "osha_bloodborne", "scope": "federal", "reason": "human tissue + specimen handling"},
                {"category_slug": "osha_lab_standard", "scope": "federal", "reason": "29 CFR 1910.1450 lab chemical hygiene"},
                {"category_slug": "epa_hazardous_waste", "scope": "federal", "reason": "RCRA Subtitle C waste streams"},
                {"category_slug": "dot_hazmat_shipping", "scope": "federal", "reason": "IATA/DOT Class 6.2 biological substance shipments"},
                {"category_slug": "hipaa_privacy", "scope": "federal", "reason": "de-identified clinical specimens still subject to HIPAA-aligned handling"},
                {"category_slug": "irb_protocols", "scope": "federal", "reason": "human subjects research oversight"},
                {"category_slug": "ca_hazardous_waste", "scope": "state", "reason": "CA DTSC stricter than RCRA"},
                {"category_slug": "ca_medical_waste", "scope": "state", "reason": "biohazard waste"},
                {"category_slug": "ca_sick_leave", "scope": "state", "reason": "CA HWHFA"},
                {"category_slug": "sf_gross_receipts", "scope": "city", "reason": "SF business tax"},
                {"category_slug": "sf_health_care_security", "scope": "city", "reason": "SF HCSO employer mandate"},
            ],
            "required_certifications": [
                {"slug": "biosafety_officer", "name": "Designated Biosafety Officer", "issuing_authority": "Institutional", "scope_level": "specialty", "renewal_period_months": 12},
                {"slug": "iata_dgr", "name": "IATA Dangerous Goods Regulations Training", "issuing_authority": "IATA", "scope_level": "federal", "renewal_period_months": 24},
                {"slug": "bbp_training", "name": "OSHA Bloodborne Pathogens Training", "issuing_authority": "OSHA-compliant provider", "scope_level": "federal", "renewal_period_months": 12},
            ],
            "required_licenses": [
                {"slug": "ca_medical_waste_generator", "name": "CA Medical Waste Generator Registration", "issuing_authority": "CA Dept. of Public Health", "scope_level": "state", "renewal_period_months": 12},
                {"slug": "ca_hazardous_waste_generator", "name": "CA Hazardous Waste Generator ID", "issuing_authority": "CA DTSC", "scope_level": "state", "renewal_period_months": None},
                {"slug": "sf_business_registration", "name": "SF Business Registration Certificate", "issuing_authority": "SF Treasurer", "scope_level": "specialty", "renewal_period_months": 12},
            ],
            "applicable_jurisdictions": [
                {"state": None, "county": None, "city": None},
                {"state": "CA", "county": None, "city": None},
                {"state": "CA", "county": "San Francisco", "city": "San Francisco"},
            ],
        },
    },
    {
        "input": {
            "business_name": "Stagger Inn",
            "industry": "hospitality",
            "specialty": "full_service_restaurant",
            "description": (
                "Full-service American gastropub + bar. 22 FTEs (tipped servers, "
                "bartenders, kitchen staff). Live music Friday/Saturday until 2am. "
                "Outdoor patio with propane heaters in winter. Cash + card. "
                "Single location in Austin, TX (Travis County)."
            ),
            "location": {"state": "TX", "county": "Travis", "city": "Austin"},
        },
        "output": {
            "naics_sector": "72",
            "compliance_categories": [
                {"category_slug": "osha_general", "scope": "federal", "reason": "general duty"},
                {"category_slug": "flsa_tipped", "scope": "federal", "reason": "FLSA tip credit, dual-jobs rule"},
                {"category_slug": "ada_accessibility", "scope": "federal", "reason": "public accommodation"},
                {"category_slug": "pci_dss", "scope": "federal", "reason": "card payment acceptance"},
                {"category_slug": "tx_workers_comp", "scope": "state", "reason": "TX opt-in WC framework"},
                {"category_slug": "tx_minimum_wage", "scope": "state", "reason": "TX wage rules"},
                {"category_slug": "tx_alcoholic_beverage", "scope": "state", "reason": "TABC permit + server training"},
                {"category_slug": "travis_food_permit", "scope": "county", "reason": "Travis County food handler establishment permit"},
                {"category_slug": "austin_late_hours_permit", "scope": "city", "reason": "Austin late-hours operating permit + sound ordinance"},
                {"category_slug": "austin_fire_code_patio", "scope": "city", "reason": "Austin Fire Code propane heater rules"},
            ],
            "required_certifications": [
                {"slug": "tx_food_handler", "name": "TX Accredited Food Handler", "issuing_authority": "TX DSHS", "scope_level": "state", "renewal_period_months": 24},
                {"slug": "tx_food_manager", "name": "TX Certified Food Manager", "issuing_authority": "TX DSHS", "scope_level": "state", "renewal_period_months": 60},
                {"slug": "tabc_seller_server", "name": "TABC Seller-Server Certification", "issuing_authority": "TX Alcoholic Beverage Commission", "scope_level": "state", "renewal_period_months": 24},
            ],
            "required_licenses": [
                {"slug": "tabc_mb_permit", "name": "TABC Mixed Beverage Permit", "issuing_authority": "TX Alcoholic Beverage Commission", "scope_level": "state", "renewal_period_months": 24},
                {"slug": "austin_business_license", "name": "Austin Business License", "issuing_authority": "City of Austin", "scope_level": "specialty", "renewal_period_months": 12},
                {"slug": "austin_outdoor_music_permit", "name": "Austin Outdoor Music Venue Permit", "issuing_authority": "City of Austin", "scope_level": "specialty", "renewal_period_months": 12},
            ],
            "applicable_jurisdictions": [
                {"state": None, "county": None, "city": None},
                {"state": "TX", "county": None, "city": None},
                {"state": "TX", "county": "Travis", "city": None},
                {"state": "TX", "county": "Travis", "city": "Austin"},
            ],
        },
    },
]


# ── Gemini call ─────────────────────────────────────────────────────────

def _gemini_client():
    """Build a google-genai client. Mirrors handbook_audit._gemini_client.

    Worker process now bootstraps load_settings() at worker_process_init
    (see celery_app.py), and FastAPI bootstraps at lifespan, so
    get_settings() is safe here from either context. Per-task fallback
    kept for defense-in-depth.
    """
    from google import genai
    from app.config import get_settings, load_settings

    try:
        settings = get_settings()
    except RuntimeError:
        settings = load_settings()

    if settings.use_vertex:
        return genai.Client(
            vertexai=True,
            project=settings.vertex_project,
            location=settings.vertex_location or "us-central1",
        )
    api_key = os.getenv("GEMINI_API_KEY") or settings.gemini_api_key
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")
    return genai.Client(api_key=api_key)


def _strip_json_fence(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


async def _fetch_category_slugs(conn) -> list[str]:
    """Live enum: the AI may only emit categories that exist in the bank."""
    rows = await conn.fetch("SELECT slug FROM compliance_categories ORDER BY slug")
    return [r["slug"] for r in rows]


async def expand_scope(
    *,
    basics: dict[str, Any],
    locations: list[dict[str, Any]],
    conn,
) -> dict[str, Any]:
    """Run Gemini to expand industry+specialty+locations into a scope manifest.

    Returns the raw AIScope shape (dict). Caller is responsible for
    validating against the ``AIScope`` Pydantic model and persisting to
    ``onboarding_sessions.ai_scope``.

    ``conn`` is an asyncpg connection — used only to fetch the live
    ``compliance_categories.slug`` enum (no writes).
    """
    industry = (basics.get("industry") or "general").strip()
    specialty = (basics.get("specialty") or "").strip() or None
    business_name = (basics.get("business_name") or "").strip()
    description = (basics.get("description") or "").strip() or None

    category_slugs = await _fetch_category_slugs(conn)
    if not category_slugs:
        # Bank not seeded. Fall back to empty scope — caller surfaces a
        # 503-ish error to admin so they don't blame the AI.
        return {
            "naics_sector": None,
            "compliance_categories": [],
            "required_certifications": [],
            "required_licenses": [],
            "applicable_jurisdictions": [],
            "_warning": "compliance_categories table is empty; seed before running scope",
        }

    locations_yaml_lines: list[str] = []
    for idx, loc in enumerate(locations or [], start=1):
        attrs = loc.get("facility_attributes") or {}
        attrs_blob = ", ".join(f"{k}={v}" for k, v in attrs.items()) or "—"
        locations_yaml_lines.append(
            f"- #{idx} {loc.get('city') or '?'}, {loc.get('state') or '?'} "
            f"(county={loc.get('county') or '—'}, attrs={attrs_blob})"
        )
    locations_yaml = "\n".join(locations_yaml_lines) or "- (no locations supplied — federal scope only)"

    description_block = (
        f"\nCOMPANY DETAILS (most authoritative — read carefully):\n  {description}\n"
        if description
        else ""
    )

    few_shot_block = (
        "WORKED EXAMPLES (study these shapes carefully; your output should look like these):\n"
        + json.dumps(FEW_SHOT_EXAMPLES, indent=2)
        + "\n\n"
    )

    prompt = (
        f"You are scoping a NEW BUSINESS called \"{business_name}\" for compliance tracking.\n\n"
        f"{few_shot_block}"
        f"INPUT:\n"
        f"  Industry: {industry}\n"
        f"  Specialty: {specialty or '(none)'}\n"
        f"  Locations:\n{locations_yaml}\n"
        f"{description_block}\n"
        f"For each location, list the compliance categories, required certifications,\n"
        f"and required licenses that THIS business must track. Distinguish federal,\n"
        f"state, county, and city scope. Be specific: a 'cardiology practice in\n"
        f"Travis County, TX' is NOT the same scope as a 'general medical practice\n"
        f"in California'.\n\n"
        f"CRITICAL — surface the non-obvious:\n"
        f"The HR admin running this wizard may not know which compliance buckets apply.\n"
        f"Treat COMPANY DETAILS (when supplied) as the most authoritative input.\n"
        f"Look for operational signals the admin mentioned and add the corresponding\n"
        f"requirements even when the industry/specialty alone wouldn't suggest them:\n"
        f"  - Grad students / research staff → student worker visa rules, IRB protocols,\n"
        f"    institutional bloodborne pathogen training, NIH guidelines if federally\n"
        f"    funded research is implied.\n"
        f"  - BSL-2 / BSL-3 / wet lab work → OSHA bloodborne pathogens, hazardous\n"
        f"    materials transport, biosafety committee oversight.\n"
        f"  - Tissue / specimen handling → HIPAA, IRB consent, hazardous waste manifests.\n"
        f"  - Minors / under-18 staff → state child labor permits, hour limits.\n"
        f"  - Late-night / 24-hour operations → state late-night liquor permits,\n"
        f"    security requirements, OSHA fatigue management.\n"
        f"  - Food handling on premises → state food handler permits, allergen disclosure.\n"
        f"  - Tipped employees → state tip credit rules, dual jobs rule.\n"
        f"  - Contractors / 1099 → ABC test, IRS classification, state misclassification audits.\n"
        f"  - Multi-state remote workers → wage theft prevention notices in each state,\n"
        f"    tax nexus, workers' comp coverage per state.\n"
        f"  - Cash handling / payment cards → PCI-DSS scope, robbery prevention.\n"
        f"  - Driving / fleet → DOT, CDL, commercial auto insurance.\n"
        f"  - Hazardous chemicals / OSHA PSM thresholds → process safety management.\n"
        f"This list is illustrative — read the description and extrapolate similarly.\n\n"
        f"Rules:\n"
        f"- compliance_categories.category_slug MUST be from this controlled list:\n"
        f"  {json.dumps(category_slugs)}\n"
        f"- required_certifications + required_licenses: pick well-known names.\n"
        f"  Skip if speculative. Provide stable slug + display name.\n"
        f"- applicable_jurisdictions: emit as {{state, county, city}} tuples. Use\n"
        f"  ISO state codes (CA, TX). county/city null when scope is broader.\n"
        f"- Only list jurisdictions whose laws actually bind this business.\n\n"
        f"Return ONLY JSON of this exact shape, no prose:\n"
        f'{{"naics_sector": "string or null",\n'
        f' "compliance_categories": [\n'
        f'   {{"category_slug": "string", "scope": "federal|state|county|city", "reason": "string"}}\n'
        f' ],\n'
        f' "required_certifications": [\n'
        f'   {{"slug": "string", "name": "string", "issuing_authority": "string or null", '
        f'"scope_level": "federal|state|specialty", "renewal_period_months": int_or_null}}\n'
        f' ],\n'
        f' "required_licenses": [\n'
        f'   {{"slug": "string", "name": "string", "issuing_authority": "string or null", '
        f'"scope_level": "federal|state|specialty", "renewal_period_months": int_or_null}}\n'
        f' ],\n'
        f' "applicable_jurisdictions": [\n'
        f'   {{"state": "CA or null", "county": "string or null", "city": "string or null"}}\n'
        f' ]\n'
        f'}}'
    )

    try:
        client = _gemini_client()
    except Exception as exc:
        logger.exception("Gemini client init failed for scope expansion: %s", exc)
        raise

    model_name = os.getenv("ONBOARDING_SCOPE_MODEL", "gemini-2.5-flash")
    try:
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
            ),
            timeout=GEMINI_EXPAND_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.exception("Gemini scope expansion call failed: %s", exc)
        raise

    raw = (getattr(response, "text", None) or "").strip()
    try:
        parsed = json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError:
        logger.warning("Scope expansion returned non-JSON: %s", raw[:200])
        return {
            "naics_sector": None,
            "compliance_categories": [],
            "required_certifications": [],
            "required_licenses": [],
            "applicable_jurisdictions": [],
            "_warning": "Gemini returned non-JSON; admin should re-run expand",
        }
    if not isinstance(parsed, dict):
        return {
            "naics_sector": None,
            "compliance_categories": [],
            "required_certifications": [],
            "required_licenses": [],
            "applicable_jurisdictions": [],
            "_warning": "Gemini returned non-object root; admin should re-run expand",
        }

    # Defensive: filter category_slug to live enum (drop hallucinations).
    cats = parsed.get("compliance_categories") or []
    live = set(category_slugs)
    parsed["compliance_categories"] = [
        c for c in cats
        if isinstance(c, dict) and c.get("category_slug") in live
    ]
    return parsed


# ── Bank reconciliation (pure SQL) ──────────────────────────────────────

async def map_to_bank(
    ai_scope: dict[str, Any],
    conn,
) -> dict[str, list[dict[str, Any]]]:
    """Resolve AI-emitted scope against ``jurisdiction_requirements``.

    Returns ``{existing, missing, ambiguous}``:

    * ``existing``: rows with a confident bank match. Each row is a dict
      ready to be persisted as a ``company_compliance_scope`` insert.
    * ``missing``: AI scope items with no bank row — admin chooses which
      to research via the dispatch endpoint.
    * ``ambiguous``: AI jurisdiction tuples that matched >1 bank row
      (e.g. "Springfield" — multiple states). Admin disambiguates.
    """
    categories = ai_scope.get("compliance_categories") or []
    jurisdictions = ai_scope.get("applicable_jurisdictions") or []
    if not categories:
        return {"existing": [], "missing": [], "ambiguous": []}

    category_slugs = [c.get("category_slug") for c in categories if isinstance(c, dict) and c.get("category_slug")]
    if not category_slugs:
        return {"existing": [], "missing": [], "ambiguous": []}

    # Resolve categories to ids in one query.
    cat_rows = await conn.fetch(
        "SELECT id, slug FROM compliance_categories WHERE slug = ANY($1::text[])",
        category_slugs,
    )
    cat_id_by_slug: dict[str, str] = {r["slug"]: str(r["id"]) for r in cat_rows}

    # Resolve jurisdictions: walk (state, county, city) tuples.
    # state-only: jurisdictions.code matches state OR jurisdictions.name matches state code at level='state'.
    # county: parent state has a child at level='county' matching county name.
    # city: parent county has a child at level='city' matching city name.
    juris_resolutions: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    for j in jurisdictions:
        if not isinstance(j, dict):
            continue
        state = (j.get("state") or "").strip() or None
        county = (j.get("county") or "").strip() or None
        city = (j.get("city") or "").strip() or None

        if state is None and county is None and city is None:
            # Federal: no jurisdiction row needed; scope_level='federal'.
            juris_resolutions.append({
                "scope_level": "federal",
                "jurisdiction_id": None,
                "state": None, "county": None, "city": None,
            })
            continue

        if state is None:
            # County/city without state — can't disambiguate; skip.
            ambiguous.append({
                "candidates": [],
                "why": f"county/city '{county or city}' with no state",
            })
            continue

        if county is None and city is None:
            row = await conn.fetchrow(
                "SELECT id FROM jurisdictions WHERE level='state' AND code = $1 LIMIT 2",
                state.upper(),
            )
            juris_resolutions.append({
                "scope_level": "state",
                "jurisdiction_id": str(row["id"]) if row else None,
                "state": state.upper(), "county": None, "city": None,
            })
            continue

        if city is None and county is not None:
            rows = await conn.fetch(
                """
                SELECT j.id
                FROM jurisdictions j
                JOIN jurisdictions p ON j.parent_id = p.id
                WHERE j.level='county' AND j.name ILIKE $1 AND p.code = $2
                """,
                county, state.upper(),
            )
            if len(rows) > 1:
                ambiguous.append({
                    "candidates": [{"jurisdiction_id": str(r["id"])} for r in rows],
                    "why": f"county '{county}' matched {len(rows)} rows in {state}",
                })
                continue
            juris_resolutions.append({
                "scope_level": "county",
                "jurisdiction_id": str(rows[0]["id"]) if rows else None,
                "state": state.upper(), "county": county, "city": None,
            })
            continue

        # city (with state, optional county)
        if city is not None:
            rows = await conn.fetch(
                """
                SELECT j.id
                FROM jurisdictions j
                JOIN jurisdictions p ON j.parent_id = p.id
                JOIN jurisdictions gp ON p.parent_id = gp.id
                WHERE j.level='city' AND j.name ILIKE $1 AND gp.code = $2
                """,
                city, state.upper(),
            )
            if len(rows) > 1:
                ambiguous.append({
                    "candidates": [{"jurisdiction_id": str(r["id"])} for r in rows],
                    "why": f"city '{city}' matched {len(rows)} rows in {state}",
                })
                continue
            juris_resolutions.append({
                "scope_level": "city",
                "jurisdiction_id": str(rows[0]["id"]) if rows else None,
                "state": state.upper(), "county": county, "city": city,
            })

    # For each (category, jurisdiction) pair, look up jurisdiction_requirements.
    existing: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for cat in categories:
        if not isinstance(cat, dict):
            continue
        slug = cat.get("category_slug")
        scope = (cat.get("scope") or "federal").strip().lower()
        cat_id = cat_id_by_slug.get(slug)
        if not cat_id:
            missing.append({
                "category_slug": slug,
                "scope_level": scope,
                "state": None, "county": None, "city": None,
                "reason": cat.get("reason") or "category slug not in bank",
            })
            continue
        # Match each resolved jurisdiction that fits this category's scope_level.
        matched_any = False
        for jres in juris_resolutions:
            if scope != jres["scope_level"]:
                continue
            rows = await conn.fetch(
                """
                SELECT jr.id, jr.canonical_key, jr.title
                FROM jurisdiction_requirements jr
                WHERE jr.category_id = $1
                  AND jr.status = 'active'
                  AND (
                    $2::uuid IS NULL OR jr.jurisdiction_id = $2::uuid
                  )
                ORDER BY jr.title
                """,
                cat_id, jres["jurisdiction_id"],
            )
            if rows:
                for r in rows:
                    existing.append({
                        "requirement_id": str(r["id"]),
                        "category_slug": slug,
                        "canonical_key": r["canonical_key"],
                        "title": r["title"],
                        "scope_level": jres["scope_level"],
                        "state": jres["state"],
                        "county": jres["county"],
                        "city": jres["city"],
                    })
                matched_any = True
            else:
                missing.append({
                    "category_slug": slug,
                    "scope_level": scope,
                    "state": jres["state"],
                    "county": jres["county"],
                    "city": jres["city"],
                    "reason": cat.get("reason") or "no bank row for this category+jurisdiction",
                })
        if not matched_any and not juris_resolutions:
            # Category but no jurisdiction context at all — mark missing.
            missing.append({
                "category_slug": slug,
                "scope_level": scope,
                "state": None, "county": None, "city": None,
                "reason": cat.get("reason") or "no jurisdiction context",
            })

    return {"existing": existing, "missing": missing, "ambiguous": ambiguous}


async def gap_check(
    *,
    basics: dict[str, Any],
    locations: list[dict[str, Any]],
    ai_scope: Optional[dict[str, Any]],
    resolved_scope: Optional[dict[str, Any]],
    conn,
) -> dict[str, Any]:
    """End-of-wizard safety net — Gemini reviews the full captured state
    and surfaces anything the AI scope expansion missed.

    Read-only: returns suggestions, never writes to ai_scope. Admin can
    re-run expand if they want suggestions folded in.

    Returns shape:
        {
          "suggested_compliance_categories": [...],
          "suggested_certifications": [...],
          "suggested_licenses": [...],
          "suggested_jurisdictions": [...],
          "summary": "1-2 sentence overview"
        }

    Empty arrays + "looks comprehensive" summary is the green path.
    """
    category_slugs = await _fetch_category_slugs(conn)
    industry = (basics.get("industry") or "general").strip()
    specialty = (basics.get("specialty") or "").strip() or None
    business_name = (basics.get("business_name") or "").strip()
    description = (basics.get("description") or "").strip() or None

    ai_scope = ai_scope or {}
    resolved_scope = resolved_scope or {}
    existing = resolved_scope.get("existing") or []
    missing = resolved_scope.get("missing") or []

    prompt = (
        f"You are doing a FINAL GAP CHECK on a compliance-tracking onboarding "
        f"manifest for \"{business_name}\".\n\n"
        f"The AI scope expansion already ran once. Your job is the safety net "
        f"BEFORE the admin commits. The HR admin running this wizard may not "
        f"know which compliance buckets apply — surface anything the first "
        f"pass missed. Do NOT re-list items already present below.\n\n"
        f"BUSINESS INPUT:\n"
        f"  Industry: {industry}\n"
        f"  Specialty: {specialty or '(none)'}\n"
        f"  Locations: {json.dumps(locations)}\n"
        + (f"  Description: {description}\n" if description else "")
        + f"\nALREADY-CAPTURED AI SCOPE:\n"
        f"  Categories: {json.dumps([c.get('category_slug') for c in (ai_scope.get('compliance_categories') or [])])}\n"
        f"  Certifications: {json.dumps([c.get('slug') for c in (ai_scope.get('required_certifications') or [])])}\n"
        f"  Licenses: {json.dumps([l.get('slug') for l in (ai_scope.get('required_licenses') or [])])}\n"
        f"  Jurisdictions: {json.dumps(ai_scope.get('applicable_jurisdictions') or [])}\n\n"
        f"BANK RECONCILIATION RESULTS:\n"
        f"  Already in bank (good): {len(existing)} items\n"
        f"  Marked missing (need research): {len(missing)} items\n\n"
        f"Live compliance category enum: {json.dumps(category_slugs)}\n\n"
        f"Return ONLY JSON of this exact shape:\n"
        f'{{"suggested_compliance_categories": [\n'
        f'   {{"category_slug": "string from live enum", "scope": "federal|state|county|city", "reason": "why the admin might have missed this"}}\n'
        f' ],\n'
        f' "suggested_certifications": [\n'
        f'   {{"slug": "string", "name": "string", "reason": "string"}}\n'
        f' ],\n'
        f' "suggested_licenses": [\n'
        f'   {{"slug": "string", "name": "string", "reason": "string"}}\n'
        f' ],\n'
        f' "suggested_jurisdictions": [\n'
        f'   {{"state": "CA or null", "county": "string or null", "city": "string or null", "reason": "string"}}\n'
        f' ],\n'
        f' "summary": "1-2 sentence overview — say so if everything looks comprehensive"\n'
        f'}}\n\n'
        f"Rules:\n"
        f"- If the manifest looks comprehensive, return empty arrays and a confirming summary.\n"
        f"- suggested_compliance_categories.category_slug MUST be from the live enum.\n"
        f"- Do NOT propose anything already present in ALREADY-CAPTURED AI SCOPE.\n"
        f"- Use the description (when supplied) to surface non-obvious items —\n"
        f"  grad students → IRB/visa rules; lab work → biosafety; cash handling → PCI;\n"
        f"  multi-state remote workers → per-state wage-theft notices + tax nexus;\n"
        f"  minors → state child-labor permits; tipped staff → state tip credit rules;\n"
        f"  late hours → late-hours permit + security ordinance; etc.\n"
    )

    try:
        client = _gemini_client()
    except Exception as exc:
        logger.exception("Gemini client init failed for gap check: %s", exc)
        raise

    model_name = os.getenv("ONBOARDING_SCOPE_MODEL", "gemini-2.5-flash")
    try:
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
            ),
            timeout=GEMINI_GAPCHECK_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.exception("Gemini gap check call failed: %s", exc)
        raise

    raw = (getattr(response, "text", None) or "").strip()
    try:
        parsed = json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError:
        logger.warning("Gap check returned non-JSON: %s", raw[:200])
        return {
            "suggested_compliance_categories": [],
            "suggested_certifications": [],
            "suggested_licenses": [],
            "suggested_jurisdictions": [],
            "summary": "Gap check could not produce a structured response; admin should re-run.",
        }
    if not isinstance(parsed, dict):
        parsed = {}

    # Filter category slugs to live enum.
    live = set(category_slugs)
    cats = parsed.get("suggested_compliance_categories") or []
    parsed["suggested_compliance_categories"] = [
        c for c in cats
        if isinstance(c, dict) and c.get("category_slug") in live
    ]
    # Make sure all expected keys exist so the downstream Pydantic
    # validator doesn't 422 on a partial response.
    for key in (
        "suggested_compliance_categories",
        "suggested_certifications",
        "suggested_licenses",
        "suggested_jurisdictions",
    ):
        if not isinstance(parsed.get(key), list):
            parsed[key] = []
    if not isinstance(parsed.get("summary"), str):
        parsed["summary"] = ""
    return parsed


def build_missing_id(item: dict[str, Any]) -> str:
    """Stable id for a missing item so admin checkboxes can reference it."""
    state = item.get("state") or "-"
    county = item.get("county") or "-"
    city = item.get("city") or "-"
    return f"{item.get('category_slug') or '?'}::{item.get('scope_level') or '?'}::{state}::{county}::{city}"
