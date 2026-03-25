# International Compliance Architecture

> Design document for extending Matcha Recruit's compliance system to support international jurisdictions (UK, Mexico, Singapore, etc.).

## Problem

The compliance system was built for US employment law, which has a unique hierarchy: Federal → State → County → City, where cities can pass their own employment ordinances. Internationally, most countries centralize employment law nationally — cities have no override power. The system needs to handle both models.

Additionally, three tables (`regulation_key_definitions`, `regulation_key_definition_history`, `repository_alerts`) were created in raw SQL migrations with no ORM models. If the DB were destroyed, there's no schema documentation to recreate them.

---

## International Employment Law Hierarchy

| Country | Hierarchy | City Override Power | Notes |
|---------|-----------|-------------------|-------|
| **US** | Federal → State → County → City | **Yes** — SF, NYC, LA pass local ordinances | US model is globally unusual |
| **UK** | UK Parliament (Westminster) for GB; Northern Ireland devolved | **None** — London, Manchester have zero employment law power | London Living Wage is voluntary, not law |
| **Mexico** | Federal (LFT) exclusively, per Constitution Art. 123 | **None** — CDMX, states cannot make labor law | ZLFN higher minimum wage is a federal geographic carve-out |
| **Singapore** | National Parliament only. City-state. | N/A — single tier | Ministry of Manpower is sole authority |
| **France** | National (Code du travail) + some collective agreement variations | Very limited | Départements/communes cannot override labor law |
| **Germany** | Federal labor law + state enforcement; works councils at company level | **None** for legislation | Collective bargaining is industry-level, not city-level |

**Key insight**: The US model where cities like San Francisco or New York City can pass their own minimum wage, paid sick leave, or predictive scheduling laws is globally unusual. Most countries centralize employment law at the national or federal level.

---

## Data Architecture

### Jurisdiction Hierarchy

```
jurisdictions
├── id              UUID PK
├── city            VARCHAR(100), nullable
├── state           VARCHAR(10), nullable
├── county          VARCHAR(100), nullable
├── country_code    VARCHAR(2), default 'US'
├── level           ENUM (federal, national, state, province, region, county, city, special_district, regulatory_body)
├── display_name    VARCHAR(200)
├── authority_type  VARCHAR(30), default 'geographic'
├── parent_id       UUID FK → jurisdictions.id (self-referential)
├── requirement_count  INTEGER
├── legislation_count  INTEGER
├── last_verified_at   TIMESTAMP
├── created_at / updated_at
```

**US hierarchy** (existing):
```
Federal (US)
├── California (state)
│   ├── Los Angeles County (county)
│   │   └── Los Angeles (city)
│   └── San Francisco County (county)
│       └── San Francisco (city)
├── New York (state)
│   └── New York City (city)
└── ...
```

**International hierarchy** (new):
```
United Kingdom (national, GB)
├── London (city, GB) — inherits all national law, no local overrides
├── Manchester (city, GB) — same
└── Northern Ireland (province, GB) — devolved employment law

Mexico (national, MX)
└── Mexico City (city, MX) — inherits all federal LFT, minimal local supplements

Singapore (national, SG)
└── (no children — city-state, single tier)
```

### Precedence Rules

```
precedence_rules
├── id                      UUID PK
├── category_id             UUID FK → compliance_categories.id
├── higher_jurisdiction_id  UUID FK → jurisdictions.id
├── lower_jurisdiction_id   UUID FK → jurisdictions.id, nullable
├── applies_to_all_children BOOLEAN (if true, lower_jurisdiction_id must be NULL)
├── precedence_type         ENUM (floor, ceiling, supersede, additive)
├── trigger_condition       JSONB, nullable
├── reasoning_text          TEXT
├── legal_citation          VARCHAR(500)
├── effective_date          DATE
├── sunset_date             DATE, nullable
├── last_verified_at        TIMESTAMP
├── status                  ENUM (active, pending_review, repealed)
├── created_at / updated_at
```

**Precedence types**:
- **`floor`**: Highest numeric value wins (e.g., highest minimum wage between state and city)
- **`ceiling`**: Higher jurisdiction caps lower jurisdiction's value
- **`supersede`**: Most local requirement wins (or higher jurisdiction completely overrides children)
- **`additive`**: All levels apply simultaneously; most local marked as "governing"

**International precedence rules**:

