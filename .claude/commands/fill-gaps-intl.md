Batch-research thin healthcare compliance categories across all international jurisdictions using Claude Code web search (no Gemini API).

No arguments needed — this skill auto-discovers international jurisdictions and fills gaps for applicable healthcare categories.

---

## Categories to research

International jurisdictions need a subset of healthcare categories adapted to their national frameworks:

1. `telehealth` — Telehealth & Digital Health (country-specific licensing, cross-border care)
2. `cybersecurity` — Cybersecurity & Data Protection (GDPR in EU, PDPA in SG, etc.)
3. `health_it` — Health IT & Interoperability (national EHR systems, data exchange standards)
4. `emerging_regulatory` — Emerging Regulatory (AI in healthcare, genomics, cannabis)
5. `language_access` — Language Access (multilingual requirements per country)
6. `marketing_comms` — Marketing & Communications (advertising regulations for healthcare)

**Skip for international** (US-specific programs):
- `tax_exempt` — US 501(r) / IRS specific
- `transplant_organ` — US NOTA/OPTN specific

## Step 1: Discover jurisdictions and gaps

Query the database to find all international jurisdictions and their existing categories:

```bash
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python -c "
import asyncio, asyncpg, os, json
from dotenv import load_dotenv
load_dotenv()
US_STATES = ['AL','AK','AZ','AR','CA','CO','CT','DE','DC','FL','GA','HI','ID','IL','IN','IA','KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY']
TARGET_CATS = ['telehealth','cybersecurity','language_access','emerging_regulatory','health_it','marketing_comms']
async def main():
    conn = await asyncpg.connect(os.environ['DATABASE_URL'])
    rows = await conn.fetch('''
        SELECT j.id, j.city, j.state, j.county,
               array_agg(DISTINCT jr.category) FILTER (WHERE jr.category IS NOT NULL) as cats
        FROM jurisdictions j
        LEFT JOIN jurisdiction_requirements jr ON jr.jurisdiction_id = j.id
        WHERE j.state != ALL(\$1) AND j.city IS NOT NULL AND j.city NOT LIKE '\_county\_%'
        GROUP BY j.id, j.city, j.state, j.county
        ORDER BY j.state, j.city
    ''', US_STATES)
    for r in rows:
        existing = [c for c in (r['cats'] or []) if c in TARGET_CATS]
        missing = [c for c in TARGET_CATS if c not in existing]
        if missing:
            print(f'{r[\"city\"]}|{r[\"state\"]}|{r[\"county\"] or \"N/A\"}|{len(missing)} gaps|{\",\".join(missing)}')
    await conn.close()
asyncio.run(main())
"
```

Report the total gap count to the user before proceeding.

## Step 2: Research each jurisdiction via WebSearch

For EACH international jurisdiction with gaps, research the missing categories using **WebSearch**.

### Research patterns per category (adapt for country)

| Category | Search Query Pattern |
|----------|---------------------|
| `telehealth` | `"<country> telemedicine telehealth regulation law cross-border prescribing 2025"` |
| `cybersecurity` | `"<country> health data protection cybersecurity law GDPR PDPA 2025"` |
| `health_it` | `"<country> national EHR health information exchange interoperability 2025"` |
| `emerging_regulatory` | `"<country> AI healthcare regulation emerging technology genomics law 2025"` |
| `language_access` | `"<country> healthcare language access multilingual patient requirements"` |
| `marketing_comms` | `"<country> healthcare advertising marketing regulation pharmaceutical"` |

### Country-specific research adaptations

- **UK (GB/ENG)**: NHS Digital, CQC regulations, UK GDPR, Medicines and Healthcare products Regulatory Agency (MHRA)
- **France (FR/IDF)**: CNIL, Agence du Numérique en Santé (ANS), DMP system, ANSM
- **Singapore (SG)**: PDPA, MOH regulations, Healthtech regulatory sandbox, HSA
- **Mexico (MX/CDMX)**: COFEPRIS, Ley General de Salud, NOM standards, LFPDPPP

### What to capture per requirement

```markdown
#### <Requirement Title>
- **regulation_key**: `<key>`
- **jurisdiction_level**: national (or province/city if applicable)
- **jurisdiction_name**: <Country Name>
- **title**: <title>
- **description**: <detailed explanation>
- **current_value**: <summary>
- **effective_date**: YYYY-MM-DD
- **source_url**: <URL>
- **source_name**: <source>
- **requires_written_policy**: true|false
- **applicable_industries**: healthcare
```

## Step 3: Write Markdown output

For each country/jurisdiction, write results to: `server/scripts/<city>_<country>_healthcare_gaps.md`

Format:

```markdown
# <City>, <Country> — Healthcare Gap Fill

**Researched by**: Claude Code (web search)
**Date**: <today's date>
**Country Code**: <XX>

---

## telehealth

#### <Requirement Title>
- **regulation_key**: `<key>`
- **jurisdiction_level**: national
...

## cybersecurity
...
```

## Step 4: Process order

Process jurisdictions found in Step 1. Expected:
- Mexico City, MX
- London, GB
- Paris, FR
- Singapore, SG
- Plus any others discovered in the DB query

After EACH jurisdiction completes, report: city/country, categories researched, output file path.

## Step 5: Summary

At the end, summarize:
- Total jurisdictions processed
- Total categories filled
- Output files created
- Any categories where no country-specific data was found

## Important

- Do NOT write to the database — output Markdown only
- Do NOT use the Gemini API or `fill_jurisdiction_gaps.py` — use WebSearch only
- If a jurisdiction doesn't exist in the DB, skip it
- Use `jurisdiction_level: "national"` for country-level laws (NOT "federal")
- Use `jurisdiction_level: "province"` for state/province-level laws
- Include the country's regulatory body names and official source URLs
