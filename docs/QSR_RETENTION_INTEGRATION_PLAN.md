# QSR Retention Integration — Reframe for ER/GRC/Agentic Positioning

## Context

`QSR_RETENTION_PLAN.md` (342 lines) sizes retention features against a $450k/yr turnover bleed for a 10-unit, 150-employee smoothie operator. The plan reads like an HRIS roadmap in places — scheduling module, time-punch ingest, shift swap UX, employee-facing schedule portal. User's constraint: **matcha is not HRIS**. Matcha is:

- **Employee Relations (ER)** — case-based workflows (ER Copilot, IR Incidents, pre-termination)
- **GRC** — compliance registry (28+ categories), jurisdiction-aware rules, audit trail
- **Agentic analysis** — Gemini-powered interviews, transcript analysis, risk scoring, anomaly detection

This plan reclassifies the QSR features against that constraint and updates `QSR_RETENTION_PLAN.md` to reflect the correct positioning.

---

## What's already shipped (baseline)

Exploration confirmed these are **live in code** even though the plan doc implies they're TODO:

| Feature | Status | Location |
|---|---|---|
| Wage benchmark (§3.1) | **Live** | `server/app/matcha/services/wage_benchmark_service.py`, `data/oews_qsr_subset.csv`, `data/title_to_soc.json`; UI: `WageGapCard`/`WageGapDrawer` on `/app/employees` |
| Flight-risk composite (§3.3 scoring) | **Live** | `server/app/matcha/services/flight_risk_service.py`, `routes/flight_risk.py`, migration `zzz6a7b8c9d0`; UI: `FlightRiskCard`/`FlightRiskDrawer` on `/app/employees` |
| 6-signal model | **Live** | wage_gap (30), tenure (20), er_case (15), ir_incident (10), cohort (15), manager (10) |
| Cohort w/ manager_id axis | **Live** | `cohort_analysis_service.py` — manager is a supported group-by dimension |
| Pre-termination 9-dim liability | **Live** | `pre_termination_service.py` |
| Anomaly detection (z-score) | **Live** | `anomaly_detection_service.py` |
| ER case workflow | **Live** | `er_copilot.py` + case detail panels (Guidance/Outcome/Policy/Evidence/Similar/Timeline) |
| IR incident workflow | **Live** | `ir_incidents.py` + analytics (OSHA, consistency, anonymous reporting) |
| Conversation analyzer | **Live** | Gemini transcript analysis with interview-type-specific schemas |

**So the QSR plan's §3.1 and most of §3.3 are done. Stay-interview side of §3.3, §4, §5 are the real work.**

---

## The positioning principle

**Matcha is the auditor, analyst, and case-handler. Matcha is not the system of record for shifts, punches, or pay.**

Applied to the QSR plan:

- **KEEP-NATIVELY**: features that reuse ER/IR/case/compliance/agentic infrastructure.
- **REFRAME-AS-AUDIT**: features the plan writes as HRIS modules — rewrite as read-only ingest (CSV upload or upstream API pull) feeding compliance audit reports + flight-risk signals. Matcha never owns the schedule or the punch clock.
- **DEFER-TO-PARTNER**: features that can't exist without becoming HRIS. Document as "requires customer's existing HRIS/scheduler" and stop there.
- **DROP-OR-TRIM**: features that don't move the turnover number and/or bloat scope.

---

## Per-feature classification