| Country | Precedence | Reasoning |
|---------|-----------|-----------|
| UK → all children | `supersede` on ALL labor/healthcare/oncology categories | Employment law reserved to Westminster Parliament (Employment Rights Act 1996) |
| Mexico → all children | `supersede` on ALL labor categories | LFT is exclusively federal (Constitution Art. 123) |
| Mexico → children | `additive` on `anti_discrimination` only | States can supplement (not override) LFT with additional protections |
| Singapore | No rules needed | Single tier, no children |

**Query resolution** (existing `resolve_jurisdiction_stack` recursive CTE):
```sql
WITH RECURSIVE jurisdiction_chain AS (
    SELECT id, level, parent_id, 0 AS depth
    FROM jurisdictions WHERE id = $1  -- start from city
    UNION ALL
    SELECT j.id, j.level, j.parent_id, jc.depth + 1
    FROM jurisdictions j JOIN jurisdiction_chain jc ON j.id = jc.parent_id
)
-- Returns all requirements up the chain, grouped by category
-- Then determine_governing_requirement() applies precedence rules
```

For Mexico City: walks CDMX → Mexico national. Precedence = supersede → national law governs.
For London: walks London → UK national. Precedence = supersede → UK law governs.
For Singapore: finds single national row, stops. No precedence needed.

### Regulation Key Definitions

```
regulation_key_definitions
├── id                      UUID PK
├── key                     VARCHAR(100), NOT NULL
├── category_slug           VARCHAR(50), NOT NULL
├── category_id             UUID FK → compliance_categories.id
├── UNIQUE(category_slug, key)
│
├── name                    VARCHAR(200)
├── description             TEXT
│
├── enforcing_agency        VARCHAR(200)
├── authority_source_urls   TEXT[]
│
├── state_variance          VARCHAR(20), default 'Moderate'  -- High/Moderate/Low
├── base_weight             NUMERIC(3,1), default 1.0
│
├── applies_to_levels       TEXT[], default '{state,city}'
├── min_employee_threshold  INTEGER
├── applicable_entity_types TEXT[]
├── applicable_industries   TEXT[]
├── applicable_countries    TEXT[], nullable  -- NEW: NULL = universal, '{MX}' = Mexico-only
│
├── update_frequency        VARCHAR(100)
├── staleness_warning_days  INTEGER, default 90
├── staleness_critical_days INTEGER, default 180
├── staleness_expired_days  INTEGER, default 365
│
├── key_group               VARCHAR(100)
├── created_by              UUID FK → users.id
├── notes                   TEXT
├── created_at / updated_at
```

**Key scoping design**: The unique constraint is `(category_slug, key)` — keys are globally unique concepts. The `applicable_countries` column annotates which countries a key is relevant to:
- `NULL` = universal (e.g., `national_minimum_wage` applies to every country)
- `'{MX}'` = Mexico-only (e.g., `aguinaldo_christmas_bonus`)
- `'{GB}'` = UK-only (e.g., `uk_auto_enrolment_pension`)
- `'{MX,CO,PE}'` = multiple Latin American countries

**How keys link to requirements**: Each `jurisdiction_requirements` row has:
- `regulation_key` (text) — the key string
- `key_definition_id` (UUID FK) — links to the definition for metadata/staleness

The same key definition can be referenced by requirements in different jurisdictions. `aguinaldo_christmas_bonus` has one definition but can appear in Mexico City, Guadalajara, Monterrey, etc.

### Key Definition Categories

**~355 existing US keys** across:
- Labor (99): minimum_wage, overtime, sick_leave, leave, meal_breaks, pay_frequency, final_pay, scheduling_reporting, workplace_safety, workers_comp, anti_discrimination, minor_work_permit
- Healthcare (229): hipaa_privacy, billing_integrity, clinical_safety, healthcare_workforce, corporate_integrity, research_consent, state_licensing, emergency_preparedness, + 17 medical compliance categories
- Oncology (25): radiation_safety, chemotherapy_handling, tumor_registry, oncology_clinical_trials, oncology_patient_rights

**~50 new international keys** in three tiers:

#### Universal keys (shared across countries)

| Category | Key | Name |
|----------|-----|------|
| minimum_wage | `national_minimum_wage` | National Minimum Wage |
| sick_leave | `statutory_sick_leave` | Statutory Sick Leave |
| leave | `annual_leave_entitlement` | Annual Leave Entitlement |
| leave | `statutory_maternity_leave` | Statutory Maternity Leave |
| leave | `statutory_paternity_leave` | Statutory Paternity Leave |
| leave | `severance_pay` | Statutory Severance Pay |
| leave | `statutory_notice_period_employer` | Statutory Notice Period (Employer) |
| workers_comp | `social_insurance_employer` | Employer Social Insurance Contributions |
| scheduling_reporting | `maximum_working_hours` | Maximum Working Hours |

