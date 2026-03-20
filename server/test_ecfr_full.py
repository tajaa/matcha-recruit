"""Full eCFR test — fetches all 97 CFR parts and shows exact requirement keys.

Run from server/:
  python test_ecfr_full.py

Output shows every requirement that would be inserted/updated in the DB,
with the exact requirement_key computed by _compute_requirement_key.
"""

import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))


async def main():
    from uuid import uuid4
    from app.core.services.government_apis.ecfr import fetch_ecfr_requirements
    from app.core.services.compliance_service import _compute_requirement_key

    print("Full eCFR Test — all 97 CFR parts")
    print("=" * 60)
    print("Fetching... (takes ~60s due to per-request delays)\n")

    t0 = time.time()
    results = []
    async for event in fetch_ecfr_requirements(uuid4()):
        etype = event.get("type")
        msg = event.get("message", "")
        if etype == "ecfr_done":
            results = event.get("results", [])
        elif msg:
            print(f"  [{etype}] {msg}")

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s — {len(results)} requirements\n")

    # Compute keys and group by category
    by_cat: dict = {}
    for req in results:
        key = _compute_requirement_key(req)
        cat = req["category"]
        by_cat.setdefault(cat, []).append({
            "key": key,
            "title": req["title"],
            "current_value": req.get("current_value", ""),
            "source_url": req.get("source_url", ""),
        })

    # Print grouped output
    print(f"{'='*60}")
    print(f"REQUIREMENTS BY CATEGORY ({len(by_cat)} categories, {len(results)} total)")
    print(f"{'='*60}\n")

    all_keys = []
    for cat in sorted(by_cat.keys()):
        reqs = by_cat[cat]
        print(f"[{cat}]  ({len(reqs)} parts)")
        for r in reqs:
            print(f"  key:   {r['key']}")
            print(f"  title: {r['title']}")
            print(f"  value: {r['current_value']}")
            print(f"  url:   {r['source_url']}")
            all_keys.append(r["key"])
        print()

    # Summary
    print(f"{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Total requirements:  {len(results)}")
    print(f"Categories covered:  {len(by_cat)}")
    print(f"Unique keys:         {len(set(all_keys))}")

    dupes = [k for k in all_keys if all_keys.count(k) > 1]
    if dupes:
        print(f"\nDUPLICATE KEYS (would upsert same row):")
        for k in sorted(set(dupes)):
            print(f"  {k}")
    else:
        print(f"Duplicate keys:      0 (all unique)")

    # Write keys to file
    outfile = os.path.join(os.path.dirname(__file__), "test_ecfr_full_output.txt")
    with open(outfile, "w") as f:
        f.write(f"Full eCFR Test Output\n")
        f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total: {len(results)} requirements across {len(by_cat)} categories\n")
        f.write(f"{'='*60}\n\n")
        for cat in sorted(by_cat.keys()):
            reqs = by_cat[cat]
            f.write(f"[{cat}]  ({len(reqs)} parts)\n")
            for r in reqs:
                f.write(f"  key:   {r['key']}\n")
                f.write(f"  title: {r['title']}\n")
                f.write(f"  value: {r['current_value']}\n")
                f.write(f"  url:   {r['source_url']}\n")
            f.write("\n")
        f.write(f"{'='*60}\n")
        f.write(f"ALL KEYS (for DB comparison):\n")
        for k in sorted(set(all_keys)):
            f.write(f"  {k}\n")

    print(f"\nFull output written to: test_ecfr_full_output.txt")


if __name__ == "__main__":
    asyncio.run(main())
