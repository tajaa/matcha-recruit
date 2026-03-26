Research and write medical compliance data for jurisdictions in a given state. Covers 17 categories: health_it, quality_reporting, cybersecurity, environmental_safety, pharmacy_drugs, payer_relations, reproductive_behavioral, pediatric_vulnerable, telehealth, medical_devices, transplant_organ, antitrust, tax_exempt, language_access, records_retention, marketing_comms, emerging_regulatory.

Parse `$ARGUMENTS` for:
- `--state <ST>` (required) — two-letter state code
- `--category <slug>` (optional) — only fill one category within the group
- `--list` — just show gaps, don't research
- `--dry-run` — research but don't write to DB

---

## Step 1: Load regulation keys for medical compliance categories

```bash
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python -c "
import asyncio, asyncpg, os, json
from dotenv import load_dotenv
load_dotenv()
async def main():
    conn = await asyncpg.connect(os.environ['DATABASE_URL'])
    cat_filter = '<CATEGORY>'
    q = '''
        SELECT rkd.id, rkd.key, rkd.name, rkd.category_slug, rkd.enforcing_agency, rkd.state_variance
        FROM regulation_key_definitions rkd
        JOIN compliance_categories cc ON cc.id = rkd.category_id
        WHERE cc.\"group\" = 'medical_compliance'
    '''
    params = []
    if cat_filter:
        q += ' AND rkd.category_slug = \$1'
        params.append(cat_filter)
    q += ' ORDER BY rkd.category_slug, rkd.key'
    rows = await conn.fetch(q, *params)
    by_cat = {}
    for r in rows:
        cat = r['category_slug']
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append({'id': str(r['id']), 'key': r['key'], 'name': r['name'], 'agency': r['enforcing_agency'], 'variance': r['state_variance']})
    for cat, keys in by_cat.items():
        print(f'CATEGORY:{cat}:{len(keys)}')
        for k in keys:
            print(json.dumps(k))
    print(f'TOTAL_KEYS:{len(rows)}')
    await conn.close()
asyncio.run(main())
"
```

## Step 2: Find jurisdictions and check existing coverage

Same pattern as `/fill-gaps-labor` Step 2. Query jurisdictions in `--state`, check which medical compliance categories already have data.

If `--list`, report and stop.

## Step 3: Research via WebSearch

Medical compliance spans many specialized domains. **Many of these are primarily federal but states add layers — especially telehealth, pharmacy, cybersecurity, and reproductive health.**

### Search patterns per category

| Category | Search queries |
|----------|---------------|
| `telehealth` | `"<state> telehealth law requirements"`, `"<state> telemedicine prescribing rules"`, `"<state> interstate telehealth compact"` |
| `cybersecurity` | `"<state> health data breach notification law"`, `"<state> cybersecurity requirements healthcare"`, `"<state> data protection act"` |
| `pharmacy_drugs` | `"<state> pharmacy board requirements"`, `"<state> controlled substance prescribing law"`, `"<state> PDMP prescription drug monitoring"` |
| `health_it` | `"<state> health information exchange requirements"`, `"<state> electronic health records law"`, `"<state> interoperability mandate"` |
| `quality_reporting` | `"<state> hospital quality reporting requirements"`, `"<state> healthcare quality measures"`, `"<state> adverse event reporting mandatory"` |
| `medical_devices` | `"<state> medical device requirements beyond FDA"`, `"<state> radiation-emitting device registration"` |
| `reproductive_behavioral` | `"<state> reproductive health law"`, `"<state> mental health parity requirements"`, `"<state> behavioral health regulations"` |
| `pediatric_vulnerable` | `"<state> child abuse mandatory reporting healthcare"`, `"<state> pediatric care requirements"`, `"<state> elder abuse reporting"` |
| `payer_relations` | `"<state> insurance commissioner healthcare"`, `"<state> provider network adequacy requirements"`, `"<state> prior authorization reform law"` |
| `language_access` | `"<state> language access healthcare requirements"`, `"<state> interpreter services medical law"` |
| `records_retention` | `"<state> medical records retention requirements"`, `"<state> health records keeping period"` |
| `marketing_comms` | `"<state> healthcare advertising law"`, `"<state> physician marketing restrictions"` |
| `emerging_regulatory` | `"<state> AI healthcare regulation"`, `"<state> health equity law"`, `"<state> social determinants of health mandate"` |
| `environmental_safety` | `"<state> healthcare facility environmental requirements"`, `"<state> medical waste management law"` |
| `antitrust` | `"<state> healthcare antitrust enforcement"`, `"<state> certificate of need law"` |
| `tax_exempt` | `"<state> nonprofit hospital tax exemption requirements"`, `"<state> community benefit requirements"` |
| `transplant_organ` | `"<state> organ donation law"`, `"<state> anatomical gift act"` |

**Batch multiple WebSearch calls in parallel.**

### Critical rules

1. **ONLY capture where state DIFFERS FROM or EXCEEDS federal baseline**
2. `jurisdiction_level` must be `state` or `city` — NEVER `federal`
3. Telehealth, pharmacy, cybersecurity, and reproductive health have the MOST state variance
4. Some categories (antitrust, tax_exempt) may be mostly federal — skip if no state-specific laws

### What to capture per key

Same fields as `/fill-gaps-labor`: title, description, current_value, effective_date, source_url, source_name, requires_written_policy, jurisdiction_level, jurisdiction_name.

If `--dry-run`, write markdown to `server/scripts/<state>_medical_compliance_gaps.md` and stop.

## Step 4: Write to database

Same UPSERT pattern as `/fill-gaps-labor` Step 4. Set `category` to the appropriate medical compliance category slug per entry.

**For state-level requirements, write a row for EACH jurisdiction in that state.**

## Step 5: Report results

1. Per category: keys filled vs skipped (federal-only)
2. Total jurisdiction_requirements created/updated
3. Link: `https://hey-matcha.com/admin/jurisdiction-data`
