Research authoritative penalty/fine data for all compliance categories and write to the database.

No arguments needed — this skill auto-discovers categories without penalty data and enriches them.

---

## Step 1: Discover what needs penalty data

Query the database to find categories missing penalty information. Use the app container or local DB:

```bash
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python -c "
import asyncio, asyncpg, os
async def main():
    conn = await asyncpg.connect(os.environ.get('DATABASE_URL', 'postgresql://matcha:matcha_dev@localhost:5432/matcha'))
    rows = await conn.fetch('''
        SELECT category, COUNT(*) as total,
               SUM(CASE WHEN metadata ? '\''penalties'\'' THEN 1 ELSE 0 END) as has_penalty
        FROM jurisdiction_requirements WHERE status = '\''active'\''
        GROUP BY category ORDER BY total DESC
    ''')
    for r in rows:
        pct = (r['has_penalty'] / r['total'] * 100) if r['total'] > 0 else 0
        print(f\"{r['category']}|{r['total']}|{r['has_penalty']}|{pct:.0f}%\")
    await conn.close()
asyncio.run(main())
"
```

## Step 2: Query structured APIs first (most authoritative)

### 2a. Federal Register API — Statutory penalty ranges

The Federal Register API is the legal authority for current inflation-adjusted penalty amounts. Every January, agencies publish Civil Monetary Penalty Inflation Adjustment notices.

Use **WebFetch** to query:

```
https://www.federalregister.gov/api/v1/documents.json?conditions[term]=%22civil+monetary+penalties+inflation+adjustment%22&conditions[agencies][]=health-and-human-services-department&conditions[type][]=RULE&per_page=5&order=newest
```

Also query for DOL/OSHA:
```
https://www.federalregister.gov/api/v1/documents.json?conditions[term]=%22civil+penalties+inflation+adjustment%22&conditions[agencies][]=labor-department&conditions[type][]=RULE&per_page=5&order=newest
```

And for EPA:
```
https://www.federalregister.gov/api/v1/documents.json?conditions[term]=%22civil+monetary+penalty+inflation+adjustment%22&conditions[agencies][]=environmental-protection-agency&conditions[type][]=RULE&per_page=5&order=newest
```

From each result, fetch the document URL and extract the updated penalty amounts. These are the **legally binding** current figures.

### 2b. OSHA Enforcement API — Real penalty data

The DOL OSHA API provides actual enforcement data with penalty amounts:

```
https://enforcedata.dol.gov/api/osha_inspection?limit=100&columns=activity_nr,estab_name,open_date,total_current_penalty,violation_type&sort=-total_current_penalty
```