| § | Feature | Current plan posture | New posture | Rationale |
|---|---|---|---|---|
| 3.1 | Wage benchmark | Build | **Done** (mostly) | Live. Tier-2 layer in Payscale can wait. |
| 3.2 | Fair Workweek scheduling | HRIS module (publish/edit/swap + right-to-rest + time-punch + employee portal schedule) | **REFRAME-AS-AUDIT** | Ship "Fair Workweek Audit" feature: operator uploads schedule CSV (or we pull read-only from their scheduler). Matcha computes advance-notice violations + predictability pay owed per jurisdiction rule. Outputs audit report → opens ER-style case when systemic. No publishing. No swaps. No employee-facing schedule. |
| 3.3 | Stay interviews + flight risk | Build both | **Flight risk done; stay interviews = new ER-case subtype** | Reuse `er_copilot` case shape. Trigger: flight-risk tier ≥ high in 30–180-day tenure window → auto-create stay-interview case with pre-filled prompts from contributing factors. Agentic angle: optional Gemini-driven stay-interview *conversation* (like screening interviews) for async capture. |
| 4.1 | Pulse surveys / eNPS | Build full engagement module | **KEEP — agentic telemetry, not HRIS** | Survey dispatch + response capture + sentiment analysis via `conversation_analyzer`. Results feed flight-risk score. Frame internally as "retention signals," not "employee engagement suite." Delivery: email + in-app to start (rails that exist); SMS/Slack deferred until outbound rails are built. |
| 4.2 | Manager 1:1 + scorecard | Build | **Scorecard = rollup endpoint + UI. 1:1 cadence = optional tracker** | Cohort already supports manager_id. Add `manager_scorecard.py` route that rolls up: turnover %, avg tenure, ER cases / direct report, flight-risk distribution, avg wage delta. Keep 1:1 cadence minimal — just a `last_one_on_one_at` field per employee and a "days since" decoration. Don't build a full 1:1 tool. |
| 4.3 | Recognition / kudos | Build | **DROP from scope or ride-along trivial** | Doesn't fit ER/GRC/agentic. If shipped, trivial `kudos` table + feed in employee portal. Low priority. |
| 4.4 | Hourly offer letters + state wage notices | Extend | **KEEP — extends existing offer-letter domain** | Not HRIS — offer-letter generation is already in matcha. Add hourly fields + NY WTPA / CA §2810.5 notice templates keyed to `compliance_service` jurisdiction data. |
| 5.1 | Tip pool / tip credit compliance | Build | **KEEP — pure GRC** | Ledger + per-state validator. Fits compliance registry naturally; registry already has the category keys. |
| 5.2 | Break-period audit from time punches | Build | **REFRAME-AS-AUDIT** | Same pattern as §3.2: ingest time-punch CSV → audit missed/short meal & rest breaks against jurisdiction rule → compute premium pay → open ER case on systemic pattern. We don't run the clock. |
| 5.3 | ACA FTE tracking | Build | **KEEP as GRC + reframe ingest** | `aca_fte_service.py` consuming ingested punch data. Compliance output, not HRIS output. |
| 5.4 | Exit interviews | Build | **KEEP — ER case subtype + agentic** | Attach to existing separation case. Structured capture OR (agentic) Gemini-driven voice exit interview reusing screening interview infra. Themes auto-extracted by `conversation_analyzer` → feed pulse-survey question library + flight-risk model. |

---

## Concrete build queue (reprioritized)

Given ~§3.1 and ~§3.3-scoring are done, here's the actual forward work ordered by positioning fit × dollar leverage:

### 1. Stay interviews as ER case subtype (next)
**Fit**: ER (native case workflow) + agentic (optional Gemini conversation).
**Build**:
- `er_case.category` — add `stay_interview` as a new value.
- `stay_interview_service.py` — trigger on flight-risk threshold crossing in 30–180-day window; builds case with pre-filled prompts from top 3 flight-risk factors.
- `routes/stay_interviews.py` — list/detail endpoints OR fold entirely into `er_copilot` if reuse is >80%.
- UI: new filter on ER Copilot case list; new case-creation path from Flight Risk Drawer.
- **Agentic option (Tier 2 polish)**: reuse screening-interview voice infra — employee receives a link, Gemini conducts a 5-min stay interview, transcript + sentiment feeds case + flight-risk.

### 2. Manager scorecard endpoint + UI
**Fit**: GRC rollup (cohort already does the math).
**Build**:
- `routes/manager_scorecard.py` — thin wrapper over `cohort_analysis_service` with manager_id axis.
- Surface in ER Copilot (case detail shows respondent's manager's scorecard) + Dashboard (manager heatmap — `flight_risk` already has `manager_hotspots`).

