Research missing compliance categories for a jurisdiction using Claude Code web search and write results to a Markdown file (does NOT write to the database).

The user will provide a city and state (e.g. "Los Angeles CA" or "fill gaps for New York NY"). Parse the city and state from their input: $ARGUMENTS

Options the user may include:
- `--list-gaps` — Just show what's missing without researching anything
- `--categories general` — Only fill the 12 general labor categories
- `--categories healthcare` — Only fill the 8 healthcare categories
- `--categories oncology` — Only fill the 5 oncology categories
- `--categories life_sciences` — Only fill the 6 life sciences categories
- `--categories all` — Fill all gaps (default)

---

## Step 1: Find the jurisdiction and check existing categories

Run this to discover what's already present and what's missing:

```bash
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python -c "
import asyncio, asyncpg, os, json
from dotenv import load_dotenv
load_dotenv()
async def main():
    conn = await asyncpg.connect(os.environ['DATABASE_URL'])
    row = await conn.fetchrow('SELECT id, city, state, county FROM jurisdictions WHERE LOWER(city) = LOWER(\$1) AND state = \$2', '<CITY>', '<STATE>')
    if not row:
        # Try state-level (city=NULL)
        row = await conn.fetchrow('SELECT id, city, state, county FROM jurisdictions WHERE city IS NULL AND state = \$1', '<STATE>')
    if not row:
        print('NOT_FOUND')
        await conn.close()
        return
    cats = await conn.fetch('SELECT DISTINCT category FROM jurisdiction_requirements WHERE jurisdiction_id = \$1', row['id'])
    existing = sorted([r['category'] for r in cats])
    print(f'ID:{row[\"id\"]}')
    print(f'CITY:{row[\"city\"] or \"(state-level)\"}')
    print(f'STATE:{row[\"state\"]}')
    print(f'COUNTY:{row[\"county\"] or \"N/A\"}')
    print(f'EXISTING:{json.dumps(existing)}')
    await conn.close()
asyncio.run(main())
"
```

Replace `<CITY>` and `<STATE>` with the parsed values.

## Step 2: Determine gaps

**All target categories by group:**

| Group | Categories |
|-------|-----------|
| General labor (12) | `minimum_wage`, `overtime`, `sick_leave`, `leave`, `meal_breaks`, `final_pay`, `pay_frequency`, `scheduling_reporting`, `workers_comp`, `workplace_safety`, `anti_discrimination`, `minor_work_permit` |
| Healthcare (8) | `hipaa_privacy`, `clinical_safety`, `billing_integrity`, `corporate_integrity`, `emergency_preparedness`, `healthcare_workforce`, `state_licensing`, `research_consent` |
| Oncology (5) | `radiation_safety`, `chemotherapy_handling`, `tumor_registry`, `oncology_clinical_trials`, `oncology_patient_rights` |
| Life Sciences (6) | `gmp_manufacturing`, `glp_nonclinical`, `clinical_trials_gcp`, `drug_supply_chain`, `sunshine_open_payments`, `biosafety_lab` |

Based on the `--categories` flag, select the target categories. Then subtract what's already present. The remainder are the **gaps** to research.

If `--list-gaps` was specified, just report the gaps and stop.

## Step 3: Get jurisdiction context

```bash
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python scripts/jurisdiction_context.py "<CITY>" "<STATE>"
```

Use the output to guide research:
- `has_local_ordinance`: whether to search for city-level ordinances
- `preemption_rules`: which categories allow local override
- `expected_regulation_keys`: the known regulation keys per category

## Step 4: Research missing categories via WebSearch

Use **WebSearch** to research each missing category. The critical rule:

**ONLY capture requirements where the STATE or CITY has laws that DIFFER FROM or EXCEED the federal baseline.** Do NOT duplicate federal requirements that apply identically everywhere.

For efficiency, batch searches — launch multiple WebSearch calls in parallel per group.

### Research patterns per category

Use the same category research tables as `/research-jurisdiction`:

**General Labor**: Search `"<state> <category_topic> law 2025 2026"`. Focus on state-specific laws.
**Healthcare**: Search `"<state> <healthcare_topic> beyond federal requirements"`. Skip base HIPAA/CMS.
**Oncology**: Search `"<state> <oncology_topic> requirements"`. Many are inherently state-specific.
**Life Sciences**: Search `"<state> <life_sciences_topic> license requirements"`. State boards set their own rules.

Key search queries:
- `"<state> minimum wage 2025 2026 current rate"`
- `"<state> paid sick leave law"`
- `"<state> family medical leave state law beyond FMLA"`
- `"<state> health privacy law beyond HIPAA"`
- `"<state> nurse staffing ratio requirements"`
- `"<state> radiation control program NRC agreement state"`
- `"<state> cancer registry reporting requirements"`
- `"<state> drug manufacturer license requirements"`
- `"<state> clinical trial registration notification requirements"`

## Step 5: Write the Markdown report

Write results to: `server/scripts/<city_lowercase>_<state_lowercase>_gaps.md`

Use the same structured format as `/research-jurisdiction`:

```markdown
# <City>, <State> — Gap Fill Research

**Researched by**: Claude Code (web search)
**Date**: <today's date>
**County**: <county or N/A>
**Has Local Ordinance**: <true/false from context>
**Categories researched**: <N gaps filled>

---

## <Group Name>

### <category_key>

#### <Requirement Title>
- **regulation_key**: `<key>`
- **rate_type**: <if applicable>
- **jurisdiction_level**: state|city
- **jurisdiction_name**: <State or City Name>
- **title**: <title>
- **description**: <detailed explanation>
- **current_value**: <value>
- **numeric_value**: <number if applicable>
- **effective_date**: YYYY-MM-DD
- **source_url**: <URL>
- **source_name**: <source>
- **requires_written_policy**: true|false
```

**Output rules:**
- Use `regulation_key` values from `expected_regulation_keys` in context JSON
- `jurisdiction_level` must be `state` or `city` — NEVER `federal`
- If a category has NO state/city requirements beyond federal: `*Federal only — no state-specific requirements.*`

## Step 6: Report results

Tell the user:
1. How many categories were already present vs gaps found
2. Summary per group — categories with state-specific laws vs federal-only
3. Notable findings
4. Where the markdown file was written
