Research and write environmental compliance data for jurisdictions in a given state.

Parse `$ARGUMENTS` for:
- `--state <ST>` (required, e.g. `--state CA`) — two-letter state code
- `--list` — just show gaps, don't research
- `--dry-run` — research but don't write to DB

---

## Step 1: Load the 8 environmental compliance regulation keys

```bash
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python -c "
import asyncio, asyncpg, os, json
from dotenv import load_dotenv
load_dotenv()
async def main():
    conn = await asyncpg.connect(os.environ['DATABASE_URL'])
    rows = await conn.fetch('''
        SELECT id, key, name, enforcing_agency, state_variance, description
        FROM regulation_key_definitions
        WHERE category_slug = '\''environmental_compliance'\''
        ORDER BY key
    ''')
    for r in rows:
        print(json.dumps({
            'id': str(r['id']), 'key': r['key'], 'name': r['name'],
            'agency': r['enforcing_agency'], 'variance': r['state_variance'],
            'description': r['description']
        }))
    print(f'TOTAL:{len(rows)}')
    await conn.close()
asyncio.run(main())
"
```

Save the key list — you'll need the `id` (for `key_definition_id`) and `key` for each.

## Step 2: Find jurisdictions in the target state and check existing coverage

```bash
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python -c "
import asyncio, asyncpg, os, json
from dotenv import load_dotenv
load_dotenv()
async def main():
    conn = await asyncpg.connect(os.environ['DATABASE_URL'])
    jurisdictions = await conn.fetch('''
        SELECT j.id, j.city, j.state, j.county
        FROM jurisdictions j
        WHERE j.state = '\''<STATE>'\''
        ORDER BY j.city NULLS FIRST
    ''')
    for j in jurisdictions:
        existing = await conn.fetch('''
            SELECT regulation_key FROM jurisdiction_requirements
            WHERE jurisdiction_id = \$1 AND category = '\''environmental_compliance'\''
        ''', j['id'])
        existing_keys = [r['regulation_key'] for r in existing]
        print(json.dumps({
            'id': str(j['id']), 'city': j['city'] or '(state-level)',
            'state': j['state'], 'county': j['county'],
            'existing_keys': existing_keys
        }))
    print(f'JURISDICTIONS:{len(jurisdictions)}')
    await conn.close()
asyncio.run(main())
"
```

Replace `<STATE>` with the parsed state code.

If `--list` was specified, report the gaps and stop here.

## Step 3: Research via WebSearch

For each regulation key that's missing across the target state, research using WebSearch. **Environmental compliance is primarily federal (EPA) but states have their own programs, delegated authority, and stricter standards.**

### Research strategy

Most environmental laws are federal with state-delegated implementation. Research what the STATE specifically requires beyond the federal baseline:

| Key | Search queries |
|-----|---------------|
| `cercla_superfund_liability` | `"<state> superfund cleanup program state equivalent"`, `"<state> environmental cleanup liability law"` |
| `clean_air_act_title_v` | `"<state> clean air act title v operating permit program"`, `"<state> air quality management district permits"` |
| `clean_water_act_npdes` | `"<state> NPDES permit program delegated authority"`, `"<state> water discharge permit requirements"` |
| `epa_risk_management_program` | `"<state> risk management program chemical accident prevention"`, `"<state> CalARP" OR "<state> state RMP equivalent"` |
| `epcra_tri_reporting` | `"<state> toxic release inventory reporting requirements"`, `"<state> community right to know hazardous chemical reporting"` |
| `rcra_hazardous_waste` | `"<state> hazardous waste generator requirements RCRA"`, `"<state> hazardous waste management regulations"` |
| `spcc_oil_spill_prevention` | `"<state> oil spill prevention control countermeasure plan"`, `"<state> aboveground storage tank regulations"` |
| `tsca_toxic_substances` | `"<state> toxic substances control requirements"`, `"<state> chemical regulation beyond TSCA"` |
| `clean_water_act_npdes` | `"<state> NPDES permit program"`, `"<state> water pollution discharge permits"` |

**Batch multiple WebSearch calls in parallel** — launch all searches for a state at once.

### What to capture per key

For each key where the state has specific requirements:

- **title**: Descriptive title (e.g. "California Air Toxics Hot Spots Program")
- **description**: 2-3 sentences explaining what the state requires beyond federal baseline
- **current_value**: Brief value (e.g. "State-delegated NPDES program with additional bioassay requirements")
- **effective_date**: When the state requirement took effect (YYYY-MM-DD)
- **source_url**: Official state agency URL
- **source_name**: Agency name (e.g. "California EPA / DTSC")
- **requires_written_policy**: true if facility must maintain written compliance documents
- **jurisdiction_level**: `state` (or `city` if city-specific, rare for environmental)
- **jurisdiction_name**: State name (e.g. "California")

