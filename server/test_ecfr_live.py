"""Quick live test of the new government_apis package.

Tests eCFR + Federal Register without a DB connection.
Run from: server/
  python test_ecfr_live.py
"""

import asyncio
import sys
import os

# Add server to path
sys.path.insert(0, os.path.dirname(__file__))


async def test_ecfr_titles():
    """Confirm /titles endpoint returns issue dates for our target titles."""
    import httpx
    from app.core.services.government_apis._base import _ECFR_BASE, _TIMEOUT

    print("\n=== eCFR /titles ===")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_ECFR_BASE}/titles")
        resp.raise_for_status()
        titles = resp.json().get("titles", [])

    target_titles = {21, 26, 29, 40, 42, 45, 10, 13, 16}
    found = {}
    for t in titles:
        num = t.get("number")
        date = t.get("latest_issue_date") or t.get("up_to_date_as_of")
        if num and int(num) in target_titles:
            found[int(num)] = date

    for title_num in sorted(target_titles):
        status = found.get(title_num, "NOT FOUND")
        print(f"  Title {title_num}: {status}")

    assert len(found) >= 5, f"Expected at least 5 target titles, got {len(found)}"
    print(f"  OK: {len(found)}/{len(target_titles)} target titles found")
    return found


async def test_ecfr_one_part(title_num: int, part_num: int, issue_date: str):
    """Test fetching structure + versions for a single CFR part."""
    import httpx
    from app.core.services.government_apis._base import _ECFR_BASE, _TIMEOUT
    from app.core.services.government_apis.ecfr import _parse_structure, _fetch_part_versions

    print(f"\n=== eCFR {title_num} CFR Part {part_num} ===")
    url = f"{_ECFR_BASE}/structure/{issue_date}/title-{title_num}.json?part={part_num}"

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        amendment_date = await _fetch_part_versions(client, title_num, part_num)

    part_label, subpart_labels, subpart_count, section_count = _parse_structure(
        data, title_num, part_num
    )

    print(f"  Part label:    {part_label[:80]}")
    print(f"  Subparts:      {subpart_count}")
    print(f"  Sections:      {section_count}")
    print(f"  Last amended:  {amendment_date}")
    if subpart_labels:
        print(f"  First subpart: {subpart_labels[0][:80]}")
    assert part_label, "Part label should not be empty"


async def test_ecfr_generator_smoke():
    """Run fetch_ecfr_requirements for a small subset and check output shape."""
    from uuid import uuid4
    from app.core.services.government_apis.ecfr import fetch_ecfr_requirements
    from app.core.compliance_registry import CATEGORY_FEDERAL_REGISTER_AGENCIES

    # Temporarily patch registry to just a few categories for speed
    import app.core.services.government_apis.ecfr as ecfr_mod
    original = ecfr_mod.CATEGORY_FEDERAL_REGISTER_AGENCIES

    # Pick 3 categories with known working parts
    test_cats = {
        k: v for k, v in original.items()
        if k in ("overtime", "leave", "hipaa_privacy")
    }
    ecfr_mod.CATEGORY_FEDERAL_REGISTER_AGENCIES = test_cats

    try:
        print(f"\n=== eCFR generator smoke test (3 categories) ===")
        events = []
        results = []
        async for event in fetch_ecfr_requirements(uuid4()):
            events.append(event)
            if event.get("type") == "ecfr_done":
                results = event.get("results", [])
            else:
                print(f"  [{event.get('type')}] {event.get('message', '')}")

        print(f"  Events received: {len(events)}")
        print(f"  Requirements:    {len(results)}")
        for req in results[:5]:
            print(f"    - [{req['category']}] {req['title'][:70]}")
            print(f"       {req['current_value'][:80]}")
        assert len(results) > 0, "Expected at least some eCFR requirements"
        print(f"  OK: {len(results)} requirements generated")
    finally:
        ecfr_mod.CATEGORY_FEDERAL_REGISTER_AGENCIES = original


async def test_cfr_parts_coverage():
    """Show coverage stats for cfr_parts across all 40 categories."""
    from app.core.compliance_registry import CATEGORY_FEDERAL_REGISTER_AGENCIES

    print("\n=== cfr_parts coverage ===")
    total_pairs = 0
    missing = []
    for cat, cfg in sorted(CATEGORY_FEDERAL_REGISTER_AGENCIES.items()):
        cfr_parts = cfg.get("cfr_parts", {})
        pairs = sum(len(parts) for parts in cfr_parts.values())
        total_pairs += pairs
        if not cfr_parts:
            missing.append(cat)

    print(f"  Total (title, part) pairs: {total_pairs}")
    print(f"  Categories with cfr_parts: {len(CATEGORY_FEDERAL_REGISTER_AGENCIES) - len(missing)}/{len(CATEGORY_FEDERAL_REGISTER_AGENCIES)}")
    if missing:
        print(f"  Missing cfr_parts: {missing}")
    else:
        print("  All categories have cfr_parts defined")


async def main():
    print("Government APIs Live Test")
    print("=" * 50)

    # 1. cfr_parts coverage (no network)
    await test_cfr_parts_coverage()

    # 2. eCFR /titles
    title_dates = await test_ecfr_titles()

    # 3. Spot-check a few specific parts
    spot_checks = [
        (29, 541, "overtime - defining FLSA exemptions"),
        (29, 825, "FMLA leave"),
        (45, 164, "HIPAA security"),
    ]
    for title_num, part_num, desc in spot_checks:
        date = title_dates.get(title_num)
        if date:
            await test_ecfr_one_part(title_num, part_num, date)
        else:
            print(f"\n  SKIP: Title {title_num} date not available")

    # 4. Generator smoke test (fetches real data for 3 categories)
    await test_ecfr_generator_smoke()

    print("\n" + "=" * 50)
    print("All tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
