# Broker A/B completion — close the remaining WTW-gap items

_Plan, 2026-06-20. Branch `matcha/compliance-tracker`._

Closing the still-open items under the report's macro needs **A (strategic/platform, pp.4–13)** and **B (HR-adjacent underwriting lines)**. Already shipped: data-driven broking, AI coverage-gap, submission packet, full WC depth + 50-state rates, EPL score + pay-transparency/BIPA/AI-hiring tools (workforce_compliance). C (cyber/fiduciary/P&C) stays out-of-scope. Pay-equity/DEI deferred (need payroll/demographics).

Building **3** chosen areas:

---

## Feature 1 — Composite risk index + client-facing risk portal (A)

The report's "Risk Intelligence Central" (p.10) + "Risk Index Model" (p.29). **No new data** — roll up the three engines already computed.

- **`services/risk_index.py`** — `compute_risk_index(conn, company_id)` → one 0–100 (higher = lower risk, matches EPL convention) + band (strong≥80 / adequate≥60 / developing≥35 / exposed<35), from 3 weighted components:
  - **WC** (wt 40) — from `compute_wc_metrics` severity_band → score; EMR>1.0 penalty.
  - **EPL** (wt 35) — `compute_epl_readiness` score directly.
  - **Compliance** (wt 25) — share of `compliance_requirements` compliant across the company's locations.
  - Components with no data drop out; weights renormalize. Returns `{index, band, components:[{key,label,score,weight,detail}], top_fixes:[...]}`.
- **Broker side** — `GET /broker-portfolio/risk-index` (band distribution rollup) + `GET /broker-portfolio/{id}/risk-index`; surfaced on `BrokerDashboard` strip + a header chip on `BrokerClientDetail`.
- **Client portal** — new flag **`risk_profile`** (default off, admin-toggle). `GET /risk-profile` (self; `require_admin_or_client` + `get_client_company_id`) returns the index + the 3 component breakdowns + top fixes. New page `pages/app/RiskProfile.tsx` at `/app/risk-profile`, `<FeatureGate feature="risk_profile">`, `ClientSidebar` Compliance group. "Your insurability at a glance + how to improve terms."
- **No migration** (flag is code). Pure scoring → unit-testable.

## Feature 2 — WC class-code dimension (B/WC)

Per-NCCI-class breakdown (report p.32–33 "class-level underwriting discipline"). Licensed NCCI class rates unavailable → ship schema + broker manual entry + a small illustrative seed.

- **Migration `wcclass01`** (off `wfcomp01`):
  - `wc_class_codes` — reference: `state, class_code, description, base_rate, source` (UNIQUE state+class_code). Seed a handful, `source='seed (demo)'`.
  - `company_wc_class_exposures` — `company_id, class_code, state, payroll, headcount, note` (broker-entered per client).
- **Backend** — extend `wc_depth.py` + `broker_portfolio.py`: `GET /broker-portfolio/wc-class-codes`, `GET|POST|DELETE /broker-portfolio/{id}/class-exposures`. Broker-role gated, `_assert_broker_owns_company`.
- **Frontend** — class-exposure table + add/delete on the WC tab of `BrokerClientDetail`.

## Feature 3 — Healthcare resident-care risk asset (B/Healthcare)

Package the insurer-facing "resident-care risk management program" (p.175) + MVR reviews (p.176) + fall-prevention. New flag **`resident_care`** (default off, admin-toggle; healthcare vertical).

- **Migration `rescare01`** (off `wcclass01`):
  - `mvr_reviews` — `company_id, driver_name, employee_id?, review_type (hire|annual), review_date, status (clear|flagged|pending), next_due_date, notes`.
  - `safety_programs` — `company_id, program_type (fall_prevention|infection_control|abuse_prevention|emergency_prep|other), name, status (active|inactive), last_reviewed_date, owner, notes`.
- **Backend** — `routes/resident_care.py` (`/resident-care`, `require_feature("resident_care")`) — CRUD for both + `GET /summary` (program coverage, MVR currency/overdue, credentialing currency from `credential_templates`, incident posture from `ir`). Asset PDF generator `services/resident_care.py` (reuse WeasyPrint deterministic pattern) → `GET /resident-care/asset.pdf`.
- **Frontend** — `pages/app/ResidentCare.tsx` (`/app/resident-care`): safety-programs register, MVR register, credentialing currency readout, "Generate insurer asset" download. `<FeatureGate feature="resident_care">` + `ClientSidebar` (Safety group).

---

## Cross-cutting (each feature)
- `feature_flags.py` `DEFAULT_COMPANY_FEATURES` + admin `KNOWN_FEATURES` (admin.py) + admin `FEATURE_LABELS` (Features.tsx) for `risk_profile`, `resident_care` (the reachability lesson).
- `CLAUDE.md` flag-table rows; `adminUpdates.ts` entry.
- Pure-logic unit tests where applicable (risk_index scoring; resident_care summary math).
- Migrations applied to **dev** only; prod pending `migrate-prod.sh`.
- Verify: `py_compile` + `tsc --noEmit` + `pytest` + dev smoke. Commit per feature.

## Sequence
1. Feature 1 (no migration, highest leverage, composes existing) → commit.
2. Feature 2 (migration wcclass01) → commit.
3. Feature 3 (migration rescare01, biggest) → commit.
4. Refresh `broker-capabilities-and-wtw-gap-2026.md` + brief HTML coverage snapshot.
