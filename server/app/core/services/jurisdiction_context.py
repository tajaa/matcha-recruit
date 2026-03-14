"""Dynamic jurisdiction context management.

This module handles learning and retrieving authoritative sources for jurisdictions,
enabling better first-attempt accuracy in compliance research by providing Gemini
with known good sources.

Phase 3.2 adds source reputation tracking for confidence score blending.
"""
from typing import Optional, List, Dict
from urllib.parse import urlparse
import asyncpg


async def get_known_sources(conn: asyncpg.Connection, jurisdiction_id) -> List[dict]:
    """Get known authoritative sources for a jurisdiction.

    Returns the top 5 most successful sources, ordered by success count.
    """
    rows = await conn.fetch("""
        SELECT domain, source_name, categories, success_count
        FROM jurisdiction_sources
        WHERE jurisdiction_id = $1
        ORDER BY success_count DESC
        LIMIT 5
    """, jurisdiction_id)
    return [dict(r) for r in rows]


async def record_source(
    conn: asyncpg.Connection,
    jurisdiction_id,
    domain: str,
    source_name: Optional[str],
    category: str,
):
    """Record a source seen in research results.

    Uses upsert to increment success_count for existing sources or insert new ones.
    Categories are accumulated in an array for sources that cover multiple categories.
    """
    if not domain:
        return

    # Normalize domain
    domain = domain.lower().strip()

    await conn.execute("""
        INSERT INTO jurisdiction_sources (jurisdiction_id, domain, source_name, categories, success_count, last_seen_at)
        VALUES ($1, $2, $3, ARRAY[$4], 1, NOW())
        ON CONFLICT (jurisdiction_id, domain) DO UPDATE SET
            source_name = COALESCE(EXCLUDED.source_name, jurisdiction_sources.source_name),
            categories = (
                SELECT array_agg(DISTINCT elem)
                FROM unnest(jurisdiction_sources.categories || ARRAY[$4]) AS elem
            ),
            success_count = jurisdiction_sources.success_count + 1,
            last_seen_at = NOW()
    """, jurisdiction_id, domain, source_name, category)


def extract_domain(url: str) -> str:
    """Extract the domain from a URL.

    Example: "https://dir.ca.gov/dlse/faq_overtime.htm" -> "dir.ca.gov"
    """
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split('/')[0]
        # Remove www. prefix if present
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain.lower()
    except Exception:
        return ""


