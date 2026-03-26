Research and create a new jurisdiction's compliance data using Claude Code's own web research (no Gemini API). Creates the jurisdiction in the DB, researches all compliance categories, and writes a structured Markdown report.

Parse the city and state from: $ARGUMENTS
If the user mentions a county, note it for the `--county` flag.

---

## Step 1: Create the jurisdiction

Run from the server directory:

```
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python scripts/create_jurisdiction.py "<city>" "<state>" --county "<county if known>"
```

If the output starts with `EXISTING:`, the jurisdiction already exists — tell the user and suggest `/fill-gaps` instead.
If the output starts with `CREATED:`, continue to Step 2.

---

## Step 2: Get jurisdiction context

Run this to get the same context the Gemini scripts use:

```
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python scripts/jurisdiction_context.py "<city>" "<state>"
```

This returns JSON with:
- `has_local_ordinance`: whether the city has its own local employment ordinances
- `preemption_rules`: which categories the state allows local override on (e.g. `{"minimum_wage": true}` means the city CAN have its own minimum wage)
- `expected_regulation_keys`: the known regulation keys per category that the system expects
- `groups`: which categories belong to labor, healthcare, oncology

**Use this context to guide your research:**
- If `has_local_ordinance` is `false`, do NOT search for city-level ordinances — the state preempts local law. Only research state-level requirements.
- If `has_local_ordinance` is `true`, search for both state AND city-level requirements.
- If `preemption_rules` shows a category with `true`, that category allows local override — check for city-level rules even if `has_local_ordinance` is generally false.

---

## Step 3: Research compliance categories

Use **WebSearch** to research each category. The critical rule:

**ONLY capture requirements where the STATE or CITY has laws that DIFFER FROM or EXCEED the federal baseline.** Do NOT duplicate federal requirements that apply identically to every jurisdiction (e.g., base HIPAA, federal OSHA general duty clause, FLSA overtime at 40hrs/week, federal FMLA).

For each category, ask: "Does this state/city have its own law here that goes beyond federal?" If YES, document the state/city-specific requirement. If NO, mark the category as "Federal only — no state-specific requirements."

For efficiency, batch searches — launch multiple WebSearch calls in parallel per group.

### Group 1: General Labor (12 categories)

| Category Key | What to Research (STATE/CITY-SPECIFIC ONLY) |
|---|---|
| `minimum_wage` | State minimum wage (if above federal $7.25). City rate if `has_local_ordinance` or preemption allows. Use regulation keys: `state_minimum_wage`, `local_minimum_wage`, `tipped_minimum_wage`, `exempt_salary_threshold`, `fast_food_minimum_wage`, `healthcare_minimum_wage` |
| `overtime` | State overtime rules ONLY if they differ from federal (e.g., daily overtime, double time). Keys: `daily_weekly_overtime`, `double_time`, `seventh_day_overtime`, `exempt_salary_threshold`, `healthcare_overtime`, `mandatory_overtime_restrictions` |
| `sick_leave` | State/city paid sick leave law (federal has none). Keys: `state_paid_sick_leave`, `local_sick_leave`, `accrual_and_usage_caps` |
| `leave` | State family/medical leave programs BEYOND federal FMLA. Keys: `state_family_leave`, `state_paid_family_leave`, `pregnancy_disability_leave`, `state_disability_insurance`, `bereavement_leave`, `domestic_violence_leave`, `jury_duty_leave`, `voting_leave`, etc. |
| `meal_breaks` | State meal/rest break requirements (no federal mandate exists). Keys: `meal_break`, `rest_break`, `lactation_break`, `missed_break_penalty`, `healthcare_meal_waiver` |
| `final_pay` | State final pay deadlines (federal has no specific timing). Keys: `final_pay_termination`, `final_pay_resignation`, `final_pay_layoff`, `waiting_time_penalty` |
| `pay_frequency` | State pay frequency rules (federal has no mandate). Keys: `standard_pay_frequency`, `exempt_monthly_pay`, `payday_posting`, `wage_notice` |
| `scheduling_reporting` | State/city predictive scheduling, reporting time pay. Keys: `predictive_scheduling`, `reporting_time_pay`, `split_shift_premium`, `on_call_pay`, `spread_of_hours` |
| `workers_comp` | State workers comp specifics (all states require it but rules vary). Keys: `mandatory_coverage`, `claim_filing`, `anti_retaliation`, `return_to_work`, `posting_requirements` |
| `workplace_safety` | State OSHA plan if it exists (beyond federal OSHA). Keys: `osha_general_duty`, `heat_illness_prevention`, `workplace_violence_prevention`, `injury_illness_recordkeeping`, `hazard_communication` |
| `anti_discrimination` | State protected classes BEYOND federal Title VII. Keys: `protected_classes`, `pay_transparency`, `salary_history_ban`, `harassment_prevention_training`, `reasonable_accommodation`, `whistleblower_protection` |
| `minor_work_permit` | State child labor rules (often stricter than federal). Keys: `work_permit`, `hour_limits_14_15`, `hour_limits_16_17`, `prohibited_occupations`, `entertainment_permits`, `recordkeeping` |

