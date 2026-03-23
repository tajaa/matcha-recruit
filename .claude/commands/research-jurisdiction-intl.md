Research and create an international jurisdiction's compliance data using Claude Code's own web research (no Gemini API). Creates the jurisdiction in the DB, researches employment law categories, and writes a structured Markdown report.

Parse the city and country from: $ARGUMENTS
Format: "<city> <country_code>" (e.g., "Singapore SG", "London GB", "Mexico City MX")
If the user provides a state/province, use it (e.g., "Mexico City CDMX MX" or "London ENG GB").

---

## Step 1: Create the jurisdiction

Run from the server directory:

```
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python scripts/create_jurisdiction.py "<city>" "<state_if_any>" --country "<country_code>" --county "<county if known>"
```

If no state/province, omit the state argument:
```
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python scripts/create_jurisdiction.py "<city>" --country "<country_code>"
```

If the output starts with `EXISTING:`, the jurisdiction already exists — tell the user and suggest `/fill-gaps` instead.
If the output starts with `CREATED:`, continue to Step 2.

---

## Step 2: Get jurisdiction context

```
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python scripts/jurisdiction_context.py "<city>" "<state_if_any>" --country "<country_code>"
```

For international jurisdictions:
- `has_local_ordinance` will be `false` (US-only concept)
- `preemption_rules` will be empty (US-only concept)
- Focus research on **national-level laws** of the country, plus any city/province-specific variations

---

## Step 3: Research compliance categories

Use **WebSearch** to research each category. The critical differences from US research:

**International research rules:**
1. Research the COUNTRY's employment/labor laws — these are the baseline (equivalent to US "federal")
2. Check if the CITY has any local variations or additional requirements
3. Use `jurisdiction_level: "national"` for country-level laws (NOT "federal" — that's US-only)
4. Use `jurisdiction_level: "province"` for state/province-level laws
5. Use `jurisdiction_level: "city"` for city-specific laws
6. Many countries mandate things the US doesn't (paid annual leave, severance, social insurance) — capture ALL of these
7. Include regulation_keys from the international set: `national_minimum_wage`, `annual_leave_entitlement`, `statutory_maternity_leave`, `severance_pay`, `social_insurance_employer`, etc.

For efficiency, batch searches — launch multiple WebSearch calls in parallel per group.

### Group 1: General Labor (12 categories)

| Category Key | What to Research (COUNTRY-SPECIFIC) |
|---|---|
| `minimum_wage` | National/sectoral minimum wage, progressive wage model if applicable. Keys: `national_minimum_wage`, `sectoral_minimum_wage`, `tipped_minimum_wage` |
| `overtime` | OT rates (may differ from US 1.5x), max working hours per week, rest day pay. Keys: `daily_weekly_overtime`, `mandatory_overtime_restrictions` |
| `sick_leave` | Statutory sick leave (most countries mandate it). Keys: `statutory_sick_leave`, `state_paid_sick_leave` |
| `leave` | Annual leave entitlement, maternity/paternity leave, notice periods, severance/redundancy pay, 13th month/bonus, probation period. Keys: `annual_leave_entitlement`, `statutory_maternity_leave`, `statutory_paternity_leave`, `severance_pay`, `statutory_notice_period_employer` |
| `meal_breaks` | Working time regulations, rest periods, maximum daily hours. Keys: `meal_break`, `rest_break` |
| `final_pay` | Final pay deadlines on termination. Keys: `final_pay_termination`, `final_pay_resignation` |
| `pay_frequency` | Pay frequency requirements, payslip requirements. Keys: `standard_pay_frequency`, `wage_notice` |
| `scheduling_reporting` | Maximum working hours, scheduling rules. Keys: `predictive_scheduling` |
| `workers_comp` | Work injury insurance, social insurance contributions. Keys: `mandatory_coverage`, `social_insurance_employer`, `social_insurance_employee` |
| `workplace_safety` | National safety authority, factory inspection requirements. Keys: `osha_general_duty` |
| `anti_discrimination` | Protected characteristics (varies by country), equal pay laws. Keys: `protected_classes`, `pay_transparency` |
| `minor_work_permit` | Child labor rules, minimum working age. Keys: `work_permit`, `hour_limits_14_15` |

### Group 2: Healthcare (if applicable)

Research only if the jurisdiction has significant healthcare industry. Use the same 8 healthcare categories as US research but frame questions around the country's health system.

### Group 3: Country-Specific

Research any major employment law concepts unique to this country:
- **Singapore**: CPF contributions, Employment Act coverage, foreign worker levy
- **Mexico**: Aguinaldo (Christmas bonus), PTU (profit sharing), IMSS/INFONAVIT
- **UK**: National Insurance, auto-enrolment pensions, IR35, statutory redundancy
- **Germany**: Kurzarbeit, works councils, co-determination
- **Japan**: Shunto, mandatory retirement age, overtime caps

**Search queries** (adapt for country):
- `"<country> employment law minimum wage 2025 2026"`
- `"<country> statutory annual leave entitlement"`
- `"<country> maternity paternity leave law"`
- `"<country> termination notice period severance pay"`
- `"<country> social insurance employer contribution rates"`
- `"<country> <city> local employment regulations"`

---

## Step 4: Write the Markdown report

Write the results to: `server/scripts/<city_lowercase>_<country_lowercase>_research.md`

Use this format — each requirement MUST use regulation keys:

```markdown
# <City>, <Country> — Compliance Research

**Researched by**: Claude Code (web search)
**Date**: <today's date>
**Country Code**: <XX>
**State/Province**: <if applicable, else N/A>

---

## General Labor

### minimum_wage

#### National Minimum Wage
- **regulation_key**: `national_minimum_wage`
- **jurisdiction_level**: national
- **jurisdiction_name**: <Country Name>
- **title**: <Country Name> National Minimum Wage
- **description**: <detailed explanation>
- **current_value**: <amount in local currency>/month or /hr
- **numeric_value**: <number>
- **effective_date**: YYYY-MM-DD
- **source_url**: <URL>
- **source_name**: <source name>
- **requires_written_policy**: false

### leave

#### Statutory Annual Leave
- **regulation_key**: `annual_leave_entitlement`
- **jurisdiction_level**: national
- **paid**: true
- **max_weeks**: <number>
...
```

**Output rules:**
- `jurisdiction_level` must be `national`, `province`, or `city` — NEVER `federal` or `state` for international
- Include country-specific keys (e.g., `sg_cpf_contribution` for Singapore)
- Include social insurance/pension contribution rates — these are often the most complex part of international compliance
- For leave: include ALL mandatory leave types (annual, maternity, paternity, sick, public holidays)
- Note the currency for all monetary values

---

## Step 5: Report results

Tell the user:
1. Whether the jurisdiction was created or already existed
2. Country code and any state/province
3. Summary per group — how many categories had country-specific laws
4. Notable findings unique to this jurisdiction (e.g., "Singapore has mandatory CPF at 37% combined rate", "Mexico requires 15-day Christmas bonus")
5. Where the markdown file was written
