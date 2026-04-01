Research and write behavioral health compliance data for jurisdictions in a given state. Covers 7 categories across two groups: reproductive_behavioral (medical_compliance group), clinical_safety, state_licensing, healthcare_workforce, hipaa_privacy, corporate_integrity, quality_reporting (healthcare group).

Parse `$ARGUMENTS` for:
- `--state <ST>` (required) — two-letter state code
- `--category <slug>` (optional) — only fill one of the 7 categories
- `--list` — just show gaps, don't research
- `--dry-run` — research but don't write to DB

---

## Step 1: Load regulation keys for all behavioral health categories

The 7 behavioral health categories span TWO compliance groups (healthcare + medical_compliance). Load keys from both:

```bash
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python -c "
import asyncio, asyncpg, os, json
from dotenv import load_dotenv
load_dotenv()

BH_CATEGORIES = [
    'reproductive_behavioral',  # medical_compliance group
    'clinical_safety',          # healthcare group
    'state_licensing',          # healthcare group
    'healthcare_workforce',     # healthcare group
    'hipaa_privacy',            # healthcare group
    'corporate_integrity',      # healthcare group
    'quality_reporting',        # medical_compliance group
]

async def main():
    conn = await asyncpg.connect(os.environ['DATABASE_URL'])
    cat_filter = '<CATEGORY>'
    cats = [cat_filter] if cat_filter else BH_CATEGORIES
    q = '''
        SELECT rkd.id, rkd.key, rkd.name, rkd.category_slug, rkd.enforcing_agency, rkd.state_variance
        FROM regulation_key_definitions rkd
        WHERE rkd.category_slug = ANY(\$1)
        ORDER BY rkd.category_slug, rkd.key
    '''
    rows = await conn.fetch(q, cats)
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

Replace `<CATEGORY>` with the `--category` value or empty string for all 7 categories.

## Step 2: Find jurisdictions and check existing coverage

```bash
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python -c "
import asyncio, asyncpg, os, json
from dotenv import load_dotenv
load_dotenv()
async def main():
    conn = await asyncpg.connect(os.environ['DATABASE_URL'])
    jurisdictions = await conn.fetch('''
        SELECT j.id, j.city, j.state, j.county
        FROM jurisdictions j WHERE j.state = \$1
        ORDER BY j.city NULLS FIRST
    ''', '<STATE>')
    cats = [<CATEGORY_LIST>]  # list of category slugs from Step 1
    for j in jurisdictions:
        existing = await conn.fetch('''
            SELECT DISTINCT category FROM jurisdiction_requirements
            WHERE jurisdiction_id = \$1 AND category = ANY(\$2)
        ''', j['id'], cats)
        existing_cats = [r['category'] for r in existing]
        missing = [c for c in cats if c not in existing_cats]
        print(json.dumps({
            'id': str(j['id']), 'city': j['city'] or '(state-level)',
            'state': j['state'], 'missing_categories': missing
        }))
    await conn.close()
asyncio.run(main())
"
```

If `--list` was specified, report gaps and stop.

## Step 3: Research via WebSearch

Behavioral health compliance is heavily state-regulated. **States have their own behavioral health facility licensing, involuntary commitment procedures, SUD treatment rules, and mental health parity requirements that go well beyond federal baselines.**

### Search patterns per category

| Category | Search queries |
|----------|---------------|
| `reproductive_behavioral` | `"<state> mental health parity law requirements"`, `"<state> behavioral health regulations 2025 2026"`, `"<state> substance use disorder treatment regulations"`, `"<state> involuntary commitment procedure 5150 Baker Act"`, `"<state> 42 CFR Part 2 state requirements"`, `"<state> minor consent mental health treatment"` |
| `clinical_safety` | `"<state> seclusion restraint regulations behavioral health"`, `"<state> suicide prevention requirements healthcare facilities"`, `"<state> patient safety reporting behavioral health"`, `"<state> trauma-informed care requirements"` |
| `state_licensing` | `"<state> behavioral health facility licensing requirements"`, `"<state> SUD treatment program certification"`, `"<state> mental health residential facility license"`, `"<state> outpatient behavioral health license"` |
| `healthcare_workforce` | `"<state> LCSW LMFT LPC scope of practice"`, `"<state> behavioral health counselor certification requirements"`, `"<state> peer support specialist certification"`, `"<state> BCBA licensing requirements"`, `"<state> psychiatric nurse practitioner prescribing authority"` |
| `hipaa_privacy` | `"<state> mental health records privacy beyond HIPAA"`, `"<state> psychotherapy notes protections"`, `"<state> substance abuse records confidentiality state law"` |
| `corporate_integrity` | `"<state> behavioral health fraud enforcement"`, `"<state> Medicaid behavioral health billing compliance"`, `"<state> corporate practice of psychology"` |
| `quality_reporting` | `"<state> behavioral health quality measures reporting"`, `"<state> mental health outcome reporting requirements"`, `"<state> HEDIS behavioral health measures state mandate"` |

**Batch multiple WebSearch calls in parallel (up to 5 at a time).**

### Critical rules

1. **ONLY capture where state DIFFERS FROM or EXCEEDS federal baseline** (MHPAEA, 42 CFR Part 2, CMS CoPs, EMTALA, HIPAA)
2. `jurisdiction_level` must be `state` or `city` — NEVER `federal`
3. Behavioral health is HIGH state variance — most states WILL have specific laws
4. Pay special attention to:
   - State behavioral health parity laws that exceed federal MHPAEA
   - State involuntary commitment procedures (5150 in CA, Baker Act in FL, MHL 9.39 in NY)
   - DHCS/OMH/AHCA equivalents per state (the state agency that licenses BH facilities)
   - SUD treatment facility certification beyond SAMHSA
   - Scope of practice variations for LCSW, LMFT, LPC, BCBA, peer support

### What to capture per key

- **title**: Descriptive title of the state requirement
- **description**: 2-3 sentences on what the state requires beyond federal
- **current_value**: Brief value (e.g. "5150/5250 72-hr hold", "DHCS certification required", "SB 855 full parity")
- **numeric_value**: Number if applicable
- **effective_date**: YYYY-MM-DD
- **source_url**: Official state agency URL (DHCS, DOH, etc.)
- **source_name**: Agency name
- **requires_written_policy**: true if facility must maintain written policy

If `--dry-run`, write markdown to `server/scripts/<state>_behavioral_health_gaps.md` and stop.

## Step 4: Write to database

Use the same UPSERT pattern as `/fill-gaps-labor` Step 4. Set `category` to the appropriate category slug per entry.

```bash
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python -c "
import asyncio, asyncpg, os, json
from dotenv import load_dotenv
load_dotenv()

