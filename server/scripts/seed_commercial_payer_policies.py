#!/usr/bin/env python3
"""
Seed commercial payer medical policies via Gemini research.

Researches common procedures for major commercial payers.
Run after CMS ingestion to fill gaps for non-Medicare payers.

Usage:
    cd server
    python scripts/seed_commercial_payer_policies.py
    python scripts/seed_commercial_payer_policies.py --payer "Aetna"
    python scripts/seed_commercial_payer_policies.py --dry-run
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SKIP_REDIS", "1")

PAYERS = [
    "Aetna",
    "UnitedHealthcare",
    "Blue Cross Blue Shield",
    "Cigna",
]

COMMON_PROCEDURES = [
    "Brain MRI",
    "Lumbar Spine MRI",
    "Knee MRI",
    "CT Scan Head",
    "CT Scan Abdomen",
    "Colonoscopy",
    "Upper Endoscopy",
    "Total Knee Replacement",
    "Total Hip Replacement",
    "Cataract Surgery",
    "Cardiac Catheterization",
    "Coronary Angioplasty with Stent",
    "Shoulder Arthroscopy",
    "Spinal Fusion",
    "Sleep Study (Polysomnography)",
    "PET Scan",
    "CPAP/BiPAP for Sleep Apnea",
    "Bariatric Surgery",
    "Epidural Steroid Injection",
    "Physical Therapy (outpatient)",
]


async def main():
    parser = argparse.ArgumentParser(description="Seed commercial payer policies")
    parser.add_argument("--payer", type=str, help="Only research for this payer")
    parser.add_argument("--procedure", type=str, help="Only research this procedure")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be researched")
    parser.add_argument("--embed", action="store_true", help="Embed after research")
    args = parser.parse_args()

    payers = [args.payer] if args.payer else PAYERS
    procedures = [args.procedure] if args.procedure else COMMON_PROCEDURES

    pairs = [(p, proc) for p in payers for proc in procedures]
    print(f"Will research {len(pairs)} payer/procedure combinations")

    if args.dry_run:
        for payer, proc in pairs:
            print(f"  {payer}: {proc}")
        return

    from app.config import load_settings
    from app.database import init_pool, get_pool, get_connection
    from app.core.services.payer_policy_research import research_payer_policy

    settings = load_settings()
    await init_pool(settings.database_url)
    pool = await get_pool()

    async with get_connection() as conn:
        success = 0
        failed = 0

        for i, (payer, proc) in enumerate(pairs):
            print(f"[{i+1}/{len(pairs)}] Researching {payer}: {proc}...")
            try:
                result = await research_payer_policy(payer, proc, conn)
                if result:
                    print(f"  -> {result.get('policy_title', 'OK')}")
                    success += 1
                else:
                    print(f"  -> No result")
                    failed += 1
            except Exception as e:
                print(f"  -> Error: {e}")
                failed += 1

            # Brief pause between Gemini calls
            if i < len(pairs) - 1:
                await asyncio.sleep(1)

        print(f"\nResults: {success} succeeded, {failed} failed out of {len(pairs)} total")

        if args.embed:
            print("\nEmbedding policies...")
            from app.core.services.payer_policy_embedding_pipeline import embed_updated_policies
            count = await embed_updated_policies(conn)
            print(f"Embedded {count} policies")

    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