#### Mexico-specific keys

| Category | Key | Name | Enforcing Agency |
|----------|-----|------|-----------------|
| minimum_wage | `zlfn_border_zone_minimum_wage` | ZLFN Border Zone Minimum Wage | CONASAMI |
| sick_leave | `imss_sick_leave` | IMSS Sick Leave Benefits | IMSS |
| leave | `vacation_premium` | Vacation Premium (Prima Vacacional) | STPS |
| leave | `aguinaldo_christmas_bonus` | Aguinaldo (Christmas Bonus) | STPS |
| leave | `ptu_profit_sharing` | PTU Profit Sharing | STPS / SAT |
| leave | `seniority_premium` | Seniority Premium (Prima de Antigüedad) | STPS |
| final_pay | `finiquito` | Finiquito (Settlement Receipt) | Tribunal Laboral |
| final_pay | `liquidacion` | Liquidación (Full Severance) | Tribunal Laboral |
| scheduling_reporting | `sunday_premium` | Sunday Premium (Prima Dominical) | STPS |
| workers_comp | `imss_employer_contribution` | IMSS Occupational Risk Premium | IMSS |
| workers_comp | `infonavit_contribution` | INFONAVIT Housing Contribution | INFONAVIT |
| workers_comp | `sar_retirement_contribution` | SAR Retirement Contribution | IMSS / AFORE |
| workplace_safety | `stps_nom_standards` | STPS NOM Standards (41 NOMs) | STPS |
| anti_discrimination | `nom_035_psychosocial_risk` | NOM-035 Psychosocial Risk Prevention | STPS |
| hipaa_privacy | `national_health_privacy_law` | National Health Privacy Law (LFPDPPP) | INAI/SABG |
| hipaa_privacy | `lfpdppp_health_data` | LFPDPPP Sensitive Health Data | INAI/SABG |
| clinical_safety | `cofepris_facility_standards` | COFEPRIS Facility Standards | COFEPRIS |
| state_licensing | `cofepris_sanitary_license` | COFEPRIS Sanitary License | COFEPRIS |
| research_consent | `national_research_consent_law` | National Research Consent Law | COFEPRIS |
| research_consent | `cofepris_research_authorization` | COFEPRIS Research Authorization | COFEPRIS |
| radiation_safety | `national_radiation_control` | National Radiation Control (CNSNS) | CNSNS |
| chemotherapy_handling | `national_hazardous_drug_handling` | National Hazardous Drug Handling | COFEPRIS/SEMARNAT |
| tumor_registry | `national_cancer_registry` | Registro Nacional de Cáncer | Secretaría de Salud |
| billing_integrity | `national_anti_corruption_healthcare` | National Anti-Corruption (Healthcare) | SFP |
| corporate_integrity | `national_whistleblower_protection` | National Whistleblower Protection | SFP |
| emergency_preparedness | `national_emergency_preparedness` | National Emergency Preparedness | SINAPROC |
| oncology_patient_rights | `palliative_care_access` | Palliative Care Access | Secretaría de Salud |
| healthcare_workforce | `professional_licensing` | Professional Licensing (Cédula Profesional) | SEP |

#### UK-specific keys

| Category | Key | Name |
|----------|-----|------|
| leave | `shared_parental_leave` | Shared Parental Leave |
| leave | `adoption_leave` | Statutory Adoption Leave |
| workers_comp | `uk_auto_enrolment_pension` | Auto-Enrolment Workplace Pension |
| workers_comp | `social_insurance_employee` | Employee Social Insurance (National Insurance) |

#### Singapore-specific keys

| Category | Key | Name |
|----------|-----|------|
| workers_comp | `cpf_employer_contribution` | CPF Employer Contribution |
| workers_comp | `foreign_worker_levy` | Foreign Worker Levy |

### Regulation Key Definition History

```
regulation_key_definition_history
├── id                  UUID PK
├── key_definition_id   UUID FK → regulation_key_definitions.id, CASCADE
├── field_changed       VARCHAR(100)
├── old_value           TEXT
├── new_value           TEXT
├── changed_at          TIMESTAMP
├── changed_by          UUID FK → users.id
├── change_reason       TEXT
```

