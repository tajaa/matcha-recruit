Research and write labor compliance data for jurisdictions in a given state. Covers 12 categories: minimum_wage, overtime, sick_leave, leave, meal_breaks, final_pay, pay_frequency, scheduling_reporting, workers_comp, workplace_safety, anti_discrimination, minor_work_permit.

Parse `$ARGUMENTS` for:
- `--state <ST>` (required) — two-letter state code
- `--category <slug>` (optional) — only fill one category within the group
- `--list` — just show gaps, don't research
- `--dry-run` — research but don't write to DB

---

## Step 1: Load regulation keys for labor categories

```bash
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python -c "
import asyncio, asyncpg, os, json
from dotenv import load_dotenv
load_dotenv()
async def main():
    conn = await asyncpg.connect(os.environ['DATABASE_URL'])
    cat_filter = '<CATEGORY>'  # empty string or specific category slug
    q = '''
        SELECT rkd.id, rkd.key, rkd.name, rkd.category_slug, rkd.enforcing_agency, rkd.state_variance
        FROM regulation_key_definitions rkd
        JOIN compliance_categories cc ON cc.id = rkd.category_id
        WHERE cc.\"group\" = 'labor'
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

Replace `<CATEGORY>` with the `--category` value or empty string for all.

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

Research each missing category per state. **Labor laws vary significantly by state — most states have their own versions that differ from federal FLSA.**

### Search patterns per category

| Category | Search queries |
|----------|---------------|
| `minimum_wage` | `"<state> minimum wage 2025 2026 current rate"`, `"<state> tipped minimum wage"` |
| `overtime` | `"<state> overtime law requirements beyond FLSA"`, `"<state> daily overtime"` |
| `sick_leave` | `"<state> paid sick leave law requirements"`, `"<state> earned sick time act"` |
| `leave` | `"<state> family medical leave law beyond FMLA"`, `"<state> paid family leave"` |
| `meal_breaks` | `"<state> meal break rest period requirements"`, `"<state> labor code breaks"` |
| `final_pay` | `"<state> final paycheck timing requirements"`, `"<state> last pay upon termination"` |
| `pay_frequency` | `"<state> pay frequency requirements law"`, `"<state> payday requirements"` |
| `scheduling_reporting` | `"<state> predictive scheduling law"`, `"<state> reporting time pay"` |
| `workers_comp` | `"<state> workers compensation requirements"`, `"<state> workers comp insurance law"` |
| `workplace_safety` | `"<state> OSHA state plan requirements"`, `"<state> workplace safety regulations beyond federal"` |
| `anti_discrimination` | `"<state> anti discrimination employment law protected classes"`, `"<state> fair employment practices"` |
| `minor_work_permit` | `"<state> minor work permit child labor requirements"`, `"<state> youth employment restrictions"` |

**Batch multiple WebSearch calls in parallel.**

### Critical rules

1. **ONLY capture where state DIFFERS FROM or EXCEEDS federal baseline** (FLSA, federal OSHA, Title VII)
2. `jurisdiction_level` must be `state` or `city` — NEVER `federal`
3. If a state has NO additional requirements beyond federal for a category, skip it
4. Labor is the highest-variance group — most states WILL have specific laws

### What to capture per key

- **title**: Descriptive title
- **description**: 2-3 sentences on what the state requires beyond federal
- **current_value**: Brief value (e.g. "$16.00/hr", "7 days accrual", "Daily overtime after 8 hours")
- **numeric_value**: Number if applicable (wage rate, days, hours)
- **effective_date**: YYYY-MM-DD
- **source_url**: Official state labor department URL
- **source_name**: Agency name
- **requires_written_policy**: true if employer must maintain written policy

If `--dry-run`, write markdown to `server/scripts/<state>_labor_gaps.md` and stop.

## Step 4: Write to database

Use the same UPSERT pattern as `/fill-gaps-environmental_compliance`. For each entry:

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
3. Link: `https://hey-matcha.com/admin/jurisdiction-data`