### Group 2: Healthcare (8 categories)

| Category Key | What to Research (STATE-SPECIFIC ONLY) |
|---|---|
| `hipaa_privacy` | State health privacy laws BEYOND HIPAA (e.g., CMIA in CA, SHIELD Act in NY). Keys: `state_health_privacy_laws`, `state_biometric_privacy_laws`. Skip base HIPAA rules. |
| `clinical_safety` | State patient safety reporting, adverse event requirements BEYOND federal CMS/Joint Commission. Keys: `state_licensure_standards_for_healthcare_facilitie`, `sentinel_event_reporting`. Skip base CMS CoPs. |
| `billing_integrity` | State false claims act, anti-kickback laws, surprise billing protections. Keys: `state_false_claims_acts`, `state_antikickback_selfreferral_laws`, `no_surprises_act`. Skip federal FCA/Stark/AKS. |
| `corporate_integrity` | State-specific compliance program mandates. Keys: `state_whistleblower_protection_laws`. Skip federal OIG guidance unless state codifies it. |
| `emergency_preparedness` | State-specific emergency preparedness BEYOND CMS rule. Keys: `state_emergency_preparedness_requirements`. Skip base CMS EP rule. |
| `healthcare_workforce` | State nurse staffing ratios, mandatory overtime restrictions, scope of practice. Keys: `nurse_staffing_ratios_requirements`, `mandatory_reporting_obligations`. Skip federal FLSA/FMLA/Title VII. |
| `state_licensing` | State facility licensing, certificate of need, corporate practice doctrine. Keys: `state_facility_licensure`, `certificate_of_need_programs`, `corporate_practice_of_medicine_doctrine`, `feesplitting_prohibitions` |
| `research_consent` | State informed consent requirements BEYOND federal Common Rule. Keys: `state_research_consent_laws`. Skip base 45 CFR 46. |

### Group 3: Oncology (5 categories)

| Category Key | What to Research (STATE-SPECIFIC ONLY) |
|---|---|
| `radiation_safety` | State radiation control program, NRC Agreement State status. Keys: `state_radiation_control_programs`. Skip base NRC/federal rules. |
| `chemotherapy_handling` | State hazardous drug handling rules, USP 800 enforcement by state board of pharmacy. Keys: `usp_compounding_standards`. Skip base USP unless state has additional rules. |
| `tumor_registry` | State cancer registry reporting requirements. This is inherently state-specific. |
| `oncology_clinical_trials` | State clinical trial insurance coverage mandates, right to try. These are inherently state-specific. |
| `oncology_patient_rights` | State cancer patient bill of rights, palliative care access laws. These are inherently state-specific. |

### Group 4: Life Sciences (6 categories)

