Batch-research thin healthcare compliance categories across all US East/Central jurisdictions using Claude Code web search (no Gemini API).

No arguments needed — this skill auto-discovers US East/Central jurisdictions and fills gaps for 8 thin healthcare categories.

---

## Thin categories to research

These categories exist but have sparse jurisdiction coverage:

1. `telehealth` — Telehealth & Digital Health (High state variance)
2. `cybersecurity` — Cybersecurity (High state variance)
3. `language_access` — Language Access & Civil Rights (High state variance)
4. `emerging_regulatory` — Emerging Regulatory (High state variance)
5. `health_it` — Health IT & Interoperability
6. `marketing_comms` — Marketing & Communications
7. `tax_exempt` — Tax-Exempt Compliance
8. `transplant_organ` — Transplant & Organ Procurement

## Step 1: Discover jurisdictions and gaps

Query the database to find all US East/Central jurisdictions and their existing categories:

```bash
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python -c "
import asyncio, asyncpg, os, json
from dotenv import load_dotenv
load_dotenv()
TARGET_STATES = ['NY','IL','TX','FL','TN','NC','OH','MI','PA','NJ','CT','MA','MD','DE','ME','RI','MN','DC','GA']
TARGET_CATS = ['telehealth','cybersecurity','language_access','emerging_regulatory','health_it','marketing_comms','tax_exempt','transplant_organ']
async def main():
    conn = await asyncpg.connect(os.environ['DATABASE_URL'])
    rows = await conn.fetch('''
        SELECT j.id, j.city, j.state, j.county,
               array_agg(DISTINCT jr.category) FILTER (WHERE jr.category IS NOT NULL) as cats
        FROM jurisdictions j
        LEFT JOIN jurisdiction_requirements jr ON jr.jurisdiction_id = j.id
        WHERE j.state = ANY(\$1) AND j.city IS NOT NULL AND j.city NOT LIKE '\_county\_%'
        GROUP BY j.id, j.city, j.state, j.county
        ORDER BY j.state, j.city
    ''', TARGET_STATES)
    for r in rows:
        existing = [c for c in (r['cats'] or []) if c in TARGET_CATS]
        missing = [c for c in TARGET_CATS if c not in existing]
        if missing:
            print(f'{r[\"city\"]}|{r[\"state\"]}|{r[\"county\"] or \"N/A\"}|{len(missing)} gaps|{\",\".join(missing)}')
    await conn.close()
asyncio.run(main())
"
```

This outputs lines like: `new york|NY|New York|8 gaps|telehealth,cybersecurity,...`

Report the total gap count to the user before proceeding.

## Step 2: Research each jurisdiction via WebSearch

For EACH jurisdiction with gaps, research the missing categories using **WebSearch**. Process states sequentially but batch multiple WebSearch calls in parallel within each jurisdiction.

### Research patterns per category

For each category, search for **state-specific** laws. These are healthcare categories, so most regulation is at the state level. Only check for city-specific rules if the city has known local healthcare ordinances (rare for these categories).

| Category | Search Query Pattern |
|----------|---------------------|
| `telehealth` | `"<state> telehealth law telemedicine prescribing licensure 2025 2026"` |
| `cybersecurity` | `"<state> cybersecurity law data breach notification health data 2025"` |
| `language_access` | `"<state> language access healthcare interpreter requirements law"` |
| `emerging_regulatory` | `"<state> AI healthcare regulation emerging technology law 2025 2026"` |
| `health_it` | `"<state> health information exchange HIE interoperability law"` |
| `marketing_comms` | `"<state> healthcare advertising marketing regulations law"` |
| `tax_exempt` | `"<state> tax exempt hospital community benefit requirements law"` |
| `transplant_organ` | `"<state> organ transplant procurement donation registry law"` |

**Critical rule**: ONLY capture requirements where the state has laws that DIFFER FROM or EXCEED the federal baseline. If a state has no specific law for a category, mark it as federal-only.

### What to capture per requirement

```markdown
#### <Requirement Title>
- **regulation_key**: `<key>`
- **jurisdiction_level**: state (or city if applicable)
- **jurisdiction_name**: <State Name>
- **title**: <title>
- **description**: <detailed explanation of the state-specific rule>
- **current_value**: <summary>
- **effective_date**: YYYY-MM-DD
- **source_url**: <URL>
- **source_name**: <source>
- **requires_written_policy**: true|false
- **applicable_industries**: healthcare
```

## Step 3: Write Markdown output

For each state, write results to: `server/scripts/<STATE>_east_healthcare_gaps.md`

Format:

```markdown
# <State> — Healthcare Gap Fill

**Researched by**: Claude Code (web search)
**Date**: <today's date>
**Jurisdictions covered**: <list of cities in this state>

---

## telehealth

### <City>, <State>

#### <Requirement Title>
- **regulation_key**: `<key>`
- **jurisdiction_level**: state
...

*or if no state-specific law:*
*Federal only — no state-specific telehealth requirements beyond federal baseline.*

## cybersecurity
...
```

Group output by STATE (one file per state), with city subsections if multiple cities exist in that state.

## Step 4: Process order

Process in this order (largest states first):
1. New York (NY) — new york, New York City
2. Texas (TX) — austin, dallas, Houston
3. Florida (FL) — miami, orlando
4. Illinois (IL) — chicago (likely only emerging_regulatory gap)
5. Ohio (OH) — cleveland, columbus
6. Michigan (MI) — detroit
7. Pennsylvania (PA) — philadelphia
8. Tennessee (TN) — nashville
9. North Carolina (NC) — charlotte
10. Georgia (GA) — atlanta
11. Massachusetts (MA) — Boston
12. Remaining: NJ, CT, MD, DE, ME, RI, MN, DC (check if cities exist)

After EACH state completes, report: state name, categories researched, output file path.

## Step 5: Summary

At the end, summarize:
- Total states/cities processed
- Total categories filled across all jurisdictions
- Output files created
- Any categories where no state-specific data was found (federal-only)

## Important

- Do NOT write to the database — output Markdown only
- Do NOT use the Gemini API or `fill_jurisdiction_gaps.py` — use WebSearch only
- If a jurisdiction doesn't exist in the DB, skip it
- State-level healthcare laws usually apply to all cities in that state — research once per state, note which cities it covers
- For cities with the same state, the state-level findings apply to all of them
