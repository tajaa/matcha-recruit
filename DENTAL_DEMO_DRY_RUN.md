# Demo dry run — LA dental office on Matcha-X (2026-07-14)

Simulated the exact demo flow against dev, end to end, as a customer would:

1. `POST /api/auth/register/business` → `tier=matcha_x`, `industry=healthcare`,
   `healthcare_specialties=['dental']` → **Sunset Smile Dental Group**
   (company `287fffb5-…`, `signup_source=matcha_x`, approved, X overlay live:
   `compliance_lite, credential_templates, discipline, employees, handbook_audit,
   handbook_pilot, handbooks, training`).
2. `POST /api/matcha-x-onboarding/locations` → 3435 Wilshire Blvd, Los Angeles, CA 90010.
3. `POST /api/employees/bulk-upload?send_invitations=false` → **44 employees, 0 emails sent**
   (8 general dentists, 2 orthodontists, 1 oral surgeon, 4 RDH, 20 RDA, 1 sterilization tech,
   8 admin/front-office). Roster: `scratchpad/roster.csv`. 35 credential rows,
   licenses seeded across expired / <30d / <90d / current.
4. `POST /api/matcha-x-onboarding/build/stream` → SSE ran to `complete`:
   *"Your compliance baseline is live"* — 1 location, 84 requirements, 273 codified.

Then read exactly what the tenant's Compliance tab is served.

## Verdict: the demo fails on all three legs

| Leg | Expected | Actual |
|---|---|---|
| Federal | applicable federal employment law | 21 rows, but the wrong ones (below) |
| State (CA) | CA wage/hour + employment law | 62 rows, **zero minimum wage, overtime, meal breaks, or state sick leave** |
| Dental-specific | dental-office obligations | **0 rows. The concept does not exist.** |
| Expiration dates | per-requirement dates | **not in the API response at all** |
| Employees out of compliance | count on Compliance tab | **no such concept on that page** |

### 1. California's core wage law never reaches the tenant

The tab has **no `minimum_wage`, no `overtime`, no `meal_breaks`, no state `sick_leave`**
row — in California. The rows exist in the catalog (18 minimum-wage rows, incl.
"California State Minimum Wage · $16.90/hr"). They are simply unreachable.

**Root cause: 1,709 of 2,724 active catalog rows (63%) are misparented.**
A row carries a *stamped* `jurisdiction_level` / `jurisdiction_name`, and separately a
`jurisdiction_id` FK to its parent. On 63% of rows these disagree:

| stamped level | actual parent level | rows |
|---|---|---|
| state | city | 1157 |
| state | county | 245 |
| national | city | 232 |
| federal | city | 49 |

Both "California State Minimum Wage" rows are stamped `state`/`California` but physically
hang off **city** jurisdictions — one off `Beverly Hills, CA`, one off a garbage jurisdiction
literally named **`ca, CA`** (city level, 100 requirements). Chain resolution walks
`jurisdiction_id` (LA city → LA county → CA → US), so a state law filed under Beverly Hills
is invisible to Los Angeles. The hierarchy — the whole point of the system — is broken at
the data layer for most of the catalog.

Also: LA city has **no minimum-wage row at all** (LA has its own city minimum wage),
and the LA chain is fragmented across four jurisdiction names
(`Los Angeles`, `Los Angeles, CA`, `Los Angeles (City)`, `City of Los Angeles`,
plus `_county_los angeles, CA`).

### 2. The build reports success while partially failing

The stream emitted a `warning` and then `complete`:

```
insert or update on table "compliance_requirements" violates foreign key constraint
"compliance_requirements_jurisdiction_requirement_id_fkey"
DETAIL: Key (jurisdiction_requirement_id)=(072fab83-…) is not present in "jurisdiction_requirements".
```

`_upsert_jurisdiction_requirements` (`compliance_service.py:2867`) — *"Remove jurisdiction rows
not in new result set"* — **DELETEs catalog rows whose `requirement_key` isn't in this one run's
results**. Two consequences:

- The in-flight `requirements` list still holds `jurisdiction_requirement_id` for rows it just
  deleted (stamped at load, `:1401`), so the next call — `_sync_requirements_to_location`
  (`:5418`) — inserts a per-location row pointing at a dead catalog id → FK violation → the
  location's sync aborts mid-way. The user is told the baseline is live.
- That DELETE is against the **shared SSOT catalog**. One tenant's research pass can delete
  jurisdiction rows every other tenant depends on.

Re-running the build does **not** heal it — same warning, same 84 rows, still zero wage rows.

