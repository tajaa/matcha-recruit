Research manufacturing-specific compliance for a jurisdiction. Covers process safety, environmental, chemical, machine safety, industrial hygiene, trade, product safety, and labor relations — plus the standard 12 labor categories.

Parse the jurisdiction and optional industry sub-type from: $ARGUMENTS

Examples:
- `North Carolina US tire-manufacturing`
- `London GB`
- `Singapore SG rubber-manufacturing`

If no industry sub-type is given, default to general manufacturing.

---

## Step 1: Verify jurisdiction exists

Run from the server directory:

```
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python scripts/create_jurisdiction.py "<city_or_state>" "<state_or_country>"
```

If `EXISTING:`, continue. If `CREATED:`, continue. Note the jurisdiction ID.

---

## Step 2: Get jurisdiction context

```
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python scripts/jurisdiction_context.py "<city_or_state>" "<state_or_country>"
```

Use the `expected_regulation_keys` and `has_local_ordinance` from the output to guide research.

---

## Step 3: Research manufacturing categories

Use **WebSearch** to research each category. The critical rule:

**ONLY capture requirements where the jurisdiction has laws that DIFFER FROM or EXCEED the federal/national baseline.** Do NOT duplicate requirements that apply identically everywhere.

Determine the jurisdiction type from the arguments:
- **US jurisdictions**: Search with state name + federal OSHA/EPA references
- **UK jurisdictions**: Search with UK + HSE/Environment Agency/COMAH/COSHH/PUWER references
- **Singapore jurisdictions**: Search with Singapore + MOM/NEA/WSH Act references
- **Other international**: Adapt to local regulatory agencies

For efficiency, batch searches — launch multiple WebSearch calls in parallel.

### Manufacturing Categories (8)

| Category Key | US Search Pattern | UK Search Pattern | SG Search Pattern |
|---|---|---|---|
| `process_safety` | `"<state> process safety management OSHA PSM chemical manufacturing 2025"` | `"UK COMAH regulations major accident hazards manufacturing 2025"` | `"Singapore major hazard installation MHI WSH factory registration 2025"` |
| `environmental_compliance` | `"<state> EPA air permit manufacturing emissions VOC NESHAP DEQ 2025"` | `"UK environmental permit manufacturing emissions Environment Agency 2025"` | `"Singapore NEA environmental protection manufacturing emissions licence 2025"` |
| `chemical_safety` | `"<state> hazardous chemical reporting right to know GHS EPCRA 2025"` | `"UK COSHH REACH chemical safety manufacturing hazardous substances 2025"` | `"Singapore hazardous substances licence NEA chemical handling 2025"` |
| `machine_safety` | `"<state> lockout tagout machine guarding OSHA manufacturing LOTO 2025"` | `"UK PUWER LOLER machinery safety regulations manufacturing 2025"` | `"Singapore WSH machinery safety equipment registration factory 2025"` |
| `industrial_hygiene` | `"<state> noise exposure respiratory protection OSHA PEL manufacturing 2025"` | `"UK workplace exposure limits COSHH noise at work manufacturing 2025"` | `"Singapore permissible exposure limits noise WSH manufacturing 2025"` |
| `trade_compliance` | `"<state> import export customs manufacturing tariff anti-dumping 2025"` | `"UK post-Brexit import export manufacturing customs duties 2025"` | `"Singapore import export manufacturing trade compliance FTA 2025"` |
| `product_safety` | `"NHTSA FMVSS tire safety standards manufacturer certification 2025"` (or adapt for industry) | `"UK UNECE product safety type approval manufacturing 2025"` | `"Singapore product safety standards consumer protection manufacturing 2025"` |
| `labor_relations` | `"<state> right to work union collective bargaining NLRA manufacturing 2025"` | `"UK trade union recognition manufacturing collective bargaining 2025"` | `"Singapore tripartism TAFEP manufacturing employment relations 2025"` |

If the user specified an industry sub-type (e.g. `tire-manufacturing`), add industry-specific terms to searches:
- **tire/rubber**: Add `rubber tire NESHAP VOC`, `FMVSS 139`, `UNECE R117`, `vulcanization`
- **chemical**: Add `TSCA`, `chemical plant`, `SEVESO`
- **automotive**: Add `IATF 16949`, `vehicle safety`, `crash testing`
- **food**: Add `FDA FSMA`, `HACCP`, `food safety`

### Standard Labor Categories (12)

Also research the standard labor categories using the same patterns from the `/research-jurisdiction` skill (for US) or `/research-jurisdiction-intl` skill (for UK/Singapore). These are:

`minimum_wage`, `overtime`, `sick_leave`, `leave`, `meal_breaks`, `final_pay`, `pay_frequency`, `scheduling_reporting`, `workers_comp`, `workplace_safety`, `anti_discrimination`, `minor_work_permit`

---

## Step 4: Write the Markdown report

Write results to: `server/scripts/<jurisdiction_slug>_manufacturing_research.md`

Use the same format as `/research-jurisdiction`:

```markdown
# <Jurisdiction> — Manufacturing Compliance Research

**Researched by**: Claude Code (web search)
**Date**: <today's date>
**Industry**: <industry sub-type or "general manufacturing">

---

## Manufacturing

### process_safety

#### OSHA Process Safety Management
- **regulation_key**: `osha_psm`
- **jurisdiction_level**: <state|federal|national>
- **jurisdiction_name**: <jurisdiction>
- **title**: <title>
- **description**: <detailed explanation>
- **current_value**: <summary of requirement>
- **source_url**: <URL>
- **source_name**: <source>
- **requires_written_policy**: true

### environmental_compliance
...

## General Labor

### minimum_wage
...
```

**Output rules:**
- Group requirements under their category key as `###` headings
- Each individual requirement is a `####` heading
- Use regulation_key values from `expected_regulation_keys` in the context JSON
- `jurisdiction_level` must be `state`, `city`, or `national` — NEVER `federal` for non-US
- If a category has NO jurisdiction-specific requirements beyond the national baseline, write: `*National baseline only — no jurisdiction-specific requirements found.*`
- Include `requires_written_policy`: true if the statute mandates documented procedures (common for PSM, LOTO, chemical safety)
- For international jurisdictions, note the local regulatory agency and statute reference

---

## Step 5: Report results

Tell the user:
1. Which jurisdiction was researched
2. How many manufacturing categories had jurisdiction-specific findings vs baseline-only
3. How many standard labor categories had findings
4. Notable findings (e.g. "NC is a State Plan state for OSHA, right-to-work state, DEQ requires separate air quality permits for rubber manufacturing")
5. Where the markdown file was written
6. Remind them to run `./venv/bin/python scripts/ingest_research_md.py <markdown_file>` to load into the database
