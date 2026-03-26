# Claude Code Skills (Slash Commands)

Slash commands you can use in Claude Code for this project. Type `/` followed by the command name.

---

## /fill-gaps

Research missing compliance categories for a jurisdiction using **Claude Code web search** and write results to a Markdown file. Does NOT write to the database — output is for review only. Only researches what's missing — safe to re-run.

**Usage:**
```
/fill-gaps Los Angeles CA
/fill-gaps New York NY --list-gaps
/fill-gaps Chicago IL --categories oncology
```

**Options:**
- `--list-gaps` — Just show what's missing without researching anything
- `--categories general` — Only fill the 12 general labor categories
- `--categories healthcare` — Only fill the 8 healthcare categories
- `--categories oncology` — Only fill the 5 oncology categories
- `--categories life_sciences` — Only fill the 6 life sciences categories
- `--categories all` — Fill all gaps (default)

**Category groups:**
| Group | Count | Examples |
|-------|-------|----------|
| General labor | 12 | minimum_wage, overtime, sick_leave, meal_breaks |
| Healthcare | 8 | hipaa_privacy, clinical_safety, billing_integrity |
| Oncology | 5 | radiation_safety, chemotherapy_handling, tumor_registry |
| Life Sciences | 6 | gmp_manufacturing, clinical_trials_gcp, drug_supply_chain |

**How it works:**
1. Queries the DB for the jurisdiction and its existing categories
2. Determines which target categories are missing (the "gaps")
3. Gets jurisdiction context (has_local_ordinance, preemption_rules, expected_regulation_keys)
4. Researches each gap via Claude Code WebSearch — only captures state/city-specific requirements
5. Writes structured Markdown to `scripts/<city>_<state>_gaps.md`

---

## /fill-gaps-us-east

Batch-research thin healthcare compliance categories across all **US East/Central** jurisdictions using Claude Code web search.

**No arguments needed** — auto-discovers jurisdictions in: NY, IL, TX, FL, TN, NC, OH, MI, PA, NJ, CT, MA, MD, DE, ME, RI, MN, DC, GA.

**Categories**: telehealth, cybersecurity, language_access, emerging_regulatory, health_it, marketing_comms, tax_exempt, transplant_organ

---

## /fill-gaps-us-west

Batch-research thin healthcare compliance categories across all **US West** jurisdictions using Claude Code web search.

**No arguments needed** — auto-discovers jurisdictions in: CA, CO, OR, WA, NV, UT, ID, AZ, HI.

**Categories**: same 8 as fill-gaps-us-east

---

## /fill-gaps-intl

Batch-research thin healthcare compliance categories across all **international** jurisdictions using Claude Code web search.

**No arguments needed** — auto-discovers non-US jurisdictions.

**Categories**: telehealth, cybersecurity, language_access, emerging_regulatory, health_it, marketing_comms (skips US-specific tax_exempt and transplant_organ)

---

## /fill-gaps-penalties

Research authoritative penalty/fine data for all compliance categories. Uses Federal Register API, OSHA enforcement API, and web search. **This one writes to the database** (updates `metadata.penalties` on jurisdiction_requirements).

---

## /bootstrap-jurisdiction

Create a **new** jurisdiction in the database and research all its compliance categories from scratch via Gemini. Use this when the city doesn't exist yet in the `jurisdictions` table. If it already exists, the script will tell you and suggest `/fill-gaps` instead.

**Usage:**
```
/bootstrap-jurisdiction Indianapolis IN
/bootstrap-jurisdiction Portland OR --county Multnomah
/bootstrap-jurisdiction Austin TX --categories healthcare
/bootstrap-jurisdiction Denver CO --dry-run
```

**Options:**
- `--county "<name>"` — Set the county for the jurisdiction
- `--categories general|healthcare|oncology|medical_compliance|life_sciences|all`
- `--dry-run` — Research and write Markdown only, do NOT create the jurisdiction in the DB
- `--output <path>` — Custom output file path

**Underlying script:** `server/scripts/bootstrap_jurisdiction.py`

**Note:** This writes to the production database. Use `--dry-run` if you just want to see the research output.

---

## /research-jurisdiction

Same goal as `/bootstrap-jurisdiction` but uses **Claude Code's own web search** instead of Gemini API calls. Matches the same architecture as the Gemini pipeline — uses `has_local_ordinance`, `preemption_rules`, and `expected_regulation_keys` to guide research.

**Key difference from Gemini pipeline**: Only captures requirements where the **state or city differs from or exceeds the federal baseline**. Federal-only categories are marked as such, not duplicated.

**Usage:**
```
/research-jurisdiction Indianapolis IN
/research-jurisdiction Portland OR
/research-jurisdiction Austin TX
```

**How it works:**
1. Creates the jurisdiction row in DB via `scripts/create_jurisdiction.py`
2. Fetches context via `scripts/jurisdiction_context.py` (has_local_ordinance, preemption_rules, expected_regulation_keys)
3. Claude researches all categories (labor, healthcare, oncology, life sciences) via web search, guided by context — only captures state/city-specific requirements
4. Writes results to `scripts/<city>_<state>_research.md` using `regulation_key`, `jurisdiction_level`, `rate_type` matching the `jurisdiction_requirements` table schema

**Output format**: Matches `jurisdiction_requirements` table fields — `regulation_key`, `jurisdiction_level` (state/city only, never federal), `rate_type`, `current_value`, `numeric_value`, `effective_date`, `source_url`, `source_name`, `requires_written_policy`

**When to use this vs `/bootstrap-jurisdiction`:**
- `/bootstrap-jurisdiction` — uses Gemini API with Google Search grounding (faster, structured JSON output)
- `/research-jurisdiction` — uses Claude Code web research (no Gemini dependency, same architecture, state-specific focus)

**Underlying scripts:**
- `server/scripts/create_jurisdiction.py` — DB insert only
- `server/scripts/jurisdiction_context.py` — outputs research context as JSON

---

## /research-jurisdiction-intl

Same as `/research-jurisdiction` but for **international** jurisdictions. Uses country-specific regulatory frameworks (GDPR, PDPA, etc.) and `jurisdiction_level: "national"` instead of `"federal"`.

**Usage:**
```
/research-jurisdiction-intl Singapore SG
/research-jurisdiction-intl London GB
/research-jurisdiction-intl Mexico City MX
```

---

## /research-manufacturing

Research **manufacturing-specific** compliance for a jurisdiction. Covers process safety, environmental, chemical, machine safety, industrial hygiene, trade, product safety, and labor relations — plus the standard 12 labor categories. Works for US and international.

**Usage:**
```
/research-manufacturing North Carolina US tire-manufacturing
/research-manufacturing London GB
/research-manufacturing Singapore SG rubber-manufacturing
```