### Critical rules

1. **ONLY capture where state DIFFERS FROM or EXCEEDS federal EPA baseline** — don't duplicate base RCRA/CWA/CAA
2. Many states have **delegated authority** from EPA — note which programs are state-delegated vs federal-only
3. Some states have their own programs that go beyond federal (e.g., California's Prop 65, CalARP, Hot Spots Act)
4. `jurisdiction_level` must be `state` or `city` — NEVER `federal`
5. If a state has NO additional requirements beyond federal for a key, skip it — don't create a row

If `--dry-run`, output a markdown summary to `server/scripts/<state>_environmental_gaps.md` and stop.

## Step 4: Write to database

For each researched requirement, UPSERT into `jurisdiction_requirements`. Use a script like this for each entry:

```bash
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python -c "
import asyncio, asyncpg, os, json
from dotenv import load_dotenv
load_dotenv()

ENTRIES = <ENTRIES_JSON>

async def main():
    conn = await asyncpg.connect(os.environ['DATABASE_URL'])
    cat_id = await conn.fetchval(\"SELECT id FROM compliance_categories WHERE slug = 'environmental_compliance' LIMIT 1\")
    inserted = 0
    for e in ENTRIES:
        requirement_key = f\"environmental_compliance:{e['regulation_key']}\"
        await conn.execute('''
            INSERT INTO jurisdiction_requirements
                (jurisdiction_id, requirement_key, category, jurisdiction_level, jurisdiction_name,
                 title, description, current_value, source_url, source_name,
                 effective_date, last_verified_at, requires_written_policy,
                 regulation_key, key_definition_id, category_id, source_tier)
            VALUES (\$1, \$2, '\''environmental_compliance'\'', \$3, \$4, \$5, \$6, \$7, \$8, \$9, \$10::date, NOW(), \$11,
                    \$12, \$13, \$14, '\''tier_3_aggregator'\''::source_tier_enum)
            ON CONFLICT (jurisdiction_id, requirement_key) DO UPDATE SET
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                previous_value = jurisdiction_requirements.current_value,
                current_value = EXCLUDED.current_value,
                source_url = EXCLUDED.source_url,
                source_name = EXCLUDED.source_name,
                effective_date = EXCLUDED.effective_date,
                last_verified_at = NOW(),
                requires_written_policy = EXCLUDED.requires_written_policy,
                regulation_key = EXCLUDED.regulation_key,
                key_definition_id = EXCLUDED.key_definition_id,
                last_changed_at = CASE
                    WHEN jurisdiction_requirements.current_value IS DISTINCT FROM EXCLUDED.current_value
                    THEN NOW() ELSE jurisdiction_requirements.last_changed_at END,
                source_tier = CASE
                    WHEN EXCLUDED.source_tier < jurisdiction_requirements.source_tier OR jurisdiction_requirements.source_tier IS NULL
                    THEN EXCLUDED.source_tier ELSE jurisdiction_requirements.source_tier END,
                updated_at = NOW()
        ''',
            e['jurisdiction_id'],        # $1
            requirement_key,             # $2
            e['jurisdiction_level'],     # $3
            e['jurisdiction_name'],      # $4
            e['title'],                  # $5
            e['description'],            # $6
            e['current_value'],          # $7
            e['source_url'],             # $8
            e['source_name'],            # $9
            e.get('effective_date'),      # $10
            e.get('requires_written_policy', False),  # $11
            e['regulation_key'],         # $12
            e['key_definition_id'],      # $13
            cat_id,                      # $14
        )
        inserted += 1
        print(f\"  ✓ {e['jurisdiction_name']}: {e['regulation_key']} — {e['title']}\")
    print(f'\\nInserted/updated {inserted} requirements')
    await conn.close()
asyncio.run(main())
"
```

Build the `ENTRIES` list as a JSON array. Each entry needs:
```json
{
  "jurisdiction_id": "<uuid>",
  "regulation_key": "<key from step 1>",
  "key_definition_id": "<uuid from step 1>",
  "jurisdiction_level": "state",
  "jurisdiction_name": "<State Name>",
  "title": "<title>",
  "description": "<description>",
  "current_value": "<brief value>",
  "source_url": "<url>",
  "source_name": "<agency>",
  "effective_date": "YYYY-MM-DD",
  "requires_written_policy": true
}
```

**Important:** For state-level requirements that apply to all cities in the state, write a row for EACH jurisdiction in that state (state-level + each city). Use the same data but different `jurisdiction_id`.

## Step 5: Report results

Tell the user:
1. How many regulation keys were researched
2. Per key: whether state has specific requirements or federal-only
3. Total jurisdiction_requirements rows created/updated
4. Link: `https://hey-matcha.com/admin/jurisdiction-data/category/environmental_compliance`