Tracks changes to key definitions (e.g., when an enforcing agency changes, when staleness SLAs are adjusted).

### Repository Alerts

```
repository_alerts
├── id                  UUID PK
├── alert_type          VARCHAR(30)  -- 'stale', 'missing', 'expiring', 'new_key'
├── severity            VARCHAR(20)  -- 'warning', 'critical', 'expired'
├── jurisdiction_id     UUID FK → jurisdictions.id, CASCADE
├── key_definition_id   UUID FK → regulation_key_definitions.id, CASCADE
├── requirement_id      UUID FK → jurisdiction_requirements.id, SET NULL
├── category            VARCHAR(50)
├── regulation_key      VARCHAR(100)
├── message             TEXT
├── days_overdue        INTEGER
├── status              VARCHAR(20), default 'open'  -- 'open', 'acknowledged', 'resolved'
├── created_at          TIMESTAMP
├── acknowledged_at     TIMESTAMP
├── acknowledged_by     UUID FK → users.id
├── resolved_at         TIMESTAMP
├── resolved_by         UUID FK → users.id
├── resolution_note     TEXT
│
├── UNIQUE(jurisdiction_id, key_definition_id, alert_type) WHERE status = 'open'
```

Generated by staleness scanning jobs. Alerts admin when jurisdiction requirements are overdue for verification based on the key definition's staleness SLA.

---

## ORM Models

### Existing (documented in `server/app/orm/`)

| Model | File | Table |
|-------|------|-------|
| `Jurisdiction` | `jurisdiction.py` | `jurisdictions` |
| `ComplianceCategory` | `jurisdiction.py` | `compliance_categories` |
| `PrecedenceRule` | `jurisdiction.py` | `precedence_rules` |
| `JurisdictionRequirement` | `requirement.py` | `jurisdiction_requirements` |
| `PolicyChangeLog` | `requirement.py` | `policy_change_log` |
| `BusinessLocation` | `location.py` | `business_locations` |
| `ComplianceRequirement` | `compliance.py` | `compliance_requirements` |
| `EmployeeJurisdiction` | `employee.py` | `employee_jurisdictions` |

### Missing (need ORM models — `server/app/orm/key_definition.py`)

| Model | Table | Created in Migration |
|-------|-------|---------------------|
| `RegulationKeyDefinition` | `regulation_key_definitions` | `p1q2r3s4t5u6` |
| `RegulationKeyDefinitionHistory` | `regulation_key_definition_history` | `p1q2r3s4t5u6` |
| `RepositoryAlert` | `repository_alerts` | `p1q2r3s4t5u6` |

### Missing Enum Values (in `server/app/orm/enums.py`)

`JurisdictionLevel` is missing values that exist in the DB:
- `national` — for country-level jurisdictions (UK, Mexico, Singapore)
- `province` — for devolved regions (Northern Ireland)
- `region` — for sub-national regions

---

## How the System Works End-to-End

### 1. Jurisdiction Creation
```
create_jurisdiction.py "Mexico City" "CDMX" --country MX
```
- Creates city-level jurisdiction row
- Auto-links `parent_id` to Mexico national jurisdiction (if exists)

### 2. Research
```
/research-jurisdiction Mexico City
```
- `jurisdiction_context.py` returns expected keys filtered by `applicable_countries`
- For MX: returns universal keys + MX-specific keys (aguinaldo, PTU, etc.)
- For US: returns existing US keys only

### 3. Ingest
```
ingest_research_md.py scripts/mexico_city_mx_research.md --city "Mexico City" --state CDMX --country MX
```
- Parses markdown into requirement dicts
- Upserts into `jurisdiction_requirements` with `jurisdiction_id` = Mexico City's UUID
- Links `key_definition_id` by matching `(category, regulation_key)` → `regulation_key_definitions`

### 4. Query (runtime)
```
resolve_jurisdiction_stack(mexico_city_jurisdiction_id)
```
- Recursive CTE walks: Mexico City → Mexico national
- Returns requirements from both levels, grouped by category
- `determine_governing_requirement()` checks precedence rules:
  - Labor categories: `supersede` → national law governs
  - Anti-discrimination: `additive` → both levels apply
- Returns `{governing_requirement, all_levels, precedence_type}` per category

### 5. Gap Detection
```
get_missing_regulations("leave", existing_keys, country_code="MX")
```
- Looks up `EXPECTED_REGULATION_KEYS["leave"]`
- Filters by `applicable_countries` containing MX (or NULL)
- Returns keys not yet present in the jurisdiction's requirements

