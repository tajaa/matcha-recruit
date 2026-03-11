# Cost of Risk — Risk Assessment Dashboard Feature

## Context

The risk assessment dashboard currently scores companies 0-100 across 5 dimensions, but the scores are abstract. Adding estimated dollar exposure ("cost of risk") makes the risk tangible — a score of 45 means something different when you see it translates to $45K-$127K in potential liability. Categories: wage misclassification back pay, HIPAA fines, lapsed credential penalties, ER litigation defense costs, and OSHA incident penalties.

## Data-Driven Approach: Industry-Specific Cost Benchmarks

Rather than hardcoded dollar ranges, cost estimates should be calibrated using **public federal enforcement data** keyed to the company's NAICS code. This makes exposure calculations specific to the company's industry (e.g., hospitality vs. manufacturing vs. healthcare).

### Lookup Table Strategy

Maintain a static `industry_risk_benchmarks` JSON table (refreshed quarterly) derived from bulk federal datasets. The company's NAICS code (or a mapping from their free-text `industry` field) is the lookup key. Each entry contains:

- **Median back wages per employee** (from DOL WHD data for that NAICS)
- **Median OSHA penalty by violation type** (from OSHA enforcement data for that NAICS)
- **EEOC charge rate per 1,000 employees** (from EEOC stats + BLS employment counts for that NAICS)
- **Injury incidence rate per 100 FTE** (from BLS SOII for that NAICS)

When industry-specific data is unavailable, fall back to the all-industry median.

### Primary Data Sources

| Dataset | Access | Update Cadence | Key Use |
|---|---|---|---|
| **DOL WHD Compliance Actions** | Free REST API (`developer.dol.gov`) + bulk CSV | Ongoing | Back wages per employee by NAICS |
| **OSHA Enforcement (Inspections + Violations)** | Free REST API (`developer.dol.gov`) + daily CSV | Daily | Actual penalty amounts by NAICS + violation type |
| **EEOC Enforcement Statistics** | Free XLSX (`eeoc.gov/data`) | Annual | Charge counts, merit resolution rates, avg settlements by basis |
| **BLS SOII** | Free XLSX (`bls.gov/iif`) | Annual | Injury/illness incidence rates by NAICS |
| **HHS OCR Breach Portal** | Free web portal (`ocrportal.hhs.gov`) | Ongoing | Breach frequency by entity type, enforcement action rates |
| **NPDB Public Use File** | Free CSV (`npdb.hrsa.gov`) | Quarterly | Adverse licensure action rates by practitioner type + state |

See **Appendix: Public Dataset Reference** at the end of this document for full details.

## Cost Categories by Dimension

### Compliance Dimension (computed from real data + static estimates)

| Category | Source | Formula |
|---|---|---|
| **Hourly wage shortfall** | `employee_violations` where `pay_classification == "hourly"` | `shortfall/hr * 2080hrs * 2-3yr lookback * 2x liquidated damages` |
| **Exempt misclassification** | `employee_violations` where `pay_classification == "exempt"` | `(salary/2080) * 1.5 OT rate * 5-10hrs/wk * 52wks * 2-3yr * 2x damages` |
| **HIPAA breach exposure** *(healthcare only)* | Static estimate from `total_employees` | `employee_count * $145-$1,452` per potential violation (2026 penalty tiers) |
| **Lapsed credential risk** *(healthcare only)* | Static estimate from `total_employees` | `employee_count * 10% assumed lapse rate * $1K-$10K per lapse` |

### ER Cases Dimension (computed from real data)

| Category | Source | Formula |
|---|---|---|
| **ER litigation exposure** | `pending_determination`, `in_review`, `open` counts | Per-case ranges * 17% merit resolution probability (EEOC FY2024), boosted if policy violation flags |

### Incidents Dimension (computed from real data)

| Category | Source | Formula |
|---|---|---|
| **Open incident penalties** | `open_critical/high/medium` counts | OSHA penalty ranges per severity level |

### Workforce & Legislative Dimensions
No cost calculations (no direct dollar-quantifiable data). These dimensions will not show cost sections.

## Healthcare Detection

