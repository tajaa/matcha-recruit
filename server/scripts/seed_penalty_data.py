#!/usr/bin/env python3
"""Seed penalty/fine data into jurisdiction_requirements.metadata from known sources.

Bootstraps penalty information from:
1. compliance_registry.py RegulationDef entries (enforcing_agency)
2. Hardcoded penalty ranges from risk_assessment_service.py and official sources

Does NOT delete or overwrite existing penalty data — only fills gaps.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import load_settings
from app.database import init_pool, close_pool, get_pool

# ── Penalty seed data ──
# Sourced from Federal Register, agency websites, and risk_assessment_service.py
PENALTY_SEED: dict[str, dict] = {
    # HIPAA (45 CFR 160.404, inflation-adjusted 2025)
    "hipaa_privacy": {
        "enforcing_agency": "HHS OCR",
        "civil_penalty_min": 137,
        "civil_penalty_max": 2067813,
        "per_violation": True,
        "annual_cap": 2067813,
        "criminal": "Up to $250,000 and 10 years imprisonment for willful violations",
        "summary": "$137–$2.07M per violation (4 tiers); annual cap $2.07M per category",
    },
    # OSHA (29 USC 666, 2025 inflation-adjusted)
    "workplace_safety": {
        "enforcing_agency": "OSHA",
        "civil_penalty_min": 1190,
        "civil_penalty_max": 165514,
        "per_violation": True,
        "annual_cap": None,
        "criminal": "Up to $250,000 and 6 months imprisonment for willful violations causing death",
        "summary": "$1,190–$16,550 per serious violation; up to $165,514 for willful/repeat",
    },
    # FLSA (29 USC 216, 2025)
    "minimum_wage": {
        "enforcing_agency": "DOL WHD",
        "civil_penalty_min": 0,
        "civil_penalty_max": 2451,
        "per_violation": True,
        "annual_cap": None,
        "criminal": "Up to $10,000 fine and 6 months imprisonment for willful violations",
        "summary": "Up to $2,451 per violation; back wages + liquidated damages",
    },
    "overtime": {
        "enforcing_agency": "DOL WHD",
        "civil_penalty_min": 0,
        "civil_penalty_max": 2451,
        "per_violation": True,
        "annual_cap": None,
        "criminal": None,
        "summary": "Up to $2,451 per violation; back wages + equal liquidated damages",
    },
    # FMLA (29 USC 2617)
    "leave": {
        "enforcing_agency": "DOL WHD",
        "civil_penalty_min": 0,
        "civil_penalty_max": None,
        "per_violation": False,
        "annual_cap": None,
        "criminal": None,
        "summary": "Damages equal to lost wages/benefits + liquidated damages; no per-violation civil penalty",
    },
    # Title VII / EEOC (42 USC 1981a)
    "anti_discrimination": {
        "enforcing_agency": "EEOC",
        "civil_penalty_min": 0,
        "civil_penalty_max": 300000,
        "per_violation": False,
        "annual_cap": None,
        "criminal": None,
        "summary": "Compensatory + punitive damages capped $50K–$300K by employer size; unlimited back pay",
    },
    # False Claims Act (31 USC 3729, 2025)
    "billing_integrity": {
        "enforcing_agency": "DOJ / OIG",
        "civil_penalty_min": 13946,
        "civil_penalty_max": 27894,
        "per_violation": True,
        "annual_cap": None,
        "criminal": "Up to $250,000 fine and 5 years imprisonment per count",
        "summary": "$13,946–$27,894 per false claim + treble damages",
    },
    # CMS Conditions of Participation
    "clinical_safety": {
        "enforcing_agency": "CMS / State Survey Agencies",
        "civil_penalty_min": 0,
        "civil_penalty_max": 10000,
        "per_violation": True,
        "annual_cap": None,
        "criminal": None,
        "summary": "Up to $10,000/day for CoP deficiencies; termination from Medicare/Medicaid",
    },
    # CMS Emergency Preparedness Rule
    "emergency_preparedness": {
        "enforcing_agency": "CMS",
        "civil_penalty_min": 0,
        "civil_penalty_max": 10000,
        "per_violation": True,
        "annual_cap": None,
        "criminal": None,
        "summary": "Up to $10,000/day for non-compliance; loss of Medicare certification",
    },
    # OIG Compliance
    "corporate_integrity": {
        "enforcing_agency": "OIG / DOJ",
        "civil_penalty_min": 0,
        "civil_penalty_max": 100000,
        "per_violation": True,
        "annual_cap": None,
        "criminal": None,
        "summary": "Civil monetary penalties up to $100K/violation; exclusion from federal programs",
    },
    # HIPAA Security / Cybersecurity
    "cybersecurity": {
        "enforcing_agency": "HHS OCR / State AGs",
        "civil_penalty_min": 137,
        "civil_penalty_max": 2067813,
        "per_violation": True,
        "annual_cap": 2067813,
        "criminal": None,
        "summary": "HIPAA Security Rule: same 4-tier penalty as Privacy Rule; state breach notification fines vary",
    },
    # DEA Controlled Substances
    "pharmacy_drugs": {
        "enforcing_agency": "DEA / State Pharmacy Boards",
        "civil_penalty_min": 0,
        "civil_penalty_max": 25000,
        "per_violation": True,
        "annual_cap": None,
        "criminal": "Schedule I/II trafficking: up to $1M and 20 years; diversion: up to $250K and 4 years",
        "summary": "Civil: up to $25,000 per violation; criminal varies by schedule and offense",
    },
    # Workers Comp
    "workers_comp": {
        "enforcing_agency": "State Workers' Comp Board",
        "civil_penalty_min": 1000,
        "civil_penalty_max": 100000,
        "per_violation": False,
        "annual_cap": None,
        "criminal": "Misdemeanor in most states; felony for fraud",
        "summary": "$1,000–$100,000+ for failure to carry insurance (varies by state)",
    },
    # Telehealth
    "telehealth": {
        "enforcing_agency": "State Medical Boards / CMS / DEA",
        "civil_penalty_min": 0,
        "civil_penalty_max": 25000,
        "per_violation": True,
        "annual_cap": None,
        "criminal": "Practicing without proper licensure: misdemeanor/felony by state",
        "summary": "State board fines up to $25K; DEA penalties for improper telehealth prescribing",
    },
    # Radiation Safety
    "radiation_safety": {
        "enforcing_agency": "NRC / State Radiation Control",
        "civil_penalty_min": 0,
        "civil_penalty_max": 375000,
        "per_violation": True,
        "annual_cap": None,
        "criminal": "Up to $250,000 and 5 years for willful violations",
        "summary": "NRC: up to $375,000 per violation per day; state programs vary",
    },
    # Medical Devices
    "medical_devices": {
        "enforcing_agency": "FDA",
        "civil_penalty_min": 0,
        "civil_penalty_max": 1000000,
        "per_violation": False,
        "annual_cap": None,
        "criminal": "Up to $1M fine and 3 years imprisonment for fraud/misbranding",
        "summary": "FDA warning letters, consent decrees, seizure; criminal fines up to $1M",
    },
    # Language Access (Title VI)
    "language_access": {
        "enforcing_agency": "HHS OCR",
        "civil_penalty_min": 0,
        "civil_penalty_max": None,
        "per_violation": False,
        "annual_cap": None,
        "criminal": None,
        "summary": "Loss of federal funding; OCR enforcement actions and corrective action plans",
    },
    # Records Retention
    "records_retention": {
        "enforcing_agency": "CMS / State Health Depts / HHS OCR",
        "civil_penalty_min": 0,
        "civil_penalty_max": 50000,
        "per_violation": True,
        "annual_cap": None,
        "criminal": None,
        "summary": "Spoliation sanctions; HIPAA penalties for retention failures; state fines vary",
    },
}


async def main():
    load_settings()
    await init_pool()
    pool = get_pool()

    updated = 0
    skipped = 0

    async with pool.acquire() as conn:
        for category, penalty_data in PENALTY_SEED.items():
            # Find requirements in this category that don't have penalty data yet
            rows = await conn.fetch(
                """
                SELECT id, metadata
                FROM jurisdiction_requirements
                WHERE category = $1 AND status = 'active'
                  AND (metadata IS NULL OR NOT (metadata ? 'penalties'))
                """,
                category,
            )
            if not rows:
                print(f"  {category}: all {0} requirements already have penalty data, skipping")
                skipped += 1
                continue

            # Update metadata with penalty data
            penalty_json = json.dumps({"penalties": penalty_data})
            result = await conn.execute(
                """
                UPDATE jurisdiction_requirements
                SET metadata = COALESCE(metadata, '{}'::jsonb) || $1::jsonb,
                    updated_at = NOW()
                WHERE category = $2 AND status = 'active'
                  AND (metadata IS NULL OR NOT (metadata ? 'penalties'))
                """,
                penalty_json,
                category,
            )
            count = int(result.split()[-1])
            print(f"  {category}: updated {count} requirements with penalty data")
            updated += count

    await close_pool()
    print(f"\nDone. Updated {updated} requirements, {skipped} categories already seeded.")


if __name__ == "__main__":
    asyncio.run(main())
