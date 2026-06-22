"""Grounded exclusion-gap analysis — emerging casualty exclusions creeping into
GL / umbrella / auto forms (WTW: PFAS, abuse & molestation, TBI, wildfire,
biometric/BIPA, silent-cyber, silent-AI…).

Replaces the old ungrounded free-gen: a curated registry of REAL emerging
exclusions, each mapped to the lines it hits, why it's hardening, the
industries/triggers that make it relevant, and the mitigation. Relevance is
decided from data we own — the client's industry, operating states, and
mitigation signals already captured (biometric consent, abuse-prevention /
infection-control programs, AI-hiring audits, MVR/driver data). Pure ``analyze``
is unit-testable; ``company_exclusions`` gathers the signals.

Severity is a directional underwriting flag (which exclusions a risk like this
typically faces), not a coverage determination.
"""

from uuid import UUID

from . import wc_depth

WILDFIRE_STATES = {"CA", "OR", "WA", "CO", "MT", "ID", "AZ", "NV", "UT", "NM", "TX", "WY"}

# Curated registry of emerging casualty exclusions. `keywords` = industry-string
# triggers; `signal` = a data signal that also makes it relevant; `state_trigger`
# = wildfire-state driven; `inherent` = always in play (broad); `mitigated_by` =
# the owned-data signal that documents mitigation.
EXCLUSION_CATALOG = [
    {"key": "pfas", "label": "PFAS / 'forever chemicals'", "lines": ["GL", "Umbrella", "Product"],
     "creep": "Broad PFAS exclusions spreading across GL/product as litigation surges.",
     "keywords": ["manufactur", "chemical", "textile", "plastic", "coating", "firefight", "packaging", "industrial", "paint"],
     "mitigation": "Confirm no PFAS in products/processes; seek affirmative coverage or a buy-back endorsement."},
    {"key": "abuse_molestation", "label": "Abuse & molestation (A&M / SAM)", "lines": ["GL", "Umbrella"],
     "creep": "A&M increasingly sub-limited or excluded; standalone SAM often required.",
     "keywords": ["health", "senior", "assisted", "nursing", "child", "day care", "daycare", "school", "educat",
                  "social", "hospitality", "hotel", "camp", "church", "fitness", "gym"],
     "mitigated_by": "abuse_program",
     "mitigation": "Background-check protocol + documented abuse-prevention program; secure a standalone SAM limit."},
    {"key": "biometric_bipa", "label": "Biometric / BIPA", "lines": ["GL", "EPL", "Cyber"],
     "creep": "BIPA class actions drive biometric exclusions onto GL and cyber forms.",
     "keywords": ["manufactur", "warehouse", "logistics", "retail", "health", "hospitality"],
     "signal": "biometric_present", "mitigated_by": "biometric_consented",
     "mitigation": "BIPA-compliant written consent + a documented retention/deletion policy before collection."},
    {"key": "tbi", "label": "Traumatic brain injury (TBI)", "lines": ["Auto", "GL", "Umbrella"],
     "creep": "TBI claims anchor nuclear verdicts; carriers add severity sub-limits.",
     "keywords": ["truck", "transport", "logistics", "fleet", "deliver", "construction", "sport", "recreation", "warehouse"],
     "signal": "has_drivers",
     "mitigation": "Document fleet-safety + medical-management; confirm umbrella adequacy for severity."},
    {"key": "wildfire", "label": "Wildfire", "lines": ["Property", "GL"],
     "creep": "Wildfire exclusions / sub-limits now standard in CAT-exposed states.",
     "keywords": [], "state_trigger": True,
     "mitigation": "Document defensible-space + wildfire-mitigation controls; confirm affirmative wildfire limits."},
    {"key": "silent_cyber", "label": "Silent cyber", "lines": ["GL", "Property", "Umbrella"],
     "creep": "Cyber excluded from non-cyber policies (e.g. CL 380); coverage falls between towers.",
     "keywords": [], "inherent": True,
     "mitigation": "Place affirmative standalone cyber; map GL/property cyber carve-outs across the program."},
    {"key": "silent_ai", "label": "Silent AI", "lines": ["GL", "EPL", "Professional", "Cyber"],
     "creep": "Emerging AI-liability exclusions; Title VII applies to AI hiring tools.",
     "keywords": ["tech", "software", "staffing", "recruit", "data", "analytics"],
     "signal": "ai_audit", "mitigated_by": "ai_audit",
     "mitigation": "Run AI bias audits; seek affirmative AI coverage; document model governance."},
    {"key": "communicable_disease", "label": "Communicable disease", "lines": ["GL", "Umbrella"],
     "creep": "Post-COVID communicable-disease exclusions now standard on GL.",
     "keywords": ["health", "senior", "nursing", "assisted", "hospitality", "hotel", "restaurant", "food", "child", "school"],
     "mitigated_by": "infection_program",
     "mitigation": "Document an infection-control program; seek carve-backs where operations warrant."},
    {"key": "assault_battery", "label": "Assault & battery", "lines": ["GL"],
     "creep": "A&B exclusions / sub-limits common in hospitality, nightlife, security, retail.",
     "keywords": ["hospitality", "hotel", "bar", "night", "security", "retail", "restaurant", "entertainment"],
     "mitigation": "Document security protocols + incident response; seek a stated A&B sub-limit vs an exclusion."},
]