# Authoritative federal/national sources for healthcare and oncology categories.
# These are always applicable regardless of jurisdiction and are injected into
# Gemini prompts to anchor research to the highest-authority sources.
CATEGORY_AUTHORITY_SOURCES: Dict[str, List[Dict[str, str]]] = {
    # Healthcare
    "hipaa_privacy": [
        {"domain": "hhs.gov/hipaa", "name": "HHS Office for Civil Rights (HIPAA)"},
        {"domain": "ecfr.gov", "name": "45 CFR Part 164 (Privacy Rule)"},
    ],
    "billing_integrity": [
        {"domain": "oig.hhs.gov", "name": "HHS Office of Inspector General"},
        {"domain": "cms.gov", "name": "CMS Billing & Coding"},
        {"domain": "ftc.gov", "name": "FTC Healthcare Billing"},
    ],
    "clinical_safety": [
        {"domain": "jointcommission.org", "name": "The Joint Commission"},
        {"domain": "cms.gov", "name": "CMS Conditions of Participation"},
        {"domain": "ahrq.gov", "name": "AHRQ Patient Safety"},
    ],
    "healthcare_workforce": [
        {"domain": "hrsa.gov", "name": "HRSA Health Workforce"},
        {"domain": "bls.gov", "name": "BLS Occupational Outlook"},
        {"domain": "cms.gov", "name": "CMS Staffing Requirements"},
    ],
    "corporate_integrity": [
        {"domain": "oig.hhs.gov/compliance", "name": "OIG Corporate Integrity Agreements"},
        {"domain": "hhs.gov", "name": "HHS Compliance Guidance"},
    ],
    "research_consent": [
        {"domain": "hhs.gov/ohrp", "name": "HHS Office for Human Research Protections"},
        {"domain": "fda.gov", "name": "FDA 21 CFR Part 50 (Informed Consent)"},
        {"domain": "ecfr.gov", "name": "45 CFR Part 46 (Common Rule)"},
    ],
    "state_licensing": [
        {"domain": "hhs.gov", "name": "HHS State Health Licensing"},
        {"domain": "cms.gov", "name": "CMS Provider Enrollment"},
    ],
    "emergency_preparedness": [
        {"domain": "aspr.hhs.gov", "name": "ASPR (HHS Office of Preparedness)"},
        {"domain": "cms.gov", "name": "CMS Emergency Preparedness Rule"},
        {"domain": "cdc.gov", "name": "CDC Public Health Emergency"},
    ],
    # Oncology
    "radiation_safety": [
        {"domain": "nrc.gov", "name": "Nuclear Regulatory Commission"},
        {"domain": "cdc.gov/niosh", "name": "NIOSH Radiation Safety"},
        {"domain": "osha.gov", "name": "OSHA Ionizing Radiation (29 CFR 1910.1096)"},
    ],
    "chemotherapy_handling": [
        {"domain": "cdc.gov/niosh", "name": "NIOSH Hazardous Drug Alert (2004-165)"},
        {"domain": "usp.org", "name": "USP 800 Hazardous Drugs Standard"},
        {"domain": "osha.gov", "name": "OSHA Hazardous Drugs in Healthcare"},
    ],
    "tumor_registry": [
        {"domain": "naaccr.org", "name": "NAACCR (North American Cancer Registries)"},
        {"domain": "seer.cancer.gov", "name": "NCI SEER Program"},
        {"domain": "cdc.gov/cancer", "name": "CDC National Program of Cancer Registries"},
    ],
    "oncology_clinical_trials": [
        {"domain": "clinicaltrials.gov", "name": "ClinicalTrials.gov"},
        {"domain": "nci.nih.gov", "name": "National Cancer Institute"},
        {"domain": "fda.gov", "name": "FDA IND/Clinical Trial Regulations"},
    ],
    "oncology_patient_rights": [
        {"domain": "cancer.gov", "name": "NCI Patient Rights"},
        {"domain": "cms.gov", "name": "CMS Patient Rights (Conditions of Participation)"},
        {"domain": "hhs.gov/ocr", "name": "HHS Office for Civil Rights"},
    ],
    "health_it": [
        {"domain": "healthit.gov", "name": "ONC Health IT"},
        {"domain": "congress.gov", "name": "21st Century Cures Act"},
        {"domain": "rce.sequoiaproject.org", "name": "TEFCA RCE"},
    ],
    "quality_reporting": [
        {"domain": "qpp.cms.gov", "name": "CMS Quality Payment Program"},
        {"domain": "ncqa.org", "name": "NCQA HEDIS Measures"},
        {"domain": "cms.gov", "name": "CMS Value-Based Programs"},
    ],
    "cybersecurity": [
        {"domain": "nist.gov", "name": "NIST Cybersecurity Framework"},
        {"domain": "hhs.gov/hipaa", "name": "HHS HIPAA Security Rule"},
        {"domain": "cisa.gov", "name": "CISA Healthcare Cybersecurity"},
    ],
    "environmental_safety": [
        {"domain": "nfpa.org", "name": "NFPA Life Safety Code"},
        {"domain": "osha.gov", "name": "OSHA Healthcare Standards"},
        {"domain": "epa.gov", "name": "EPA Medical Waste (RCRA)"},
    ],
    "pharmacy_drugs": [
        {"domain": "deadiversion.usdoj.gov", "name": "DEA Diversion Control"},
        {"domain": "hrsa.gov/opa", "name": "HRSA 340B Program"},
        {"domain": "fda.gov", "name": "FDA DSCSA / Drug Safety"},
    ],
    "payer_relations": [
        {"domain": "cms.gov", "name": "CMS Medicare Advantage / Medicaid MCO"},
        {"domain": "cms.gov/nosurprises", "name": "No Surprises Act (CMS)"},
    ],
    "reproductive_behavioral": [
        {"domain": "samhsa.gov", "name": "SAMHSA (42 CFR Part 2)"},
        {"domain": "cms.gov", "name": "CMS Mental Health Parity"},
        {"domain": "hhs.gov/ocr", "name": "HHS Office for Civil Rights"},
    ],
    "pediatric_vulnerable": [
        {"domain": "acf.hhs.gov", "name": "ACF (CAPTA / Child Welfare)"},
        {"domain": "acl.gov", "name": "ACL Elder Justice"},
        {"domain": "childwelfare.gov", "name": "Child Welfare Information Gateway"},
    ],
    "telehealth": [
        {"domain": "imlcc.org", "name": "Interstate Medical Licensure Compact"},
        {"domain": "ncsbn.org/nlc", "name": "Nurse Licensure Compact"},
        {"domain": "cchpca.org", "name": "CCHP Telehealth Policy"},
    ],
    "medical_devices": [
        {"domain": "fda.gov/medicaldevices", "name": "FDA Medical Devices"},
        {"domain": "accessdata.fda.gov", "name": "FDA MDR / UDI Database"},
    ],
    "transplant_organ": [
        {"domain": "optn.transplant.hrsa.gov", "name": "OPTN / UNOS"},
        {"domain": "cms.gov", "name": "CMS Transplant CoPs"},
        {"domain": "organdonor.gov", "name": "HRSA Organ Donation"},
    ],
    "antitrust": [
        {"domain": "ftc.gov", "name": "FTC Healthcare Competition"},
        {"domain": "justice.gov/atr", "name": "DOJ Antitrust Division"},
    ],
    "tax_exempt": [
        {"domain": "irs.gov", "name": "IRS § 501(r) / Schedule H"},
        {"domain": "aha.org", "name": "AHA Community Benefit"},
    ],
    "language_access": [
        {"domain": "hhs.gov/ocr", "name": "HHS OCR Section 1557"},
        {"domain": "lep.gov", "name": "Federal LEP Resources"},
        {"domain": "ada.gov", "name": "ADA Title III"},
    ],
    "records_retention": [
        {"domain": "hhs.gov/hipaa", "name": "HIPAA Retention Requirements"},
        {"domain": "ahima.org", "name": "AHIMA Retention Guidelines"},
    ],
    "marketing_comms": [
        {"domain": "hhs.gov/hipaa", "name": "HIPAA Marketing Rules"},
        {"domain": "cms.gov", "name": "CMS Marketing Guidelines (MCMG)"},
        {"domain": "fcc.gov", "name": "FCC TCPA Enforcement"},
    ],
    "emerging_regulatory": [
        {"domain": "fda.gov", "name": "FDA AI/SaMD Framework"},
        {"domain": "cms.gov", "name": "CMS SDOH Initiatives"},
        {"domain": "hhs.gov", "name": "HHS Emerging Policy"},
    ],
}