| Category Key | What to Research (STATE-SPECIFIC ONLY) |
|---|---|
| `gmp_manufacturing` | State drug manufacturing licenses, compounding facility requirements BEYOND federal cGMP. Keys: `cgmp_drugs_21cfr210_211`, `fda_facility_registration`. Skip base 21 CFR 210/211. |
| `glp_nonclinical` | State lab certification/accreditation requirements BEYOND federal GLP. Keys: `glp_21cfr58`. Skip base 21 CFR 58. |
| `clinical_trials_gcp` | State clinical trial registration, notification, or patient protection requirements BEYOND federal IND/GCP. Keys: `ich_e6r2_gcp`, `ind_application_21cfr312`. Skip base ICH E6/21 CFR 312. |
| `drug_supply_chain` | State wholesale drug distributor licensing, pedigree requirements BEYOND federal DSCSA. Keys: `wholesale_distribution_license`, `dscsa_serialization`. These are inherently state-specific (state boards set their own licensing). |
| `sunshine_open_payments` | State physician gift ban/disclosure laws BEYOND federal Sunshine Act (e.g., MA, MN, VT, CT gift bans). Keys: `state_gift_ban_laws`. These are inherently state-specific. |
| `biosafety_lab` | State biosafety lab registration, hazardous materials requirements BEYOND federal BSL/OSHA. Keys: `bsl_classifications`, `chemical_hygiene_plan`. Check state OSHA plan requirements. |

**Search queries** (adapt for city/state):
- `"<state> minimum wage 2025 2026 current rate"`
- `"<state> employment law beyond federal requirements"`
- `"<state> paid sick leave law"` (no federal law exists, so any result is state-specific)
- `"<state> family medical leave state law beyond FMLA"`
- `"<state> health privacy law beyond HIPAA"`
- `"<state> nurse staffing ratio requirements"`
- `"<state> false claims act healthcare"`
- `"<state> radiation control program NRC agreement state"`
- `"<state> cancer registry reporting requirements"`
- `"<state> drug manufacturer license requirements"`
- `"<state> wholesale drug distributor license"`
- `"<state> pharmaceutical gift ban physician disclosure"`
- `"<state> clinical trial registration notification requirements"`

---

## Step 4: Write the Markdown report

Write the results to: `server/scripts/<city_lowercase>_<state_lowercase>_research.md`

Use this format — each requirement MUST use the regulation keys from Step 2's context:

```markdown
# <City>, <State> — Compliance Research

**Researched by**: Claude Code (web search)
**Date**: <today's date>
**County**: <county or N/A>
**Has Local Ordinance**: <true/false from context>

---

## General Labor

### minimum_wage

#### State Minimum Wage
- **regulation_key**: `state_minimum_wage`
- **rate_type**: general
- **jurisdiction_level**: state
- **jurisdiction_name**: <State Name>
- **title**: <State Name> Minimum Wage
- **description**: <detailed explanation of the state-specific rule>
- **current_value**: $X.XX/hr
- **numeric_value**: X.XX
- **effective_date**: YYYY-MM-DD
- **source_url**: <URL>
- **source_name**: <source name>
- **requires_written_policy**: false

#### Tipped Minimum Wage
- **regulation_key**: `tipped_minimum_wage`
...

### overtime

*Federal only — no state-specific requirements beyond FLSA.*

### sick_leave
...

## Healthcare
...

## Oncology
...

## Life Sciences
...
```

**Output rules:**
- Group requirements under their category key as a `###` heading
- Each individual requirement is a `####` heading using its title
- Use the **regulation_key** values from the `expected_regulation_keys` in the context JSON. If a requirement doesn't match a known key, create a short snake_case key from the statute name.
- `jurisdiction_level` must be `state` or `city` — NEVER `federal`
- `rate_type` only for `minimum_wage` category: general, tipped, exempt_salary, fast_food, healthcare, etc.
- For leave categories include: `paid`, `max_weeks`, `wage_replacement_pct`, `job_protection`, `employer_size_threshold`
- If a category has NO state or city requirements beyond federal, write: `*Federal only — no state-specific requirements beyond <federal law name>.*`
- Include `requires_written_policy`: true ONLY if the state statute explicitly mandates written disclosure/handbook policy

---

## Step 5: Report results

Tell the user:
1. Whether the jurisdiction was created or already existed
2. Context: has_local_ordinance value and any preemption rules found
3. Summary per group — how many categories had state-specific laws vs federal-only
4. Notable findings (e.g., "CA has daily overtime, mandatory nurse staffing ratios, CMIA beyond HIPAA")
5. Where the markdown file was written
