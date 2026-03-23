# Risk Assessment System Improvements

## Context
The risk assessment system computes a 5-dimension risk score (compliance, incidents, ER cases, workforce, legislative) for companies, with Monte Carlo simulation, cohort analysis, benchmarks, and anomaly detection. The current UI is utilitarian — it needs better visual hierarchy. Scoring has rough edges and there are missing features.

## Phase 1: UI/UX Redesign (Priority)

### Score Card & Dimensions
- **Animated score gauge** — replace the flat number with an arc/ring gauge that animates on load
- **Dimension sparklines** — tiny inline trend lines next to each dimension score showing 4-week direction
- **Color-coded dimension icons** — distinct icons per dimension (shield for compliance, alert-triangle for incidents, users for ER, etc.)
- **Score delta indicators** — show +/- change from last assessment with arrow indicators

### Page Layout
- **Sticky header** with score summary that collapses as you scroll
- **Better tab design** — pill style instead of current boxy tabs
- **Card hover states** — subtle lift/glow on dimension cards
- **Loading skeleton** — replace text spinner with skeleton cards

### Files:
- `client/src/pages/app/RiskAssessment.tsx`
- `client/src/components/risk-assessment/RiskScoreCard.tsx`
- `client/src/components/risk-assessment/RiskDimensionsGrid.tsx`

## Phase 2: Scoring Accuracy

### Compliance Dimension (currently 30%)
- **Jurisdiction requirement gap scoring** — score for missing/incomplete requirements in `compliance_requirements` table
- **Weight by employee count per location** — a violation at a 500-person location matters more than a 5-person one

### Workforce Dimension (currently 15%)
- **Onboarding completion rate** — incomplete onboarding tasks are a compliance gap
- **Headcount concentration risk** — over-reliance on single locations or departments

### Legislative Dimension (currently 5%)
- **Increase weight to 10%** for healthcare clients where regulatory changes are high-impact
- **Compliance requirement staleness** — if jurisdiction data hasn't been refreshed, that's a risk signal

### Files:
- `server/app/matcha/services/risk_assessment_service.py` (dimension compute functions)

## Phase 3: New Features

### PDF Export
- "Export PDF" button generating a branded risk report
- Score summary, dimension breakdown, recommendations, cost of risk

### Email Digest
- Weekly/monthly risk summary email to admins
- Score trend, new action items, dimension changes
- Wire through Gmail `send_email()` method

### Real-time Alerts
- Threshold-based alerts when a dimension crosses into a higher band
- Email notification when score increases by >10 points

### Files:
- New: `server/app/matcha/services/risk_report_service.py`
- New: `server/app/matcha/routes/risk_report.py`
- `server/app/core/services/email.py` (add risk digest email method)

## Phase 4: Performance

### Backend
- **Parallelize dimension computation** — verify `asyncio.gather()` is used for all 5 dimensions
- **Cache benchmark data** — NAICS benchmarks don't change often, cache for 24hrs
- **Batch wage violation queries** — replace per-location loop in `_collect_minimum_wage_violation_metrics` with bulk query

### Frontend
- **Lazy load Analytics tab** — Monte Carlo, cohort, benchmarks, anomalies only fetch when tab is clicked
- **Memoize dimension components** — prevent re-renders when switching tabs

### Files:
- `server/app/matcha/services/risk_assessment_service.py`
- `server/app/matcha/services/benchmark_service.py`
- `client/src/pages/app/RiskAssessment.tsx`

## Execution Order
1. **Phase 1** (UI/UX) — highest visible impact, self-contained
2. **Phase 4** (Performance) — quick wins, improves experience
3. **Phase 2** (Scoring) — backend-only, can iterate
4. **Phase 3** (Features) — new functionality, most scope
