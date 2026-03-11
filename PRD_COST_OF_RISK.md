# Cost of Risk — Risk Assessment Dashboard Feature

## Context

The risk assessment dashboard currently scores companies 0-100 across 5 dimensions, but the scores are abstract. Adding estimated dollar exposure ("cost of risk") makes the risk tangible — a score of 45 means something different when you see it translates to $45K-$127K in potential liability. Categories: wage misclassification back pay, HIPAA fines, lapsed credential penalties, ER litigation defense costs, and OSHA incident penalties.

## Cost Categories by Dimension

### Compliance Dimension (computed from real data + static estimates)

| Category | Source | Formula |
|---|---|---|
| **Hourly wage shortfall** | `employee_violations` where `pay_classification == "hourly"` | `shortfall/hr * 2080hrs * 2-3yr lookback * 2x liquidated damages` |
| **Exempt misclassification** | `employee_violations` where `pay_classification == "exempt"` | `(salary/2080) * 1.5 OT rate * 5-10hrs/wk * 52wks * 2-3yr * 2x damages` |
| **HIPAA breach exposure** *(healthcare only)* | Static estimate from `total_employees` | `employee_count * $100-$1,000` per potential violation |
| **Lapsed credential risk** *(healthcare only)* | Static estimate from `total_employees` | `employee_count * 10% assumed lapse rate * $1K-$10K per lapse` |

### ER Cases Dimension (computed from real data)

| Category | Source | Formula |
|---|---|---|
| **ER litigation exposure** | `pending_determination`, `in_review`, `open` counts | Per-case ranges * 15% claim probability, boosted if policy violation flags |

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

- `low = total_employees * $100` (Tier 1: lack of knowledge, per-violation minimum)
- `high = total_employees * $1,000` (Tier 2: reasonable cause)
- Legal basis: HIPAA penalty tiers range $100-$50,000 per violation. Using conservative Tier 1-2 range.
- Each employee handling PHI represents a potential violation point.

**Example:** 50-employee healthcare company
- Low: 50 × $100 = **$5,000**
- High: 50 × $1,000 = **$50,000**

### 4. Lapsed Credential Risk (Healthcare Only — Static Estimate)

- `at_risk = ceil(total_employees * 0.10)` (10% estimated lapse risk at any time)
- `low = at_risk * $1,000` (state Department of Health minimum fine)
- `high = at_risk * $10,000` (includes Medicare/Medicaid reimbursement repayment exposure)
- If a healthcare employee works on an expired license, the facility faces state DoH fines. More expensively, they may be required to repay all Medicare/Medicaid reimbursements for any patient that unlicensed employee touched during the lapsed period.

**Example:** 50-employee healthcare company
- At risk: ceil(50 × 0.10) = 5 employees
- Low: 5 × $1,000 = **$5,000**
- High: 5 × $10,000 = **$50,000**

### 5. ER Litigation Exposure

Per-case estimated defense cost ranges (based on EEOC/defense attorney data):
- `pending_determination`: $75,000 - $200,000 per case (highest risk — unresolved)
- `in_review`: $50,000 - $150,000 per case (actively managed, somewhat lower)
- `open`: $25,000 - $75,000 per case (acknowledged but less acute)

Apply probability adjustment:
- Base probability: 15% of ER cases escalate to formal claims
- If `major_policy_violation` flag: multiply high estimate by 1.5x
- If `high_discrepancy` flag: multiply high estimate by 1.5x
- The user's benchmark: an employment lawsuit going to court costs $150,000-$200,000 in legal defense fees

**Example:** 2 cases pending determination, 1 in review, major policy violation detected
- Low: (2 × $75K + 1 × $50K) × 0.15 = **$30,000**
- High: (2 × $200K + 1 × $150K) × 0.15 × 1.5 = **$123,750**

### 6. Open Incident Penalties (OSHA Ranges)

Direct penalty ranges by severity (2024 OSHA rates):
- Critical: $15,625 - $156,259 per incident (serious/willful violation range)
- High: $5,000 - $50,000 per incident
- Medium: $1,000 - $15,000 per incident
- Low: $0 (not material enough for cost estimation)

No probability discount — open incidents ARE active exposure.

**Example:** 1 critical, 2 high severity open incidents
- Low: 1 × $15,625 + 2 × $5,000 = **$25,625**
- High: 1 × $156,259 + 2 × $50,000 = **$256,259**

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
│  │  $30K — $124K                 │  │
│  │                               │  │
│  │  Litigation Risk   $30K-$124K │  │
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
│  │  $26K — $256K                 │  │
│  │                               │  │
│  │  OSHA Penalties    $26K-$256K │  │
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
