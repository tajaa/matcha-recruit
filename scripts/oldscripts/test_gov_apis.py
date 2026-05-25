"""
Quick test script to see if we get usable data from government APIs.

Usage:
    python scripts/test_gov_apis.py

Set CONGRESS_API_KEY env var for Congress.gov (optional - skips if missing).
"""

import json
import os
import sys
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError

TIMEOUT = 15  # seconds


def fetch_json(url, headers=None):
    req = Request(url)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def divider(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


# ---------------------------------------------------------------------------
# 1. Federal Register API — Recent final rules from DOL, OSHA, CMS, EEOC
# ---------------------------------------------------------------------------
def test_federal_register_documents():
    divider("Federal Register API — Recent Final Rules")

    agencies = [
        "labor-department",
        "occupational-safety-and-health-administration",
        "centers-for-medicare-medicaid-services",
        "equal-employment-opportunity-commission",
        "wage-and-hour-division",
    ]

    thirty_days_ago = (datetime.now() - timedelta(days=365)).strftime("%m/%d/%Y")

    params = urlencode({
        "per_page": 5,
        "order": "newest",
        "conditions[type][]": "RULE",
        "conditions[publication_date][gte]": thirty_days_ago,
    }, doseq=False)

    # Federal Register wants repeated keys for agencies
    agency_params = "&".join(
        f"conditions[agencies][]={a}" for a in agencies
    )

    url = f"https://www.federalregister.gov/api/v1/documents.json?{params}&{agency_params}"
    print(f"URL: {url[:120]}...\n")

    try:
        data = fetch_json(url)
        print(f"Total results: {data.get('count', '?')}")
        print(f"Results returned: {len(data.get('results', []))}\n")

        for doc in data.get("results", [])[:5]:
            print(f"  Title:          {doc.get('title', 'N/A')[:90]}")
            print(f"  Type:           {doc.get('type', 'N/A')}")
            print(f"  Agency:         {', '.join(a['name'] for a in doc.get('agencies', []))}")
            print(f"  Published:      {doc.get('publication_date', 'N/A')}")
            print(f"  Effective:      {doc.get('effective_on', 'N/A')}")
            print(f"  CFR refs:       {doc.get('cfr_references', [])}")
            print(f"  Abstract:       {(doc.get('abstract') or 'N/A')[:120]}")
            print(f"  URL:            {doc.get('html_url', 'N/A')}")
            print(f"  Document #:     {doc.get('document_number', 'N/A')}")
            print()

        return True
    except (HTTPError, URLError, Exception) as e:
        print(f"  FAILED: {e}")
        return False


# ---------------------------------------------------------------------------
# 2. Federal Register API — Public Inspection Documents (pre-publication)
# ---------------------------------------------------------------------------
def test_federal_register_public_inspection():
    divider("Federal Register API — Public Inspection (Pre-Publication)")

    url = "https://www.federalregister.gov/api/v1/public-inspection-documents/current.json"
    print(f"URL: {url}\n")

    try:
        data = fetch_json(url)
        count = data.get("count", len(data.get("results", [])))
        print(f"Documents on public inspection today: {count}\n")

        for doc in data.get("results", [])[:5]:
            print(f"  Title:          {doc.get('title', 'N/A')[:90]}")
            print(f"  Type:           {doc.get('type', 'N/A')}")
            print(f"  Agency:         {', '.join(a.get('name', '?') for a in doc.get('agencies', []))}")
            print(f"  Filed:          {doc.get('filed_at', 'N/A')}")
            print(f"  Pub date:       {doc.get('publication_date', 'N/A')}")
            print(f"  Doc #:          {doc.get('document_number', 'N/A')}")
            print(f"  PDF:            {doc.get('pdf_url', 'N/A')}")
            print()

        return True
    except (HTTPError, URLError, Exception) as e:
        print(f"  FAILED: {e}")
        return False


# ---------------------------------------------------------------------------
# 3. Federal Register API — Proposed rules (upcoming regulation changes)
# ---------------------------------------------------------------------------
def test_federal_register_proposed_rules():
    divider("Federal Register API — Proposed Rules (Upcoming Changes)")

    agencies = [
        "labor-department",
        "occupational-safety-and-health-administration",
        "centers-for-medicare-medicaid-services",
    ]

    agency_params = "&".join(f"conditions[agencies][]={a}" for a in agencies)
    url = (
        f"https://www.federalregister.gov/api/v1/documents.json"
        f"?per_page=5&order=newest&conditions[type][]=PRORULE&{agency_params}"
    )
    print(f"URL: {url[:120]}...\n")

    try:
        data = fetch_json(url)
        print(f"Total proposed rules: {data.get('count', '?')}\n")

        for doc in data.get("results", [])[:5]:
            print(f"  Title:          {doc.get('title', 'N/A')[:90]}")
            print(f"  Agency:         {', '.join(a.get('name', a.get('raw_name', '?')) for a in doc.get('agencies', []))}")
            print(f"  Published:      {doc.get('publication_date', 'N/A')}")
            print(f"  Comment end:    {doc.get('comments_close_on', 'N/A')}")
            print(f"  Abstract:       {(doc.get('abstract') or 'N/A')[:120]}")
            print(f"  URL:            {doc.get('html_url', 'N/A')}")
            print()

        return True
    except (HTTPError, URLError, Exception) as e:
        print(f"  FAILED: {e}")
        return False


# ---------------------------------------------------------------------------
# 4. Congress.gov API — Recent employment/labor bills
# ---------------------------------------------------------------------------
def test_congress_api():
    divider("Congress.gov API — Recent Employment Bills")

    api_key = os.environ.get("CONGRESS_API_KEY", "")
    if not api_key:
        print("  SKIPPED: Set CONGRESS_API_KEY env var to test")
        print("  Get a free key at: https://api.congress.gov/sign-up/")
        return None

    url = (
        f"https://api.congress.gov/v3/bill"
        f"?limit=5&sort=updateDate+desc&api_key={api_key}"
    )
    print(f"URL: (api key redacted)\n")

    try:
        data = fetch_json(url)
        bills = data.get("bills", [])
        print(f"Bills returned: {len(bills)}\n")

        for bill in bills[:5]:
            print(f"  Title:          {bill.get('title', 'N/A')[:90]}")
            print(f"  Number:         {bill.get('number', 'N/A')}")
            print(f"  Type:           {bill.get('type', 'N/A')}")
            print(f"  Congress:       {bill.get('congress', 'N/A')}")
            print(f"  Updated:        {bill.get('updateDate', 'N/A')}")
            print(f"  Latest action:  {bill.get('latestAction', {}).get('text', 'N/A')[:90]}")
            print(f"  URL:            {bill.get('url', 'N/A')}")
            print()

        return True
    except (HTTPError, URLError, Exception) as e:
        print(f"  FAILED: {e}")
        return False


# ---------------------------------------------------------------------------
# 5. CMS Data — State Waivers / Medicaid data
# ---------------------------------------------------------------------------
def test_cms_data():
    divider("CMS Data — Available Datasets & Medicaid")

    endpoints = [
        (
            "CMS Provider Data — Dataset Catalog",
            "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items?limit=5",
            lambda data: _print_cms_catalog(data),
        ),
        (
            "Medicaid.gov — State Overviews",
            "https://data.medicaid.gov/resource/wek2-v2gd.json?$limit=5",
            lambda data: _print_generic_records(data),
        ),
        (
            "Medicaid.gov — State Drug Utilization",
            "https://data.medicaid.gov/resource/va5y-jhsv.json?$limit=5&$order=utilization_type",
            lambda data: _print_generic_records(data),
        ),
    ]

    any_success = False
    for name, url, printer in endpoints:
        print(f"  --- {name} ---")
        print(f"  URL: {url[:100]}...\n")
        try:
            data = fetch_json(url)
            print(f"  Records returned: {len(data)}\n")
            printer(data)
            any_success = True
        except (HTTPError, URLError, Exception) as e:
            print(f"  FAILED: {e}\n")

    return any_success


def _print_cms_catalog(data):
    for ds in data[:3]:
        print(f"    Title:       {ds.get('title', 'N/A')[:90]}")
        print(f"    Modified:    {ds.get('modified', 'N/A')}")
        desc = ds.get('description', 'N/A')
        if isinstance(desc, str):
            print(f"    Description: {desc[:120]}")
        print()


def _print_generic_records(data):
    for rec in data[:3]:
        for key in list(rec.keys())[:6]:
            val = str(rec[key])[:90]
            print(f"    {key:22s}: {val}")
        print()


# ---------------------------------------------------------------------------
# 6. OSHA — Standards search (no formal API, test what's available)
# ---------------------------------------------------------------------------
def test_osha():
    divider("OSHA — Standards (via Federal Register filter)")

    # OSHA doesn't have a standalone API, but Federal Register covers their rulemaking
    url = (
        "https://www.federalregister.gov/api/v1/documents.json"
        "?per_page=5&order=newest"
        "&conditions[agencies][]=occupational-safety-and-health-administration"
    )
    print(f"Using Federal Register filtered to OSHA agency\n")
    print(f"URL: {url[:120]}...\n")

    try:
        data = fetch_json(url)
        print(f"Total OSHA documents: {data.get('count', '?')}\n")

        for doc in data.get("results", [])[:5]:
            print(f"  Title:          {doc.get('title', 'N/A')[:90]}")
            print(f"  Type:           {doc.get('type', 'N/A')}")
            print(f"  Published:      {doc.get('publication_date', 'N/A')}")
            print(f"  Effective:      {doc.get('effective_on', 'N/A')}")
            print(f"  CFR refs:       {doc.get('cfr_references', [])}")
            print(f"  URL:            {doc.get('html_url', 'N/A')}")
            print()

        return True
    except (HTTPError, URLError, Exception) as e:
        print(f"  FAILED: {e}")
        return False


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Government API Probe — Testing data availability")
    print(f"Timestamp: {datetime.now().isoformat()}")

    results = {}
    tests = [
        ("Federal Register — Final Rules", test_federal_register_documents),
        ("Federal Register — Public Inspection", test_federal_register_public_inspection),
        ("Federal Register — Proposed Rules", test_federal_register_proposed_rules),
        ("Congress.gov", test_congress_api),
        ("CMS Data", test_cms_data),
        ("OSHA (via Fed Register)", test_osha),
    ]

    for name, fn in tests:
        try:
            results[name] = fn()
        except Exception as e:
            print(f"  UNEXPECTED ERROR: {e}")
            results[name] = False

    # Summary
    divider("SUMMARY")
    for name, result in results.items():
        if result is True:
            status = "OK — usable data returned"
        elif result is None:
            status = "SKIPPED (missing API key)"
        else:
            status = "FAILED"
        print(f"  {name:45s} {status}")

    print()
    failed = sum(1 for v in results.values() if v is False)
    if failed:
        print(f"{failed} source(s) failed. Check network access or API availability.")
        sys.exit(1)
    else:
        print("All reachable sources returned data.")