### 6. Staleness Monitoring
- Scanning job checks `jurisdiction_requirements.last_verified_at` against `regulation_key_definitions.staleness_*_days`
- Creates `repository_alerts` when requirements are overdue
- Admin dashboard shows alerts by jurisdiction/severity

---

## Adding a New Country

To add support for a new country (e.g., Germany):

1. **Create national jurisdiction**: `create_jurisdiction.py --country DE` (creates national row + any city rows)
2. **Research hierarchy**: Does the country allow local employment ordinances? (Germany: no)
3. **Add precedence rules**: If flat, add `supersede` from national to all children
4. **Add country-specific key definitions**: e.g., `kurzarbeit`, `works_council_mandate`, `betriebsrat`
5. **Research and ingest**: `/research-jurisdiction-intl Berlin` → ingest markdown
6. **Key definitions auto-link**: Ingest script matches `regulation_key` to `key_definition_id`

No code changes needed — just migration seeds for key definitions and precedence rules.

---

## Design Principle: Policies as Independent Units

Each requirement/policy is an independent, atomic unit — like a stock on an exchange.

| Concept | Compliance System | Stock Market Analogy |
|---------|------------------|---------------------|
| Key definition | `regulation_key_definitions` | Ticker symbol registry (AAPL, GOOGL) |
| Master repository | `jurisdiction_requirements` | Exchange listings (AAPL on NASDAQ at $X) |
| Company portfolio | `compliance_requirements` | Company's holdings (this firm holds AAPL, GOOGL) |
| Category | `compliance_categories` | Sector/index (Tech, Healthcare) |
| Admin cherry-pick | Manual assignment | Adding a single stock regardless of sector |

**Why this matters**: Companies typically inherit entire categories based on their business profile (a healthcare company gets all healthcare categories). But occasionally, admin needs to assign 1-2 specific policies from another category — like a tech company that handles medical data needing just `hipaa_privacy` requirements without the full healthcare suite.

**Current state**: The data model fully supports this. Each row in `jurisdiction_requirements` is independently addressable via `requirement_key` + `jurisdiction_id`. The sync function (`_sync_requirements_to_location()`) processes requirements individually, not as category batches. `is_bookmarked` and `is_pinned` work at the individual requirement level.

**Gap**: No admin endpoint exists to manually add individual requirements from another category to a company location. Needed: `POST /admin/locations/{location_id}/requirements/add` with `governance_source = 'admin_override'`.

---

## Runtime Code Audit Findings

Issues discovered when auditing the compliance service against international jurisdiction requirements:

| Issue | Severity | Location | Fix |
|-------|----------|----------|-----|
| `resolve_jurisdiction_stack()` CTE doesn't SELECT/filter `country_code` | HIGH | compliance_service.py ~8107 | Add `country_code` to CTE + WHERE clause to prevent cross-country traversal |
| `get_missing_regulations()` ignores country | HIGH | compliance_registry.py ~4565 | Add `country_code` parameter; filter by `applicable_countries` |
| `jurisdiction_context.py` serves US-centric expected keys to all countries | MEDIUM | jurisdiction_context.py ~77 | Query `regulation_key_definitions` with `applicable_countries` filter for non-US |
| Key definition linking doesn't validate `applicable_countries` | MEDIUM | ingest_research_md.py ~269 | Add JOIN to jurisdictions + WHERE on `applicable_countries` |
| Coverage dashboard not filtered by `country_code` | MEDIUM | admin.py ~3877 | Filter CROSS JOIN by country |
| `_filter_with_preemption()` assumes US state codes | LOW | compliance_service.py ~3807 | Add guard for non-US country_code |
| `determine_governing_requirement()` defaults to "most local" when no precedence rule exists | LOW | compliance_service.py ~8237 | Acceptable — adding explicit precedence rules for all international jurisdictions makes this a non-issue |