Query `companies.industry` for the company (field exists as free-text string). Match case-insensitively against: `healthcare`, `hospital`, `medical`, `nursing`, `clinic`, `health care`. The `industry_compliance_profiles` table also has a "Healthcare" profile that could be cross-referenced.

## UI Placement: Inside Each Dimension Card

Cost breakdowns render as an inner sub-card inside each `DimensionCard` (same `border border-white/10 bg-black/20 p-3 rounded-xl` style as the existing "Employee Compliance Alerts" sub-section in the compliance card). Only dimensions with cost data show the section. Format: category label + dollar range + small basis text.

## Detailed Formulas

### 1. Hourly Wage Shortfall (Back Pay + Liquidated Damages)

For each hourly employee with a shortfall below local minimum wage:
- `low = shortfall_per_hour * 2080 * 2 * 2` (2-year lookback + equal liquidated damages)
- `high = shortfall_per_hour * 2080 * 3 * 2` (3-year lookback for willful violations + liquidated damages)
- `shortfall` is the per-hour dollar gap between the employee's rate and the jurisdictional minimum
- Legal basis: FLSA § 216(b) — 2-year statute of limitations (3 years for willful), liquidated damages equal to back pay

**Example:** Employee paid $13/hr in a $15/hr jurisdiction → $2/hr shortfall
- Low: $2 × 2,080 × 2 × 2 = **$16,640**
- High: $2 × 2,080 × 3 × 2 = **$24,960**

### 2. Exempt Misclassification (Overtime Back Pay + Liquidated Damages)

For each exempt employee below the salary threshold (potential misclassification as exempt when role may not qualify):
- `effective_hourly = pay_rate / 2080`
- `overtime_rate = effective_hourly * 1.5`
- `low = overtime_rate * 5 hrs/wk * 52 weeks * 2 years * 2x` (conservative 5 OT hours/week)
- `high = overtime_rate * 10 hrs/wk * 52 weeks * 3 years * 2x` (aggressive 10 OT hours/week, willful)
- `pay_rate` and `threshold` are annual salary figures
- Legal basis: DOL recovered $274M in back wages in FY2023. States like CA (AB5), NJ, and MA apply strictest tests.

**Example:** Employee earning $40,000/yr in a $43,888 threshold jurisdiction
- Effective hourly: $40,000 / 2,080 = $19.23
- OT rate: $19.23 × 1.5 = $28.85
- Low: $28.85 × 5 × 52 × 2 × 2 = **$30,004**
- High: $28.85 × 10 × 52 × 3 × 2 = **$90,012**

### 3. HIPAA Breach Exposure (Healthcare Only — Static Estimate)

- `low = total_employees * $145` (Tier 1: lack of knowledge, per-violation minimum)
- `high = total_employees * $1,452` (Tier 2: reasonable cause, per-violation minimum)
- Legal basis: 2026 HIPAA penalty tiers (inflation-adjusted annually):
  - Tier 1 (lack of knowledge): $145 - $36,352 per violation
  - Tier 2 (reasonable cause): $1,452 - $72,703 per violation
  - Tier 3 (willful neglect, corrected): $14,520 - $72,703 per violation
  - Tier 4 (willful neglect, not corrected): $72,703 - $2,190,294 per violation
  - Annual cap per identical provision: up to $2,190,294
- Each employee handling PHI represents a potential violation point.
- Data source: HHS OCR publishes all resolution agreements with penalty amounts at `hhs.gov/hipaa/for-professionals/compliance-enforcement/agreements/`. To date: 152 cases totaling $144.9M. Enforcement probability after a reported breach can be derived from (enforcement actions / total breaches reported to OCR portal).

**Example:** 50-employee healthcare company
- Low: 50 × $145 = **$7,250**
- High: 50 × $1,452 = **$72,600**

### 4. Lapsed Credential Risk (Healthcare Only — Data-Informed Estimate)

- `at_risk = ceil(total_employees * lapse_rate)` where `lapse_rate` is derived from NPDB data (default 10% if no industry-specific data available)
- `low = at_risk * $1,000` (state Department of Health minimum fine)
- `high = at_risk * $10,000` (includes Medicare/Medicaid reimbursement repayment exposure)
- If a healthcare employee works on an expired license, the facility faces state DoH fines. More expensively, they may be required to repay all Medicare/Medicaid reimbursements for any patient that unlicensed employee touched during the lapsed period.
- Data source: The **NPDB Public Use File** (`npdb.hrsa.gov/resources/publicData.jsp`) contains all adverse licensure actions reported since 1990, broken down by practitioner type and state. Available as quarterly CSV downloads. The NPDB Data Analysis Tool (`npdb.hrsa.gov/analysistool/`) provides interactive queries. Use this to compute actual adverse action rates by practitioner type instead of the flat 10% assumption.