### 3. "Dental-specific compliance" does not exist — two independent reasons

- **Catalog:** zero dental rows. (All 17 rows matching `%dental%` are *California Acci**dental**
  Release Prevention*.) The sub-industry vocabulary in `compliance_registry.py` has
  `healthcare:oncology`, `:pharmacy`, `:behavioral_health`, `:primary_care`, `:telehealth`,
  `:managed_care`, `:transplant` — **no `healthcare:dental`**. No Dental Practice Act, no Dental
  Board of California licensure/CE, no radiation-safety/RDA rules, no dental infection control.
- **Build:** the Matcha-X build only researches `MATCHA_X_LITE_CATEGORIES` — 9 labor categories
  (min wage, overtime, sick leave, meal breaks, pay frequency, final pay, anti-discrimination,
  workplace safety, i9). Industry-specific research is *by design* not part of X.

What the dental office actually gets under the `healthcare` tag (38 rows) is **the whole of
healthcare**: SAMHSA opioid-treatment-program certification, Lanterman-Petris-Short involuntary
psychiatric holds, MIPS/APM quality reporting, Medi-Cal provider enrollment, mental-health parity.
None apply to a dental practice. The industry filter is one flat `healthcare` bucket — an
oncology-vs-dental distinction it cannot make.

### 4. Expiration dates never reach the tab

`expiration_date` is NULL on all 2,618 active catalog rows, and `RequirementResponse` **does not
carry the field at all** (`compliance_service.py:6377`) even though both
`jurisdiction_requirements.expiration_date` and `compliance_requirements.expiration_date` exist in
the schema. No renewal/next-review date is reachable from the Compliance tab.

### 5. "Employees out of compliance" — right answer, wrong page, half the roster invisible

`GET /api/dashboard/credential-expirations` **works**: `{expired: 4, critical: 4, warning: 5}`,
13 named rows with job titles. But:

- It lives on the **Dashboard, not the Compliance tab**. The Compliance page has no employee
  dimension at all (its only employee number is minimum-wage violation counts — which are 0 here,
  because no minimum-wage row was synced).
- It only sees expiry dates **someone typed in**. It can never see a *missing* credential:
  `bulk_upload.py` never calls `resolve_credential_requirements` (only single-employee `POST
  /employees` and HRIS sync do), so the CSV import produced **0 `employee_credential_requirements`**.
- **20 of 44 employees resolve to nothing.** `GET /credential-templates/preview?state=CA&job_title=
  Registered Dental Assistant` → `{"role_category": null, "requirements": []}`. `role_categories`
  has `dentist` (`dds|dmd|oral surgeon`) but **no dental assistant and no dental hygienist** — the
  largest staff block in any dental practice is invisible to credentialing. (A DDS license is also
  labelled "Medical License" in the customer-facing UI.)

## Fix order (smallest first, biggest payoff first)

1. **Re-parent the catalog** — 1,709 rows to their stamped level's jurisdiction; merge the LA
   jurisdiction variants; delete/merge the `ca, CA` garbage jurisdiction. Without this nothing
   else matters: the chain can't see the law. *This alone restores CA wage/hour to the tab.*
2. **Stop the catalog-destroying DELETE** in `_upsert_jurisdiction_requirements`, and refresh
   `jurisdiction_requirement_id` from the post-upsert state before sync (kills the FK abort).
3. **Fail the build loudly** — never emit `complete: baseline is live` after a location errored.
4. **`healthcare:dental` sub-industry** — tag + core keyset + author the CA dental rows
   (Dental Practice Act, Dental Board licensure/CE, RDA duties + radiation safety, infection
   control), and add dental categories to the X build (or accept that X is wage-and-hour only
   and sell dental scope as Pro).
5. **`role_categories`: add `dental_hygienist` + `dental_assistant`**, with CA credential
   templates (RDA/RDH licence, radiation safety, BLS, infection control).
6. **Surface expiry on the Compliance tab** — add `expiration_date` to `RequirementResponse`,
   and put the credential-expiration roll-up on the Compliance page.
7. Call `resolve_credential_requirements` from the bulk-upload path so an imported roster gets
   *required*-credential gaps, not just typed-in expiry dates.

## Demo assets

- Roster CSV (44, reserved-domain emails): `scratchpad/roster.csv`
- Tenant: `maria.chen@example.com` / `DemoPass2026!` — company `287fffb5-ea50-40a2-bf07-6b5c2ca3c400`,
  location `59bf0bdc-558f-4530-8917-a792eb7f5d98` (dev DB only).