### 3. Pulse surveys (engagement telemetry, not HRIS)
**Fit**: agentic (sentiment analysis) + feeds flight-risk.
**Build**:
- Schema: `pulse_surveys`, `pulse_responses`, `engagement_scores`.
- `engagement_service.py` + `routes/engagement.py`.
- Question library (industry-specific QSR defaults).
- Delivery rails: email + in-app only to start. SMS/Slack deferred (needs outbound rails built).
- `conversation_analyzer` extension: free-text response sentiment.
- Wire sentiment trend → flight-risk score as the 7th signal (planned `pulse_sentiment` factor, weight to come out of currently-overweighted wage_gap).
- Feature flag: add `engagement` to `feature_flags.py` + admin UI. Hide until backend ships (per plan §8 — "stop selling vapor").

### 4. Hourly offer letters + state wage notices (§4.4)
**Fit**: extends existing offer letter module.
**Build**:
- Offer-letter schema: add `hourly_rate`, `regular_rate`, `overtime_rate`, `shift_pattern`, `tip_policy`, `meal_period_policy`, `benefits_eligibility_date`.
- PDF templates for hourly offer + NY WTPA + CA §2810.5 wage notices.
- Auto-fill offer rate from wage benchmark so it lands at-or-above market.

### 5. Fair Workweek AUDIT (reframed §3.2)
**Fit**: GRC audit + agentic analysis.
**Build**:
- Ingest surface: `routes/schedule_ingest.py` — CSV upload + stub ADP/Homebase/7shifts read-only API fetch.
- `fair_workweek_audit_service.py` — reads ingested shifts, looks up jurisdiction rule via `compliance_service`, computes advance-notice violations + predictability-pay owed + right-to-rest (clopening) warnings.
- Output: audit report (downloadable), summary on `/app/compliance`, auto-create ER case on systemic pattern.
- Explicitly NOT: schedule editor, shift swap UI, employee-facing schedule.
- Feature flag: `fair_workweek_audit`.

### 6. Exit interviews (§5.4)
**Fit**: ER case subtype + agentic.
**Build**:
- Attach structured form to existing `separation` case flow.
- Optional Gemini-driven voice exit interview (same infra as screening).
- Theme extraction feeds pulse question library + flight-risk retraining.

### 7. Tip pool compliance (§5.1)
**Fit**: GRC.
**Build**:
- Tip ledger schema (per pay period, pool, distribution rule, per-employee allocation).
- Per-state validator (tip credit legality, dual-jobs rule).
- Compliance page surface.

### 8. Break audit from ingested punches (§5.2)
Rides on #5 ingest. Same audit pattern.

### 9. ACA FTE (§5.3)
Rides on #5 ingest.

### 10. Recognition (§4.3)
**Optional**. Ride-along trivial, or drop. Does not move turnover enough to justify ahead of anything above.

---

## Shared infrastructure gaps to plan around

Found during exploration — these block multiple items above:

1. **No location table.** Company has `headquarters_state`/`headquarters_city`; employee has `work_state`. Multi-location QSR operator use-case needs a real location entity. Proposed: `locations` table (`id`, `company_id`, `name`, `address`, `state`, `city`, `zip`, `manager_id`), FK from employees. Blocks: manager scorecard per-location, schedule ingest per-location, jurisdiction rule resolution per-location.