**Example:** 50-employee healthcare company (using default 10% lapse rate)
- At risk: ceil(50 × 0.10) = 5 employees
- Low: 5 × $1,000 = **$5,000**
- High: 5 × $10,000 = **$50,000**

### 5. ER Litigation Exposure

Per-case estimated defense cost ranges (based on EEOC/defense attorney data):
- `pending_determination`: $75,000 - $200,000 per case (highest risk — unresolved)
- `in_review`: $50,000 - $150,000 per case (actively managed, somewhat lower)
- `open`: $25,000 - $75,000 per case (acknowledged but less acute)

Apply probability adjustment:
- Base probability: **17%** of ER cases reach merit resolution (EEOC FY2024: 88,531 charges filed, ~17% merit resolution rate)
- If `major_policy_violation` flag: multiply high estimate by 1.5x
- If `high_discrepancy` flag: multiply high estimate by 1.5x
- The user's benchmark: an employment lawsuit going to court costs $150,000-$200,000 in legal defense fees

EEOC basis-specific average settlements (for future per-claim-type breakdowns):
- Disability discrimination: ~$52,000
- Hostile work environment: ~$53,200
- Retaliation: ~$45,000
- Sexual harassment: ~$36,800
- Cases reaching jury trial: avg verdict ~$217,000-$250,000
- EEOC charge-to-EEOC-lawsuit rate: ~0.14% (125 EEOC lawsuits out of 88,531 charges in FY2024), though private lawsuits filed after right-to-sue letters are far more common

Data source: EEOC Enforcement and Litigation Statistics (`eeoc.gov/data/enforcement-and-litigation-statistics-0`), published annually as XLSX. No API — manual download.

**Example:** 2 cases pending determination, 1 in review, major policy violation detected
- Low: (2 × $75K + 1 × $50K) × 0.17 = **$34,000**
- High: (2 × $200K + 1 × $150K) × 0.17 × 1.5 = **$140,250**

### 6. Open Incident Penalties (OSHA Ranges)

Direct penalty ranges by severity (2025 OSHA rates, effective Jan 15, 2025):
- Critical: $16,550 - $165,514 per incident (serious/willful violation range)
- High: $5,000 - $50,000 per incident
- Medium: $1,000 - $16,550 per incident
- Low: $0 (not material enough for cost estimation)

No probability discount — open incidents ARE active exposure.

When industry-specific OSHA data is available (via the NAICS lookup table), use the **median actual penalty** for that industry and violation type instead of the static ranges above. The OSHA enforcement dataset contains `penalty_initial` and `penalty_current` for every cited violation, enabling precise industry-specific medians.

Data source: OSHA Enforcement Data via DOL REST API (`developer.dol.gov/health-and-safety/dol-osha-enforcement/`) or daily bulk CSV at `enforcedata.dol.gov`. Tables: inspections (with NAICS), violations (with penalty amounts and type), accidents. Additionally, OSHA publishes **Frequently Cited Standards by NAICS** at `osha.gov/ords/imis/citedstandard.naics` — useful for identifying which standards to watch for a given industry.

**Example:** 1 critical, 2 high severity open incidents
- Low: 1 × $16,550 + 2 × $5,000 = **$26,550**
- High: 1 × $165,514 + 2 × $50,000 = **$265,514**

## UI Mockup