ENTRIES = <ENTRIES_JSON>

async def main():
    conn = await asyncpg.connect(os.environ['DATABASE_URL'])
    inserted = 0
    for e in ENTRIES:
        cat = e['category']
        cat_id = await conn.fetchval(\"SELECT id FROM compliance_categories WHERE slug = \$1 LIMIT 1\", cat)
        requirement_key = f\"{cat}:{e['regulation_key']}\"
        await conn.execute('''
            INSERT INTO jurisdiction_requirements
                (jurisdiction_id, requirement_key, category, jurisdiction_level, jurisdiction_name,
                 title, description, current_value, numeric_value, source_url, source_name,
                 effective_date, last_verified_at, requires_written_policy,
                 regulation_key, key_definition_id, category_id, source_tier)
            VALUES (\$1, \$2, \$3, \$4, \$5, \$6, \$7, \$8, \$9, \$10, \$11, \$12::date, NOW(), \$13,
                    \$14, \$15, \$16, 'tier_3_aggregator'::source_tier_enum)
            ON CONFLICT (jurisdiction_id, requirement_key) DO UPDATE SET
                title = EXCLUDED.title, description = EXCLUDED.description,
                previous_value = jurisdiction_requirements.current_value,
                current_value = EXCLUDED.current_value, numeric_value = EXCLUDED.numeric_value,
                source_url = EXCLUDED.source_url, source_name = EXCLUDED.source_name,
                effective_date = EXCLUDED.effective_date, last_verified_at = NOW(),
                requires_written_policy = EXCLUDED.requires_written_policy,
                regulation_key = EXCLUDED.regulation_key, key_definition_id = EXCLUDED.key_definition_id,
                last_changed_at = CASE WHEN jurisdiction_requirements.current_value IS DISTINCT FROM EXCLUDED.current_value
                    THEN NOW() ELSE jurisdiction_requirements.last_changed_at END,
                source_tier = CASE WHEN EXCLUDED.source_tier < jurisdiction_requirements.source_tier OR jurisdiction_requirements.source_tier IS NULL
                    THEN EXCLUDED.source_tier ELSE jurisdiction_requirements.source_tier END,
                updated_at = NOW()
        ''',
            e['jurisdiction_id'], requirement_key, cat,
            e['jurisdiction_level'], e['jurisdiction_name'],
            e['title'], e['description'], e['current_value'],
            e.get('numeric_value'), e['source_url'], e['source_name'],
            e.get('effective_date'), e.get('requires_written_policy', False),
            e['regulation_key'], e['key_definition_id'], cat_id,
        )
        inserted += 1
        print(f\"  {e['jurisdiction_name']}: {cat}/{e['regulation_key']}\")
    print(f'Inserted/updated {inserted} requirements')
    await conn.close()
asyncio.run(main())
"
```

**For state-level requirements, write a row for EACH jurisdiction in that state.**

## Step 5: Report results

1. Per category: keys filled vs skipped (federal-only)
2. Total jurisdiction_requirements created/updated
3. Summary table:

| Category | Keys Researched | Jurisdictions Updated |
|----------|----------------|----------------------|
| reproductive_behavioral | X | Y |
| clinical_safety | X | Y |
| state_licensing | X | Y |
| healthcare_workforce | X | Y |
| hipaa_privacy | X | Y |
| corporate_integrity | X | Y |
| quality_reporting | X | Y |

4. Link: `https://hey-matcha.com/admin/jurisdiction-data`