2. **No outbound SMS / Slack messaging rails.** `notification_service` is email + in-app only. `twilio_webhook` is inbound voice only. `slack_service` is onboarding-only. For QSR (baristas won't check email), this is a real blocker for pulse surveys and stay-interview invites. Propose: outbound SMS via Twilio as the first expansion, Slack messaging second. Defer until #1–#4 ship.

3. **No schedule / shift / punch tables.** Zero — confirmed by grep. Anything ingest-based needs these (even as pure audit, we need a table to land the CSV into). Propose: `ingested_shifts`, `ingested_punches`, `schedule_audit_events` — named to signal "audit ingest," not "system of record."

---

## Proposed edits to `QSR_RETENTION_PLAN.md`

The doc is mostly right but needs to reflect the positioning. Suggested changes:

1. **Add §0 "Positioning"** (above §1): 2 paragraphs stating matcha is ER/GRC/agentic, not HRIS, and that this constrains how §3.2 / §5.2 / §5.3 are built.

2. **§3.2 rewrite**: change "new scheduling_service.py with schedule publish/edit/swap primitives" → "new fair_workweek_audit_service.py ingesting schedule data (CSV or read-only API from customer's scheduler) and producing advance-notice / predictability-pay / right-to-rest audit reports. Matcha does not publish, edit, or swap schedules." Remove the `employee_portal.py` schedule/swap surface. Remove shift-swap-as-retention-UX claim.

3. **§3.1 mark as "Shipped"** at the top of the section.

4. **§3.3 split**: "Flight risk scoring — Shipped. Stay interviews — Next."

5. **§4.1 reframe**: retitle "Pulse surveys" → "Engagement telemetry (retention signals)." Remove eNPS as user-facing framing; it's an *input* to flight risk, not a dashboard metric for managers.

6. **§4.3 deprioritize or drop**: move to "optional / ride-along" at the bottom.

7. **Add §5.5 "Shared infrastructure"**: document the location table, outbound rails, ingest tables explicitly.

8. **§6 sequencing rewrite**: remove the "Time-punch ingest" as #1 (it's not the foundation for near-term work) and replace with:
   1. Stay-interview ER case subtype
   2. Manager scorecard (rollup only)
   3. Pulse survey MVP (email + in-app)
   4. Locations table
   5. Hourly offer letters + state wage notices
   6. Fair Workweek audit ingest (unlocks 7, 8)
   7. Break audit
   8. ACA FTE
   9. Exit interviews
   10. Tip pool compliance
   11. (optional) Recognition

9. **§8 out-of-scope**: explicitly add "schedule editor / shift swap / time clock UI — customer's existing HRIS owns these; matcha audits them."

---

## Verification

Plan is soft — no code written yet. Once each §N ships:

- **Stay interviews**: seeded 720 Behavioral flight-risk `high`/`critical` employees auto-create stay-interview cases; cases show pre-filled prompts derived from the top 3 contributing factors.
- **Manager scorecard**: pick a manager with ≥5 direct reports in the seed data; scorecard endpoint returns turnover %, avg tenure, ER case count, flight-risk distribution, avg wage delta; UI renders them.
- **Pulse surveys**: send 3-question survey to seed employees, capture responses, sentiment analyzer runs, per-employee sentiment trend appears as 7th factor in flight-risk recomputation.
- **Hourly offer letters**: generate a CA offer at below-market, confirm §2810.5 notice auto-attaches and wage benchmark warns "offer is below p50 by X%."
- **Fair Workweek audit**: upload CSV with 3 shifts changed inside SF's 14-day window; audit report flags all 3 with predictability-pay owed.

---

## Critical files referenced

- `server/app/matcha/services/flight_risk_service.py` — extend with 7th signal (pulse sentiment) later
- `server/app/matcha/services/wage_benchmark_service.py` — reuse for hourly offer letter auto-fill
- `server/app/matcha/services/cohort_analysis_service.py` — manager_id axis already exists; wrap for scorecard
- `server/app/matcha/routes/er_copilot.py` + `models/er_case.py` — add `stay_interview` / `exit_interview` case categories
- `server/app/matcha/services/conversation_analyzer.py` — extend with pulse-survey sentiment schema
- `server/app/matcha/services/compliance_service.py` — Fair Workweek jurisdiction rules lookup (registry keys exist; implementation is the gap)
- `server/app/core/feature_flags.py` — add `engagement`, `stay_interviews`, `manager_scorecard`, `fair_workweek_audit`, `tip_pool`
- `client/src/pages/app/Employees.tsx` — existing landing zone for FlightRisk + WageGap cards; add ManagerScorecard card
- `client/src/pages/app/ERCopilot.tsx` — add stay-interview / exit-interview filters
- `QSR_RETENTION_PLAN.md` — the doc itself gets the edits listed above