```
┌─────────────────────────────────────┐
│  COMPLIANCE          [MODERATE]     │
│  45 /100                            │
│  ─────────────────                  │
│  · 2 unread critical alerts (+70)   │
│  · 3 employees below min wage       │
│                                     │
│  ┌─ ESTIMATED EXPOSURE ──────────┐  │
│  │  $45K — $127K                 │  │
│  │                               │  │
│  │  Wage Shortfall    $33K-$50K  │  │
│  │  Misclassification $12K-$77K  │  │
│  └───────────────────────────────┘  │
│                                     │
│  ┌─ EMPLOYEE COMPLIANCE ALERTS ──┐  │
│  │  (existing sub-section)       │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  ER CASES              [HIGH]       │
│  62 /100                            │
│  ─────────────────                  │
│  · 2 cases pending determination    │
│  · Major policy violation found     │
│                                     │
│  ┌─ ESTIMATED EXPOSURE ──────────┐  │
│  │  $34K — $140K                 │  │
│  │                               │  │
│  │  Litigation Risk   $34K-$140K │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  INCIDENTS             [HIGH]       │
│  55 /100                            │
│  ─────────────────                  │
│  · 1 open critical incident (+25)   │
│  · 2 open high severity (+30)       │
│                                     │
│  ┌─ ESTIMATED EXPOSURE ──────────┐  │
│  │  $27K — $266K                 │  │
│  │                               │  │
│  │  OSHA Penalties    $27K-$266K │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

## Implementation Files

| File | Changes |
|---|---|
| `server/app/matcha/services/risk_assessment_service.py` | Add dataclasses, `compute_cost_of_risk()`, integrate into `compute_risk_assessment()`, fix `[:10]` cap, add healthcare detection query |
| `server/app/matcha/routes/risk_assessment.py` | Add Pydantic models, update response model, update `_snapshot_to_response()` |
| `client/src/types/index.ts` | Add `CostLineItem`, `CostOfRisk` interfaces, extend `RiskAssessmentResult` |
| `client/src/pages/RiskAssessment.tsx` | Extend `DimensionCard` with cost sub-section, add `formatCostRange()` helper |

## Edge Cases

- **No violations/cases:** Cost section doesn't render in that dimension's card
- **Non-healthcare companies:** HIPAA and lapsed credential categories skipped entirely
- **Existing snapshots without cost data:** `cost_of_risk` is optional/nullable throughout
- **>10 violating employees:** Compute cost aggregates before truncating the employee detail list (current `[:10]` slice)
- **Zero employees:** Skip HIPAA/credential estimates

## No Schema Migration Required

Cost data embeds inside the existing JSONB `raw_data` field of each dimension in `risk_assessment_snapshots` and `risk_assessment_history`. No new columns or tables needed.

---

## Appendix: Public Dataset Reference

### DOL WHD Compliance Actions (Wage & Hour)

- **Bulk CSV**: `enforcedata.dol.gov/views/data_catalogs.php`
- **REST API**: `developer.dol.gov/wage-and-hour-division/whd-compliance/` (free API key via X-API-KEY header)
- **Data.gov mirror**: `catalog.data.gov/dataset/wage-and-hour-division-compliance-action-data-92329`
- **Coverage**: All concluded WHD compliance actions since FY 2005
- **Key fields**: `naics_code_description`, `bw_atp_amt` (back wages), `ee_atp_cnt` (employees affected), `cmp_assd_cnt` (civil money penalties), violation type flags (FLSA MW, FLSA OT)
- **Use**: Compute median back wages per employee by NAICS code. Replace flat shortfall multipliers with industry-calibrated data.

### OSHA Enforcement Data (Inspections + Violations + Accidents)

- **Bulk CSV**: `enforcedata.dol.gov/views/data_catalogs.php` (updated daily)
- **REST API**: `developer.dol.gov/health-and-safety/dol-osha-enforcement/`
- **Coverage**: ~90,000-100,000 inspections annually, decades of history
- **Key fields (Violations)**: `naics_code`, `viol_type` (S=Serious, W=Willful, R=Repeat), `penalty_initial`, `penalty_current`, `standard` (OSHA standard cited), `nr_exposed`
- **Use**: Compute median/mean penalty by NAICS + violation type. Calculate inspection probability (inspections in NAICS / total establishments from Census Bureau).

### EEOC Enforcement & Litigation Statistics

- **URL**: `eeoc.gov/data/enforcement-and-litigation-statistics-0`
- **Format**: XLSX tables (no API), annual release
- **Coverage**: FY 1997+
- **Key data points**:
  - FY2024: 88,531 charges, $700M recovered, ~17% merit resolution rate
  - 125 EEOC lawsuits filed (0.14% of charges), 97% success rate
  - Basis-specific settlement averages: disability ~$52K, hostile environment ~$53K, retaliation ~$45K, harassment ~$37K
- **EEOC Explore**: `eeoc.gov/data/data-tools-and-products` — interactive EEO-1 data by NAICS, geography, demographics
- **Use**: Replace flat claim probability with actual merit resolution rates. Build basis-specific settlement estimates.

### HHS OCR Breach Portal & HIPAA Enforcement

- **Breach Portal**: `ocrportal.hhs.gov/ocr/breach/breach_report.jsf` — all breaches affecting 500+ individuals since 2009
- **Enforcement Data**: `hhs.gov/hipaa/for-professionals/compliance-enforcement/data/index.html`
- **Resolution Agreements**: `hhs.gov/hipaa/for-professionals/compliance-enforcement/agreements/index.html`
- **Key stats**: 152 cases totaling $144.9M to date
- **2026 penalty tiers**: Tier 1 $145-$36,352, Tier 2 $1,452-$72,703, Tier 3 $14,520-$72,703, Tier 4 $72,703-$2,190,294
- **Use**: Derive enforcement probability from (enforcement actions / total reported breaches). Use actual penalty distribution from resolution agreements.

### NPDB Public Use File (Healthcare Credentials)

- **URL**: `npdb.hrsa.gov/resources/publicData.jsp`
- **Format**: CSV, POR, DAT — quarterly updates (latest through Dec 2025)
- **Analysis Tool**: `npdb.hrsa.gov/analysistool/`
- **Coverage**: All adverse licensure actions and malpractice payments since September 1990
- **Key fields**: Practitioner type (LICNFELD taxonomy), state, adverse action type, basis, malpractice amounts (de-identified)
- **Use**: Compute actual adverse action rates by practitioner type and state, replacing the flat 10% lapse assumption.

### BLS Survey of Occupational Injuries and Illnesses (SOII)

- **URL**: `bls.gov/iif/nonfatal-injuries-and-illnesses-tables.htm`
- **Format**: XLSX tables, annual release
- **Coverage**: Nonfatal injury/illness incidence rates by 4-6 digit NAICS, establishment size, case type
- **Key data**: TRC (Total Recordable Cases), DART (Days Away/Restricted/Transfer), DAFW (Days Away From Work) rates per 100 FTE
- **2024 headline**: TRC rate = 2.3 per 100 FTE (private industry)
- **Use**: When the Workforce dimension adds cost estimates, use actual injury rates by NAICS × OSHA Safety Pays average costs per injury type (`osha.gov/safetypays/estimator`) to compute expected annual injury costs.

### Workers' Compensation Cost Data

- **OSHA Safety Pays**: `osha.gov/safetypays/estimator` — average direct WC claim costs + indirect cost multipliers for 40 injury types (sourced from NCCI)
- **NSC Injury Facts**: `injuryfacts.nsc.org/work/costs/workers-compensation-costs/` — average claim costs by injury type (2022-2023): all claims $47,316, motor vehicle $91,433, burns $64,973, falls/slips $54,499
- **Use**: Combine with BLS SOII injury rates for total expected cost per worker by industry.

### Implementation: NAICS Lookup Table

The industry benchmarks table should be stored as a static JSON file (or a DB table) with this structure:

```json
{
  "7225": {
    "naics_label": "Restaurants and Other Eating Places",
    "whd_median_backwages_per_employee": 1847,
    "whd_median_cmp": 3200,
    "osha_median_penalty_serious": 4500,
    "osha_median_penalty_willful": 82000,
    "osha_inspection_probability": 0.012,
    "eeoc_charges_per_1000_employees": 3.2,
    "eeoc_merit_resolution_rate": 0.17,
    "bls_trc_rate_per_100": 3.1,
    "bls_dart_rate_per_100": 1.8,
    "last_updated": "2026-01-15"
  }
}
```

**Refresh cadence**: Quarterly. DOL APIs support incremental queries by date range. EEOC/BLS publish annually — check in January for prior-year data.

**Fallback**: When a company's NAICS code has insufficient data (< 30 records in the source dataset), use the 2-digit NAICS sector aggregate. If that's also insufficient, use all-industry medians.
