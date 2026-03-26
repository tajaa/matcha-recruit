Research and write healthcare compliance data for jurisdictions in a given state. Covers 9 categories: hipaa_privacy, clinical_safety, billing_integrity, corporate_integrity, emergency_preparedness, healthcare_workforce, state_licensing, research_consent, reimbursement_vbc.

Parse `$ARGUMENTS` for:
- `--state <ST>` (required) — two-letter state code
- `--category <slug>` (optional) — only fill one category within the group
- `--list` — just show gaps, don't research
- `--dry-run` — research but don't write to DB

---

## Step 1: Load regulation keys for healthcare categories

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
        WHERE cc.\"group\" = 'healthcare'
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

Same pattern as `/fill-gaps-labor` Step 2. Query jurisdictions in `--state`, check which healthcare categories already have data.

If `--list`, report and stop.

## Step 3: Research via WebSearch

Healthcare compliance is heavily state-regulated. **States often have their own privacy, licensing, staffing, and reporting requirements beyond federal (HIPAA, CMS, EMTALA).**

### Search patterns per category

| Category | Search queries |
|----------|---------------|
| `hipaa_privacy` | `"<state> health privacy law beyond HIPAA"`, `"<state> medical records privacy act"`, `"<state> health information exchange law"` |
| `clinical_safety` | `"<state> nurse staffing ratio requirements"`, `"<state> patient safety act"`, `"<state> hospital adverse event reporting"` |
| `billing_integrity` | `"<state> false claims act healthcare"`, `"<state> surprise billing law"`, `"<state> balance billing protections"` |
| `corporate_integrity` | `"<state> healthcare fraud whistleblower protections"`, `"<state> corporate practice of medicine"` |
| `emergency_preparedness` | `"<state> hospital emergency preparedness requirements"`, `"<state> disaster planning healthcare facilities"` |
| `healthcare_workforce` | `"<state> nurse practitioner scope of practice"`, `"<state> healthcare worker training requirements"`, `"<state> continuing education healthcare"` |
| `state_licensing` | `"<state> healthcare facility licensing requirements"`, `"<state> hospital licensure"`, `"<state> ambulatory surgery center license"` |
| `research_consent` | `"<state> human research subject protections"`, `"<state> informed consent law"`, `"<state> IRB requirements beyond federal"` |
| `reimbursement_vbc` | `"<state> Medicaid reimbursement rates"`, `"<state> value-based care requirements"`, `"<state> all-payer claims database"` |

**Batch multiple WebSearch calls in parallel.**

### Critical rules

1. **ONLY capture where state DIFFERS FROM or EXCEEDS federal baseline** (HIPAA, CMS CoPs, EMTALA, 42 CFR Part 2)
2. `jurisdiction_level` must be `state` or `city` — NEVER `federal`
3. Healthcare is highly state-regulated — most states WILL have specific laws
4. Note state-specific agencies (e.g., CA CDPH, NY DOH, TX HHSC)

### What to capture per key

Same fields as `/fill-gaps-labor`: title, description, current_value, effective_date, source_url, source_name, requires_written_policy, jurisdiction_level, jurisdiction_name.

If `--dry-run`, write markdown to `server/scripts/<state>_healthcare_gaps.md` and stop.

## Step 4: Write to database

Same UPSERT pattern as `/fill-gaps-labor` Step 4. Set `category` to the appropriate healthcare category slug per entry.

**For state-level requirements, write a row for EACH jurisdiction in that state.**

## Step 5: Report results

1. Per category: keys filled vs skipped (federal-only)
2. Total jurisdiction_requirements created/updated
3. Link: `https://hey-matcha.com/admin/jurisdiction-data`
