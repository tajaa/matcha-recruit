# Agentic upgrades — make the new broker/compliance features derive, not type

_Plan, 2026-06-21. Branch `matcha/compliance-tracker`._

Feedback: the new features (workforce-compliance registers, WC class-codes, pay-equity,
resident-care) lean on **manual entry**, unlike the rest of the platform which derives from
existing data + agentic Gemini (onboarding wizard, compliance research). Add the auto/agentic
path to each; **manual entry stays as fallback + edit**. Reuse: cached `IRAnalyzer` one-shot
Gemini (best-effort, never-raises — as in `submission_packet`/`loss_run_parser`), the existing
`employees` data (job_title, department, pay_rate, pay_classification), incidents, locations,
industry. No new integration required (HRIS demographics noted where missing).

## 1. WC class-code auto-map (deterministic + AI)
Employees → NCCI class. `services/wc_classmap.py`: pull distinct `job_title`/`department` +
headcount + annualized `pay_rate` sum per group; Gemini maps each distinct title → a
`wc_class_codes.class_code` (best-effort; unmapped → flagged for review). Aggregate into
proposed `company_wc_class_exposures` rows (class_code, state from HQ, payroll, headcount).
- Endpoint `POST /broker/wc-portfolio/{id}/class-exposures/auto` → returns proposed rows (no
  auto-commit); broker confirms → existing create path persists. Broker WC tab: "Auto-map from
  employees" button → review table → Save all.

## 2. Pay-equity = real analysis from comp data (deterministic)
Instead of logging a study date, **compute** from `employees.pay_rate` grouped by `job_title`
(within-role pay dispersion: spread, coefficient of variation, outliers >X% from role median).
That's a legitimate pay-equity screen using data we hold. `services/pay_equity_analysis.py`.
- Endpoint `POST /workforce-compliance/pay-equity/analyze` → computes + writes a
  `pay_equity_reviews` row (scope="auto: pay dispersion by role", gap_pct = max role CoV/spread,
  remediation auto-noted) → flips the EPL factor on real data. Page: "Run analysis from payroll"
  button.
- **Honest gap:** protected-class (gender/race) pay-gap needs demographics not in our schema →
  note "protected-class analysis requires HRIS demographics (Finch /individual) — not yet synced."

## 3. AI scan & suggest for the registers (Gemini one-shot)
`services/workforce_suggest.py` + `resident_care` suggest. Gemini reads company context
(industry, headcount, job_titles sample, locations, recent incident categories, existing
integrations) → proposes starter rows:
- AI-hiring-tool register (likely ATS/assessment tools for the industry/size),
- biometric points (time clocks for hourly workforces, access control),
- safety programs (fall-prevention/infection-control/… by industry + incident history).
- Endpoints `POST /workforce-compliance/ai-audits/suggest`, `/biometric-points/suggest`,
  `POST /resident-care/programs/suggest` → return suggestions (no auto-commit) → FE "AI suggest"
  button → review checkboxes → confirm → bulk create. One-shot, best-effort.

## 4. Risk-profile AI narrative + action plan (Gemini one-shot)
`risk_index` + Gemini → a plain-English "here's why your index is X and the top moves to improve
your terms" with prioritized actions. Endpoint `POST /risk-profile/narrative` (client) +
`/broker/risk-index/{id}/narrative` (broker). Surface on the portal + broker view. Best-effort.

## Cross-cutting
- All Gemini calls: cached `IRAnalyzer`, `asyncio.wait_for` timeout, `_parse_json_response`,
  never raise (return empty/fallback). No auto-commit — user always confirms suggestions.
- Manual register/forms remain. Add an "auto" affordance next to each.
- Pure-logic unit tests for the deterministic parts (class aggregation, pay-dispersion math).
- Dev smokes against the seeded book. Commit per feature. No migrations (all reuse existing tables).

## Sequence (data-derived first, then Gemini)
1. WC class-code auto-map (deterministic core + AI title map).
2. Pay-equity dispersion analysis (deterministic).
3. AI scan & suggest (Gemini) for the 3 registers.
4. Risk-profile AI narrative.