def get_global_authority_sources(categories: List[str]) -> str:
    """Return a formatted prompt section listing federal authoritative sources
    for the given categories. Returns empty string if no matches."""
    lines = []
    seen_domains: set = set()
    for cat in categories:
        sources = CATEGORY_AUTHORITY_SOURCES.get(cat, [])
        for src in sources:
            if src["domain"] not in seen_domains:
                seen_domains.add(src["domain"])
                lines.append(f"- {src['domain']} ({src['name']}) - for: {cat.replace('_', ' ')}")

    if not lines:
        return ""
    return "\nFEDERAL AUTHORITATIVE SOURCES (prioritize these):\n" + "\n".join(lines)


def build_context_prompt(known_sources: List[dict]) -> str:
    """Build prompt section from known sources.

    Returns an empty string if no sources are known, or a formatted
    section listing known authoritative sources for the jurisdiction.
    """
    if not known_sources:
        return ""

    lines = ["\nKNOWN AUTHORITATIVE SOURCES (prefer these when available):"]
    for s in known_sources:
        source_name = s.get('source_name', 'unknown')
        domain = s.get('domain', '')
        categories = s.get('categories', [])
        cat_str = ", ".join(categories) if categories else "general"
        lines.append(f"- {domain} ({source_name}) - covers: {cat_str}")

    return "\n".join(lines)