_RANK = {"exposed": 0, "monitor": 1, "mitigated": 2}


def analyze(industry, signals: dict) -> dict:
    """Pure: which emerging exclusions a risk like this faces, given industry +
    owned-data signals. Returns relevant exclusions (exposed first) + a summary."""
    ind = (industry or "").lower()
    out: list[dict] = []
    for ex in EXCLUSION_CATALOG:
        relevant = ex.get("inherent", False)
        if any(k in ind for k in ex.get("keywords", [])):
            relevant = True
        if ex.get("signal") and signals.get(ex["signal"]):
            relevant = True
        if ex.get("state_trigger") and signals.get("wildfire_state"):
            relevant = True
        if not relevant:
            continue
        mitigated = bool(ex.get("mitigated_by") and signals.get(ex["mitigated_by"]))
        status = "mitigated" if mitigated else ("monitor" if ex.get("inherent") else "exposed")
        out.append({"key": ex["key"], "label": ex["label"], "lines": ex["lines"],
                    "creep": ex["creep"], "mitigation": ex["mitigation"], "status": status})
    out.sort(key=lambda e: _RANK.get(e["status"], 3))
    return {
        "exclusions": out,
        "summary": {
            "exposed": sum(1 for e in out if e["status"] == "exposed"),
            "monitor": sum(1 for e in out if e["status"] == "monitor"),
            "mitigated": sum(1 for e in out if e["status"] == "mitigated"),
            "total": len(out),
        },
    }


async def _gather_signals(conn, company_id: UUID, states: list[str]) -> dict:
    async def cnt(q) -> int:
        try:
            return int(await conn.fetchval(q, company_id) or 0)
        except Exception:  # pragma: no cover - defensive (table/feature absent)
            return 0

    bio = await cnt("SELECT count(*) FROM biometric_consent_points WHERE company_id = $1 AND COALESCE(is_active, true)")
    bio_consent = await cnt("SELECT count(*) FROM biometric_consent_points WHERE company_id = $1 AND COALESCE(is_active, true) AND consent_obtained = true")
    abuse = await cnt("SELECT count(*) FROM safety_programs WHERE company_id = $1 AND program_type = 'abuse_prevention' AND status = 'active'")
    infection = await cnt("SELECT count(*) FROM safety_programs WHERE company_id = $1 AND program_type = 'infection_control' AND status = 'active'")
    ai = await cnt("SELECT count(*) FROM hiring_ai_audits WHERE company_id = $1")
    drivers = await cnt("SELECT count(*) FROM mvr_reviews WHERE company_id = $1")
    return {
        "biometric_present": bio > 0, "biometric_consented": bio_consent > 0,
        "abuse_program": abuse > 0, "infection_program": infection > 0,
        "ai_audit": ai > 0, "has_drivers": drivers > 0,
        "wildfire_state": any((s or "").upper() in WILDFIRE_STATES for s in states),
    }


async def company_exclusions(conn, company_id: UUID) -> dict:
    """Grounded exclusion exposure for a tenant. Never raises."""
    company = await conn.fetchrow("SELECT industry FROM companies WHERE id = $1", company_id)
    industry = company["industry"] if company else None
    try:
        states = await wc_depth.resolve_company_states(conn, company_id)
    except Exception:  # pragma: no cover
        states = []
    signals = await _gather_signals(conn, company_id, states)
    return analyze(industry, signals)


def external_exclusions(industry, state) -> dict:
    """Off-platform client: only industry + wildfire-state drive relevance (no owned signals)."""
    return analyze(industry, {"wildfire_state": (state or "").upper() in WILDFIRE_STATES})