Use this to get **real penalty ranges** (what's actually being assessed, not just statutory maximums). Calculate min/median/max from recent inspections for the `workplace_safety` category.

### 2c. HHS OCR Resolution Agreements

Fetch from the OCR breach portal for HIPAA settlement amounts:
```
https://ocrportal.hhs.gov/ocr/breach/breach_report.jsf
```
This may not have a clean API — fall back to WebSearch: `site:hhs.gov "resolution agreement" hipaa 2024 2025`

### 2d. OIG CMP Amounts

WebFetch the OIG CMP page:
```
https://oig.hhs.gov/fraud/enforcement/cmp/
```

## Step 3: Web search for remaining categories

After API data, use **WebSearch** for categories not covered by APIs. For each category:

1. Look up `enforcing_agency` and `authority_sources` from `server/app/core/compliance_registry.py` (read the file to find them)
2. Search the agency's enforcement/penalty page directly:
   - `site:osha.gov/penalties 2025` (OSHA)
   - `site:hhs.gov hipaa enforcement penalty amounts` (HIPAA)
   - `site:dol.gov/agencies/whd/penalties` (FLSA/FMLA)
   - `site:oig.hhs.gov civil-monetary-penalties` (OIG)
   - `site:cms.gov civil-monetary-penalties` (CMS)
   - `site:deadiversion.usdoj.gov penalties` (DEA)
   - `site:fda.gov regulatory-information penalties` (FDA)
   - `site:epa.gov enforcement civil-penalty` (EPA)
   - `site:eeoc.gov remedies discrimination` (EEOC)
3. For state-specific penalties: `"<state> labor department penalties <category> 2025"`

### Data to capture per category

```json
{
  "enforcing_agency": "Agency Name",
  "civil_penalty_min": 137,
  "civil_penalty_max": 2067813,
  "per_violation": true,
  "annual_cap": 2067813,
  "criminal": "Description or null",
  "summary": "$137–$2.07M per violation (4 tiers); annual cap $2.07M per category",
  "source_url": "https://federalregister.gov/...",
  "verified_date": "2026-03-25"
}
```

### Verification rules

- **Prefer Federal Register API data** over agency websites (it's the legal authority)
- **Use 2025/2026 inflation-adjusted amounts** — reject anything pre-2024 without flagging it
- **Cross-check**: If API data and agency website differ, note both and prefer the Federal Register
- **Always record the source_url** where the amount was found
- **Distinguish per-violation vs aggregate** — this matters enormously for risk calculation

### Category priority order

**Tier 1 — Federal healthcare:**
`hipaa_privacy`, `billing_integrity`, `clinical_safety`, `corporate_integrity`, `cybersecurity`, `pharmacy_drugs`, `radiation_safety`

**Tier 2 — Labor/employment:**
`minimum_wage`, `overtime`, `workplace_safety`, `anti_discrimination`, `leave`, `sick_leave`, `workers_comp`, `meal_breaks`

**Tier 3 — Remaining:**
`emergency_preparedness`, `telehealth`, `medical_devices`, `language_access`, `records_retention`, `marketing_comms`, `tax_exempt`, `transplant_organ`, `antitrust`, `emerging_regulatory`, `health_it`, `quality_reporting`, plus any manufacturing/oncology categories

## Step 4: Write verified data to the database

For each category where penalty data was found, update `metadata.penalties` on all active requirements in that category:

```python
import asyncio, asyncpg, os, json

async def update_category(category, penalty_data):
    conn = await asyncpg.connect(os.environ.get('DATABASE_URL'))
    result = await conn.execute(
        """UPDATE jurisdiction_requirements
        SET metadata = COALESCE(metadata, '{}'::jsonb) || $1::jsonb, updated_at = NOW()
        WHERE category = $2 AND status = 'active'
          AND (metadata IS NULL OR NOT (metadata ? 'penalties'))""",
        json.dumps({"penalties": penalty_data}),
        category,
    )
    count = int(result.split()[-1])
    print(f"  {category}: updated {count} requirements")
    await conn.close()
    return count
```

Federal-level penalties apply to ALL requirements in that category (same enforcing agency regardless of jurisdiction). State-specific penalties should only be applied to requirements in that state's jurisdiction.

## Step 5: Re-embed affected requirements

After all updates, re-embed so penalty text is searchable via RAG:

```bash
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python -c "
import asyncio
from app.config import load_settings
from app.database import init_pool, close_pool, get_pool
from app.core.services.compliance_embedding_pipeline import embed_requirements
load_settings()
async def main():
    await init_pool()
    pool = get_pool()
    async with pool.acquire() as conn:
        count = await embed_requirements(conn)
        print(f'Re-embedded {count} requirements')
    await close_pool()
asyncio.run(main())
"
```

## Step 6: Report results

For each category, report:
1. Category name + enforcing agency
2. Penalty summary (the one-liner with dollar amounts)
3. **Source**: URL where the data was found (Federal Register, agency site, etc.)
4. **Verified date**: When the amount was confirmed current
5. Requirements updated count

At the end:
- Overall coverage: X of 52 categories now have penalty data
- Any categories where no authoritative penalty data could be found
- Flag any amounts that are pre-2024 and may need refresh