All fixes are backward-compatible (don't affect existing US jurisdictions).

---

## Known Issues & Data Quality

### Key Definition Linkage Gap (US)

**Status**: 2,131 of 2,173 requirements (98%) have `key_definition_id = NULL`.

**Root cause**: The original key definition backfill (migration `p1q2r3s4t5u6`) matched `regulation_key` against `regulation_key_definitions.key`, but legacy US data from Gemini research uses long descriptive strings as `regulation_key` (e.g., `"fair employment and housing act feha protected classes"`, `"general"`, `"tipped"`) instead of canonical short keys (`protected_classes`, `state_minimum_wage`, `tipped_minimum_wage`).

Only 42 rows currently match — those are from newer research that used canonical keys (London, recent ingest script runs).

**Impact**: Without `key_definition_id`:
- No staleness SLA tracking for those requirements
- No enforcing agency metadata linkage
- No base_weight for severity scoring
- Gap detection still works (uses `regulation_key` string matching via `EXPECTED_REGULATION_KEYS`)

**Fix (future task)**: Normalize legacy `regulation_key` values to canonical keys. This involves:
1. Building a mapping of 1,668 distinct descriptive strings → 353 canonical keys
2. Updating `regulation_key` and `key_definition_id` for all matched rows
3. Creating new key definitions for any genuinely new keys not in the 353 set

The problem won't grow — the ingest script (`ingest_research_md.py`) now writes canonical keys for all new data.

### London Miscategorized Requirements

**Status**: 13 of London's 46 requirements are in wrong categories due to the `ingest_research_md.py` parser bug (now fixed) that skipped single-word category headers like `overtime` and `leave`.

**Affected keys**:

| Current Category | Should Be | Keys |
|-----------------|-----------|------|
| `minimum_wage` | `overtime` | `daily_weekly_overtime` |
| `sick_leave` | `leave` | `annual_leave_entitlement`, `statutory_maternity_leave`, `statutory_paternity_leave`, `shared_parental_leave`, `adoption_leave`, `bereavement_leave`, `severance_pay`, `statutory_notice_period_employer`, `emergency_dependant_leave`, `state_family_leave`, `jury_duty_leave` |
| `minor_work_permit` | `anti_discrimination` | `uk_unfair_dismissal` |

**Fix**: Included in the international migration — UPDATE statements to correct `category` and `category_id` for these rows.

### `current_value` Column Width

**Status**: Column is `VARCHAR(100)`. Max value in DB is exactly 100 characters. Mexico City research data has values exceeding 100 chars (e.g., `"3 months SDI + 20 days SDI/year of service + seniority premium + accrued benefits (unjust dismissal)"`).

**Fix**: Widen to `VARCHAR(500)` in the international migration. ORM updated to match.

---

## Implementation Status

### Completed
- [x] Research: Mexico City (58 requirements across labor, healthcare, oncology)
- [x] Research: NYC life sciences (11 requirements)
- [x] Research: Boston life sciences (8 requirements)
- [x] Fix: `ingest_research_md.py` parser for single-word categories
- [x] Architecture doc (this file)

### Next: International Migration
- [ ] ORM models for `regulation_key_definitions`, history, alerts (`server/app/orm/key_definition.py`)
- [ ] Enum values: `national`, `province`, `region` in `JurisdictionLevel` (`server/app/orm/enums.py`)
- [ ] Migration: `applicable_countries` column on `regulation_key_definitions`
- [ ] Migration: Seed ~50 international key definitions
- [ ] Migration: Create national jurisdiction rows (UK, MX, SG) + parent linking
- [ ] Migration: Precedence rules (UK supersede, MX supersede + additive)
- [ ] Migration: Widen `current_value` to VARCHAR(500)
- [ ] Migration: Fix London miscategorized requirements
- [ ] Migration: Backfill `key_definition_id` (direct match)
- [ ] Fix `resolve_jurisdiction_stack()` CTE — add `country_code` safety (`compliance_service.py`)
- [ ] Fix `get_missing_regulations()` — country-aware gap detection (`compliance_registry.py`)
- [ ] Fix `jurisdiction_context.py` — country-filtered expected keys
- [ ] Fix `ingest_research_md.py` — validate `applicable_countries` on key linking
- [ ] Update `compliance_registry.py` with `_INTERNATIONAL_REGULATION_KEYS`
- [ ] Update `create_jurisdiction.py` for auto parent linking
- [ ] Ingest: Mexico City, NYC life sciences, Boston life sciences

### Future Work
- [ ] Normalize legacy US `regulation_key` values to canonical keys (1,668 strings → 353 definitions)
- [ ] Admin cherry-pick endpoint: `POST /admin/locations/{location_id}/requirements/add`
- [ ] Admin coverage dashboard: filter by `country_code`
- [ ] `_filter_with_preemption()`: guard for non-US country_code
- [ ] Add more international jurisdictions (France, Germany, etc.)
- [ ] Northern Ireland devolved employment law research
