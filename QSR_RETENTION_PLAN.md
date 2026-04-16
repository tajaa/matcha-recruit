# QSR / Coffee & Smoothie Retention Plan

A roadmap for turning matcha-recruit into a P&L-grade retention tool for high-turnover service operators.

---

## 1. The pain we're addressing

Coffee, smoothie, and similar fast-format QSR concepts sit in the worst slice of the worst industry for labor economics. The numbers an operator faces:

| Stat | Source |
|---|---|
| Average restaurant employee turnover topped **75%** in 2025; fast food **can exceed 130%** | Homebase |
| Some operators report **150–400%** turnover; Panera's CFO pegged industry at **130%** — effectively a full workforce refresh every year | COMPT |
| Cost to replace one hourly coffee employee averages **~$6,000** | Toast POS |
| Fully-loaded replacement cost: **~$5,864** per person (includes ~$821 training) | Restroworks |
| **70%** of restaurant employees would quit over low compensation | Menu Tiger |

Worked example, the kind a multi-unit operator runs in their head:

> 10 stores × ~15 staff = **150 employees**.  
> 100% annual turnover × $3,000 conservative replacement = **~$450,000/year in pure churn cost**, before counting revenue lost to undertrained baristas, slow drive-thrus, broken POS reconciliation, customer churn from inconsistent service, and the manager hours soaked up onboarding the same role for the fifth time.

If matcha can credibly cut that 100% turnover number to 65%, that's **~$160k/year of recovered margin per 10 stores** — and far more once you factor revenue impact. That number is what this plan is sized against.

---

## 2. Why the platform doesn't move that number today

matcha-recruit's current posture is **strong on compliance plumbing and post-hoc risk** and **weak on proactive retention levers**. That asymmetry is the strategic problem: when an operator's #1 dollar bleed is turnover, a system that documents the firing well doesn't move the bleed.