# =============================================================================
# Phase 3.2: Source Reputation Tracking
# =============================================================================

async def get_source_accuracy(
    conn: asyncpg.Connection,
    jurisdiction_id,
    domain: str,
) -> float:
    """Get accuracy score for a source domain with Laplace smoothing.

    Returns a value between 0.0 and 1.0 representing historical accuracy.
    Uses Laplace smoothing (add-1) to handle sources with little data.

    Args:
        conn: Database connection
        jurisdiction_id: UUID of the jurisdiction
        domain: Source domain to look up

    Returns:
        Float between 0.0 and 1.0 (0.5 for unknown sources)
    """
    if not domain:
        return 0.5  # Neutral for unknown

    domain = domain.lower().strip()

    row = await conn.fetchrow("""
        SELECT accurate_count, inaccurate_count
        FROM jurisdiction_sources
        WHERE jurisdiction_id = $1 AND domain = $2
    """, jurisdiction_id, domain)

    if not row:
        return 0.5  # Neutral for unknown sources

    accurate = row["accurate_count"] or 0
    inaccurate = row["inaccurate_count"] or 0

    # Laplace smoothing: (accurate + 1) / (total + 2)
    # This prevents 0/0 and provides a reasonable prior
    total = accurate + inaccurate
    return (accurate + 1) / (total + 2)


async def get_source_reputations(
    conn: asyncpg.Connection,
    jurisdiction_id,
    domains: List[str],
) -> Dict[str, float]:
    """Batch lookup of accuracy scores for multiple domains.

    Args:
        conn: Database connection
        jurisdiction_id: UUID of the jurisdiction
        domains: List of source domains to look up

    Returns:
        Dict mapping domain -> accuracy score (0.0-1.0)
    """
    if not domains:
        return {}

    # Normalize domains
    normalized = [d.lower().strip() for d in domains if d]
    if not normalized:
        return {}

    rows = await conn.fetch("""
        SELECT domain, accurate_count, inaccurate_count
        FROM jurisdiction_sources
        WHERE jurisdiction_id = $1 AND domain = ANY($2)
    """, jurisdiction_id, normalized)

    result = {}
    found_domains = set()

    for row in rows:
        domain = row["domain"]
        found_domains.add(domain)
        accurate = row["accurate_count"] or 0
        inaccurate = row["inaccurate_count"] or 0
        total = accurate + inaccurate
        result[domain] = (accurate + 1) / (total + 2)

    # Fill in unknown domains with neutral 0.5
    for domain in normalized:
        if domain not in found_domains:
            result[domain] = 0.5

    return result


async def update_source_accuracy(
    conn: asyncpg.Connection,
    jurisdiction_id,
    domain: str,
    was_accurate: bool,
):
    """Update accuracy counters for a source domain.

    Args:
        conn: Database connection
        jurisdiction_id: UUID of the jurisdiction
        domain: Source domain
        was_accurate: True if the source provided accurate information
    """
    if not domain:
        return

    domain = domain.lower().strip()

    if was_accurate:
        await conn.execute("""
            UPDATE jurisdiction_sources
            SET accurate_count = COALESCE(accurate_count, 0) + 1,
                last_accuracy_update = NOW()
            WHERE jurisdiction_id = $1 AND domain = $2
        """, jurisdiction_id, domain)
    else:
        await conn.execute("""
            UPDATE jurisdiction_sources
            SET inaccurate_count = COALESCE(inaccurate_count, 0) + 1,
                last_accuracy_update = NOW()
            WHERE jurisdiction_id = $1 AND domain = $2
        """, jurisdiction_id, domain)