Inventory of what *is* built (so we don't reinvent it):     

| Capability | Lives in | Posture |
|---|---|---|
| AI candidate screening (voice, Gemini Live) | `interviews.py`, `conversation_analyzer.py` | Hire-quality |
| Resume batch + AI matching | `matcha_work.py` (resume_batch state) | Hire-quality |
| Salaried offer letters + negotiation | `offer_letters.py` | White-collar oriented |
| Onboarding orchestration + state machine | `onboarding_orchestrator.py`, `onboarding_state_machine.py` | Compliance |
| Training requirements + completion tracking | `training.py` | Compliance |
| FMLA / state-leave eligibility + notices | `leave_eligibility_service.py`, `leave_notices_service.py` | Compliance |
| ADA accommodation cases | `accommodation_service.py` | Compliance |
| ADEA-aware separation agreements | `separation.py` | Defensive legal |
| COBRA, I-9 / E-Verify | `cobra.py`, `i9.py` | Compliance |
| ER copilot + IR incidents | `er_copilot.py`, `ir_incidents.py` + `er_*.py` / `ir_*.py` | Defensive legal |
| Pre-termination 9-dimension liability check | `pre_termination_service.py` | Defensive legal |
| Anomaly detection on monthly turnover (z-score) | `anomaly_detection_service.py` | Reactive |
| Cohort analysis by hire quarter / location / dept | `cohort_analysis_service.py` | Reactive |
| Risk assessment + NAICS peer benchmarks | `risk_assessment_service.py`, `benchmark_service.py` | Reactive |
| Compliance registry (28+ categories) | `core/services/compliance_service.py` | Reactive |

Notice the right column. Almost every line is "compliance" or "defensive" or "reactive." A coffee chain at 100% turnover does not pay $450k/year because their I-9s are messy. They pay it because of:

1. **Comp** — 70% of QSR employees would walk for a better wage offer.
2. **Schedule chaos** — last-minute shift changes destroy childcare, school, second jobs.
3. **Manager quality** — people quit managers, not companies.
4. **Zero growth path** — barista today, barista in two years.
5. **No early signal** — by the time HR notices the spike, the cohort is already gone.

The plan below maps the platform's gaps to those five drivers and orders them by dollar leverage.

---

## 3. The Tier 1 plan (direct turnover-cost killers)

Three features. Together they reframe matcha from "compliance binder" to "retention P&L tool" — which is the actual pitch a multi-unit coffee operator buys.

### 3.1 Hourly wage benchmarking + below-market alerts

**Addresses**: "70% of restaurant employees would quit over low compensation."

**What's missing today**:
- `benchmark_service.py` benchmarks ER case rates and OSHA incident rates against NAICS peers — not pay.
- The offer-letter recommendation engine has hardcoded *salaried* role bands (`software_engineering: $130k-$205k`, etc.) and skips hourly roles entirely.
- An operator has no way to know their Denver baristas are $1.50/hr below local market — a delta that, against a $6,000 replacement cost and 75–130% turnover, is one of the most asymmetric financial bets in the building.

**What ships**:
- New `wage_benchmark_service.py` ingesting BLS Occupational Employment and Wage Statistics (OEWS) keyed on SOC code (35-3023 fast-food cooks, 35-3041 food prep workers, 35-3031 waiters, 41-2011 cashiers, 35-1011 chefs, 35-1012 supervisors of food prep) at the metro/zip level.
- Per-employee delta computation: `(employee.hourly_rate − market_p50_for_role_metro) / market_p50`.
- Dashboard widget on the operator dashboard (`dashboard.py`): "X of Y hourly employees below market by ≥10%; closing the gap = $Z/hr in raises versus $W/yr in expected churn cost." That math is the entire pitch.
- Per-employee record decoration so a manager opening a profile sees the delta inline.
- Trigger condition for stay-interview flow (Tier 1 #3 below) when delta < −10% AND tenure between 30 and 180 days (the sweet spot where comp dissatisfaction becomes a quit).

**Why this is #1**: it directly addresses the most-cited cause of QSR quits and it monetizes itself in the UI. Every other Tier 1 item compounds on it (flight-risk score uses below-market as a feature; stay interviews open with a comp data point).

**Cost-of-replacement framing as the UX hook**: every below-market alert should display the avoided-replacement-cost math. "Sasha is $1.20/hr below market. A raise = $2,496/yr. Expected replacement cost if Sasha leaves at the segment's 100% rate = $5,864. Net retention bet: $3,368 per year saved."

**Files to touch**:
- New: `server/app/matcha/services/wage_benchmark_service.py`
- New: `server/app/matcha/routes/wage_benchmark.py`
- Extend: `server/app/matcha/routes/dashboard.py` (operator widget)
- Extend: `server/app/matcha/routes/employees.py` (per-employee delta)
- Extend: `server/app/matcha/routes/offer_letters.py` (use benchmark when generating hourly offers — see §3.4 / Tier 2)

**Data source**: BLS OEWS quarterly download (free, ~50MB). Refresh quarterly via Celery task. Optional Tier 2: layer Payscale or local-data partners for tighter zip-level signal.

---

### 3.2 Predictable scheduling & Fair Workweek compliance

**Addresses**: schedule chaos as a top-2 turnover cause AND class-action liability in CA/OR/NYC/Chicago/Philly/LA/SF/Seattle/Emeryville/etc.

**What's missing today**:
- The compliance registry has the category — "Scheduling & Reporting Time" — with regulation keys including `predictive_scheduling`, `split_shift_premium`, `on_call_pay`, `spread_of_hours`, `reporting_time_pay`. **Zero implementation.** It's a row in a database, not a feature.
- No scheduling module. No advance-notice ledger. No predictability-pay calculator. No shift swap. No right-to-rest enforcement.

**What ships**:
- New `scheduling_service.py` with schedule publish/edit/swap primitives, time-stamped so advance-notice can be computed against the jurisdiction rule.
- Hook into `compliance_service.py` to look up the live rule per location: SF requires 14 days, NYC fast food requires 14 days plus consent for changes inside 14, Chicago 10 days (rising to 14 in 2024), Oregon 14 days, etc. Auto-compute predictability-pay owed on each violation.
- Right-to-rest (clopening) flag: detect any closing shift followed by an opening shift inside the rule's minimum gap (often 11 hours), surface as warning.
- Schedule-swap surface in `employee_portal.py` so employees can self-resolve conflicts without manager bottlenecks (which is itself a turnover driver — "I quit because I couldn't get my schedule changed").
- Time-punch ingest in `hris_sync_orchestrator.py` so we can validate published schedule vs. actual hours for predictability-pay reconciliation.

**Why this matters dollarwise**:
- A single SF Fair Workweek class action against a small chain has run >$500k in settlements + back pay. Building this *also* builds the audit-defense story for the segment.
- Operationally, predictable schedules are correlated with measurable turnover drops in the academic literature (e.g., the Kronos/Williams Predictable Scheduling field study showed ~30% turnover reduction for the treatment group).

**Files to touch**:
- New: `server/app/matcha/services/scheduling_service.py`
- New: `server/app/matcha/routes/scheduling.py`
- New: schema migration for `schedules`, `shifts`, `shift_changes`, `predictability_pay_events`
- Extend: `server/app/matcha/services/compliance_service.py` (resolve jurisdiction rule per location)
- Extend: `server/app/matcha/services/hris_sync_orchestrator.py` (time-punch ingest)
- Extend: `server/app/matcha/routes/employee_portal.py` (employee-facing schedule + swap)

**Sequencing**: time-punch ingest is shared infrastructure with §3.6 (break-period audit) and §3.7 (ACA FTE). Build it once, three Tier 1/3 features come online.

---

### 3.3 Stay interviews + flight-risk scoring

**Addresses**: "by month 3, 30–40% of new hires in a 100% turnover environment are already gone" — and matcha currently has zero forward-looking signal.

**What's missing today**:
- `pre_termination_service.py` runs a 9-dimension liability score *after a manager has decided to fire*. It is the inverse of what's needed.
- `cohort_analysis_service.py` is post-hoc — it tells you Q2 was a bad cohort, not which specific Q3 employee is about to leave.
- `anomaly_detection_service.py` flags monthly turnover spikes after they've happened.
- No stay interview workflow. No flight-risk score per employee. No automatic intervention trigger.

**What ships**:
- New `flight_risk_service.py` consuming signals already (or soon-to-be) collected:
  - Wage delta vs. market (from §3.1)
  - Tenure × role-typical-quit-curve
  - Schedule volatility (from §3.2)
  - Missed-shift count, late-arrival pattern (from time-punch ingest)
  - ER case involvement
  - Manager identity (rolled up — see §3.5)
  - Pulse-survey sentiment trend (from §3.4)
  - Ratio of hours worked vs. requested
  - Days since last 1:1 (from §3.5)
- Per-employee score 0–100 with the contributing-factor breakdown attached so a manager can act on it (not just see "67% — leaving soon ¯\\_(ツ)_/¯").
- Stay-interview workflow modeled on `er_copilot.py` case structure but proactive: when score crosses a threshold for an employee in their 30–180-day window, auto-create a stay-interview case for the manager with question prompts pre-filled with the risk signals (e.g., "Sasha is $1.20/hr below market and worked 18 vs. 30 requested hours last month — open with comp and scheduling").
- Reminder via `notification_service.py` if the case is open >7 days without manager action.

**Why this matters dollarwise**:
- Stay interviews are the highest-ROI retention intervention in the literature — a $50 manager-time investment to surface a $5,864 leak. Even at modest accuracy (e.g., the score correctly flags 30% of would-quit employees and intervention saves half), the math on a 10-store / 150-employee chain is roughly $200k+/yr in retained-employee replacement cost avoided.

**Files to touch**:
- New: `server/app/matcha/services/flight_risk_service.py`
- New: `server/app/matcha/services/stay_interview_service.py`
- New: `server/app/matcha/routes/stay_interviews.py`
- Extend: `server/app/matcha/services/pre_termination_service.py` (share scoring infrastructure — invert the model)
- Extend: `server/app/matcha/services/cohort_analysis_service.py` (per-employee risk vs. its hire cohort baseline)
- Extend: `server/app/matcha/services/notification_service.py` (manager nudges)

---

## 4. Tier 2 — retention infrastructure that makes Tier 1 credible

These are the day-to-day operations features. Tier 1 is the headline pitch; Tier 2 is what an operator actually uses every week.

### 4.1 Pulse surveys / vibe checks / eNPS — actually built this time

`vibe_checks` and `enps` are listed as feature flags in CLAUDE.md but **the backend doesn't ship the feature**. There is no engagement data model, no survey tables, no question library, no scoring. Marketing claims a feature the backend doesn't have. Dangerous.

**What ships**:
- New `engagement_service.py` + `routes/engagement.py`.
- Schema: `pulse_surveys` (definition), `pulse_responses` (one row per employee per cycle), `engagement_scores` (computed trend per employee + per location).
- Question library with industry-specific defaults (QSR: "How is your schedule fitting your life this week?", "Did you feel respected by customers this week?", "Did your manager check in with you?", classic eNPS "How likely are you to recommend working here?").
- Delivery rails: SMS via existing `twilio_webhook.py` for off-shift baristas (most won't have Slack/email), Slack via `slack_service.py` for back-office, in-app via `employee_portal.py`.
- Trend + sentiment via existing `conversation_analyzer.py` (or a thinner version) — feeds the flight-risk score.
- Manager-facing rollup: which questions are dropping at which location.

**Files**:
- New: `server/app/matcha/services/engagement_service.py`
- New: `server/app/matcha/routes/engagement.py`
- New: schema migration
- Extend: `server/app/matcha/routes/twilio_webhook.py` (outbound SMS path)
- Extend: `server/app/matcha/services/slack_service.py`
- Extend: `server/app/matcha/routes/employee_portal.py`

### 4.2 Manager 1:1 cadence + manager retention scorecard

People quit managers, not companies. Manager ID is already on every employee and incident record — we just don't roll up.

**What ships**:
- Extend `cohort_analysis_service.py` to support `manager_id` as a group-by attribute. Surfaces "Manager A's stores have 180% turnover, Manager B's have 60%" — a fuzzy problem becomes accountable.
- 1:1 cadence object: scheduled 1:1s per direct report, completion tracking, missed-1:1 alerts, optional template (questions, action items).
- "Last 1:1" decoration on every employee record. Feeds flight-risk: an employee with no 1:1 in 60 days is a risk signal.
- Manager scorecard report: turnover %, average tenure, ER cases per direct report, 1:1 cadence, pulse-survey delta.

**Files**:
- Extend: `server/app/matcha/services/cohort_analysis_service.py` (manager_id rollup)
- New: `server/app/matcha/services/one_on_one_service.py`
- New: `server/app/matcha/routes/manager_scorecard.py`
- Extend: `server/app/matcha/routes/employee_portal.py` (1:1 surface for both sides)

### 4.3 Recognition / peer kudos

Cheap, high-emotional-value. Coffee crews are small, public-facing, high-social-density teams — recognition lands hard there.

**What ships**:
- Lightweight kudos object: sender, recipient, message, optional value-tag (e.g., "hospitality," "team support," "drive-thru speed").
- Feed in `employee_portal.py` (employee sees their own + recent across location).
- Slack delivery (cross-post to a #kudos channel if the company uses Slack).
- Roll into the manager scorecard (managers whose teams *give* kudos generally have lower turnover).
- Roll into stay interview prompts ("Sasha got 4 kudos this month for hospitality — open by acknowledging that").

**Files**:
- New: `server/app/matcha/services/recognition_service.py`
- New: `server/app/matcha/routes/recognition.py`
- Extend: `server/app/matcha/routes/employee_portal.py`
- Extend: `server/app/matcha/services/slack_service.py`

### 4.4 Hourly offer letters + state wage notices

Today the offer-letter engine assumes salaried. NY Wage Theft Prevention Act notice and CA Labor Code §2810.5 notice are legally required at hire — and matcha currently doesn't generate them. This is *table stakes*, not a stretch goal, and it's a credibility own-goal in the segment matcha wants to win.

**What ships**:
- Extend offer-letter schema with hourly fields: `hourly_rate`, `regular_rate`, `overtime_rate`, `shift_pattern`, `tip_policy`, `meal_period_policy`, `benefits_eligibility_date`.
- PDF templates for hourly offer letters in plain language.
- State wage-notice generators (NY WTPA, CA §2810.5, others as the registry expands), pulled from `compliance_service.py` per the location.
- Auto-fill from the wage benchmark (§3.1) so the offer is suggested at-or-above market, not below.

**Files**:
- Extend: `server/app/matcha/routes/offer_letters.py`
- Extend: `server/app/matcha/services/compliance_service.py` (notice templates by state)
- New: PDF templates for hourly + state notices

---

## 5. Tier 3 — foundational + audit defense

These don't pitch, but the segment expects them, and several share infrastructure with Tier 1.

### 5.1 Tip pool / tip credit compliance

Handbook tracks `tipped_employees` and `tip_pooling` as booleans only. Recent Starbucks tip-pool class actions ran into the tens of millions. For coffee/smoothie specifically, this is a real liability category.

**What ships**: tip ledger (per pay period: pool size, distribution rule, per-employee allocation), tip-credit-vs-full-min-wage validator per state (illegal in CA, OR, WA, NV, MT, AK, MN), state-specific dual-jobs rule check.

### 5.2 Break-period audit from time punches

The compliance registry has `meal_break`, `rest_break`, `lactation_break`, `missed_break_penalty`. Time-punch ingest from §3.2 unlocks this. California meal-break premium pay (one hour at regular rate per missed meal break) is the largest single QSR wage class-action category.

**What ships**: punch reader that flags missing/late/short breaks per the jurisdiction rule, computes premium owed, flags into ER pipeline.

### 5.3 ACA FTE tracking + benefits eligibility

Once a chain crosses 50 FTE (Applicable Large Employer), ACA penalties bite hard. Matcha can prevent unintentional ALE crossings, auto-flag eligible-but-unenrolled employees, and feed the affordability calculation into the wage benchmark UI.

**What ships**: `aca_fte_service.py` reading time punches, monthly look-back computation, eligibility alerting.

### 5.4 Exit interviews

Currently we have separation paperwork but no exit interview capture. Even at 75% turnover, the exit cohort is the most accurate source of *why* people are leaving — and feeds back into the question library for §4.1 and the flight-risk model in §3.3.

**What ships**: structured exit-interview workflow attached to the existing separation case, themes auto-extracted via `conversation_analyzer.py`, rolled up by manager / location in the scorecard.

---

## 6. Sequencing & shared infrastructure

The right build order isn't strictly Tier 1 → 2 → 3, because some features unlock others.

**Shared infrastructure to build first** (because three Tier 1/3 features depend on it):

- **Time-punch ingest in `hris_sync_orchestrator.py`** — required for §3.2 (Fair Workweek), §5.2 (break audit), §5.3 (ACA FTE), and feeds §3.3 (flight risk).

**Recommended sequence**:

1. Time-punch ingest (foundation)
2. §3.1 Wage benchmark + dashboard widget (fastest visible ROI for sales conversations)
3. §4.4 Hourly offer letters + state wage notices (small surface area, big credibility win)
4. §3.2 Fair Workweek scheduling (heavy lift, biggest single retention move)
5. §4.1 Pulse surveys (feeds §3.3)
6. §4.2 Manager 1:1 + scorecard (also feeds §3.3)
7. §3.3 Flight risk + stay interviews (compounds on #2, #4, #5, #6)
8. §4.3 Recognition (lightweight, ride along)
9. §5.1 Tip pool (audit-defense, segment expects it)
10. §5.2 Break audit (rides on time-punch ingest)
11. §5.3 ACA FTE (rides on time-punch ingest)
12. §5.4 Exit interviews (closes the loop on §4.1 question library)

---

## 7. The dollar story (one slide for the operator)

This is the core sales pitch the platform owes its customers:

> Your 10 stores, 150 staff, 100% turnover today.  
> Industry replacement cost: ~$5,864/employee fully loaded ⇒ **~$880k/year** at the current rate.  
> Independent operators conservatively quote $3,000/employee ⇒ **~$450k/year**.  
>  
> **What we move this number with**:  
> 1. Show you which staff are below market — the 70% lever (Menu Tiger).  
> 2. Publish their schedules with the legally-required notice — the segment's #2 quit cause + class-action shield.  
> 3. Tell you who's about to leave 30–60 days out, with a manager script for the conversation.  
>  
> Conservatively cutting 100% turnover to 65% on a $450k base = **~$160k/yr per 10 stores, recoverable margin** — multiples of the platform price.

That number, on that slide, is what wins the segment.

---

## 8. Out of scope (deliberately)

- POS integration (Toast, Square, Clover) — valuable but not on the critical path. The first wave of customers will accept manual schedule entry; integrate later.
- Payroll write-back — keep matcha as the brain, not the paymaster.
- Onboarding LMS / curriculum content — partner; don't build a content library.
- Background-check provider integration — partner; offer-letter contingency flags already exist.
- Marketing the unbuilt features — until §4.1 actually ships, the `vibe_checks` and `enps` feature flags should be hidden in the company-features UI to avoid selling vapor.

---

## 9. Verification — how we know each piece works

When a Tier 1 item ships, it isn't done until:

- **§3.1 Wage benchmark**: load the 360 BH roster (or another seeded multi-location company), confirm the below-market alerts cross-check against BLS OEWS for 2–3 zip codes. Operator dashboard widget shows non-zero counts and the avoided-replacement-cost math is correct to the dollar.
- **§3.2 Fair Workweek**: simulate a 14-day rolling schedule for a CA/Chicago/NYC location, confirm the engine flags shifts changed inside the jurisdiction notice window and computes the right premium pay. Schedule swap UX works for an off-shift employee on mobile.
- **§3.3 Flight risk + stay interviews**: backtest the score against the seeded company's historical separations — does the score correlate with who actually left in the 30–60-day window? Stay-interview cases auto-create with the right question prompts pre-filled from the contributing factors.

Same standard applies to Tier 2/3 as they ship: test against real-shape data, verify the math the operator will see, and confirm at least one full happy-path flow end-to-end before declaring done.

---

## 10. What this plan does NOT change

The recruiting front end (AI screening interviews, resume matching, recruiting project pipelines) is matcha's existing strong suit and stays the entry point. The compliance/legal-defense skeleton (separation, COBRA, I-9, ER copilot, IR incidents, pre-termination) is what wins the audit-conscious buyer and stays as table stakes. The plan above adds the **retention layer in between** — the layer that turns matcha from "we documented your firing well" into "we kept your barista."

That's the segment-winning shift.
