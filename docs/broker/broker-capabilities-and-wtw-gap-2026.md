# Matcha Broker — Capabilities, WTW 2026 Coverage & Gaps

_Last updated: 2026-06-20_

A single reference for the broker product: **(A)** everything Matcha gives brokers today, **(B)** how that maps to the needs in WTW's _Insurance Marketplace Realities 2026 (Spring Update)_, and **(C)** what's still missing. Source report: `~/Desktop/insurance-marketplace-realities-2026-spring-update-1805.pdf` (184 pp).

> **Status 2026-06-20 — the report's macro needs A (strategic, pp.4–13) + B (HR-adjacent lines) are implemented.** Shipped since this doc was first written: submission packet + AI coverage-gap (`3942146`), composite risk index + client portal (`1e2ef44`), WC class-code dimension (`7c67877`), resident-care risk asset (`00e4faa`), and the EPL pay-transparency/BIPA/AI-hiring trackers (`5472281`). **Still open (by design):** pay-equity/DEI as tools (need payroll/demographics), a *licensed* NCCI rate/class feed, loss-run PDF auto-parse + client-intake link. C-list lines (cyber/fiduciary/P&C) remain out of scope.

---

## 0. The two broker models (read this first)

Everything below splits along one architectural line:

| Model | What it is | Status |
|---|---|---|
| **Pass-through** (today) | Broker sees + acts on data from the businesses they **onboarded onto Matcha** (each client is a Matcha tenant with a `companies` row). All current features key on `companies.id`. | **Live** |
| **Broker-only / off-platform** (next) | Broker manages clients that are **not on Matcha** — keying in / ingesting data (loss runs, underwriting questionnaires) about prospects or book clients who never onboard. | **Not built** (design agreed; v1 scope pending) |

The WC + EPL engines we just shipped are **pass-through** (they read each tenant client's operational data). The off-platform model reuses the same scoring engine but feeds it broker-entered/ingested inputs instead of derived data.

---

## Part A — What Matcha gives brokers today

### A1. Account management & onboarding
- **Client onboarding pipeline** — create client setups (single + batch ≤50), invite tokens, stage pipeline (submitted → under_review → configuring → live), cancel/expire. `routes/brokers.py`, `pages/broker/BrokerClients.tsx`, `BrokerPipeline.tsx`.
- **Seat pooling** — allocated/committed/remaining seats; company-pinned client invites that debit the pool. `BrokerClientSeats.tsx`.
- **Referral links** — shareable Matcha-Lite signup tokens (broker- or business-paid). `BrokerReferralLinks.tsx`.
- **Team management** — multi-user broker orgs, owner/admin/member roles + granular permissions. `BrokerTeam.tsx`.
- **Terms gate** — broker must accept partner terms before onboarding clients.
- **White-label / co-branding** — per-broker branding (logo, colors, login subdomain, support identity); slug-based runtime restyle of the login page. `broker_branding_configs`.
- **Lifecycle / transitions** — convert-to-direct / transfer-to-broker / sunset / matcha-managed off-boarding workflow; data-handoff tracking. `broker_company_transitions` (admin-driven).
- **Commercials** — `broker_contracts` (billing mode, PEPM rate, minimum commit) — stored, no billing integration.

### A2. Book of Business (portfolio visibility)
- **Portfolio dashboard** — total clients, employees, at-risk count; per-client risk signal (healthy/watch/at_risk from policy-compliance + open actions); handbook-coverage rollup; setup-status grid. `BrokerDashboard.tsx`, `/brokers/reporting/portfolio`.
- **Per-client deep view** — `BrokerClientDetail.tsx` tabs: Overview, Compliance (per-location requirements), Policies & Handbooks (signature rates + handbook strength), IR/ER (incident + ER summaries), **Workers' Comp** (new), **EPL Readiness** (new), Activity (audit feed). `/brokers/companies/{id}`.
- **Handbook coverage** — per-client handbook strength score + label across the book.

### A3. Risk intelligence
- **Risk alerts** — automated TRIR/DART/lost-day/claim-free-broken/premium-trend detection, severity-banded, read-state, emailed digest. Celery `broker_risk_alerts` (gated, default off). `broker_risk_alerts` table.
- **Milestones** — positive achievements (claims-free, safety, handbook) with family/tier grouping. Celery `broker_milestones`.
- **AI consultative outreach** — Gemini prompts grounded in a client's WC + renewal + milestone data, 24h cached. `services/broker_outreach.py`, Action Center.

### A4. Workers' Comp depth ⭐ NEW (2026-06-20)
Commits `e45f2b2` (analytics) + `3d3553a` (incident input). Migration `wcdeep01`.
- **Loss metrics** — TRIR, DART, lost days, recordables, severity band, industry benchmark, premium-impact estimate. `services/wc_benchmarks.py`, `compute_wc_metrics`.
- **Experience-mod (EMR) trajectory** — broker records each policy period's mod (+ carrier/premium); debit/credit coloring. `company_wc_mods`.
- **Claim taxonomy** — cumulative-trauma vs acute + **post-termination** flag, set on each recordable via the incident "WC Classification" control. `ir_incidents.wc_claim_type / post_termination`.
- **Return-to-work** — open vs resolved lost-time + avg days to RTW. `ir_incidents.return_to_work_date`.
- **NCCI jurisdiction overlay** — per-state loss-cost rate trend, matched to the client's operating states. `wc_state_rates` (seeded from report p.32).
- **Surfaces** — Workers' Comp tab on client detail + WC-depth strip on the dashboard. `GET /broker/wc-portfolio[/{id}]`, mods CRUD, `/wc-state-rates`.

### A5. EPL readiness ⭐ NEW (2026-06-20)
Commit `dd4df42`. Migration `epldeep01`. `services/epl_readiness.py`.
- **Composite readiness score (0–100)** + band (strong/adequate/developing/exposed) + headline "top gap".
- **Derived (55%)** from existing tenant data — anti-harassment/EEO policy + signature rate, anti-harassment training completion, documented progressive discipline, ER case management, multi-state wage & hour compliance coverage.
- **Attested (45%)** — broker grades the 5 non-derivable underwriting asks (pay transparency, biometric/BIPA, pay equity, AI-hiring audit, DEI). `company_epl_attestations`.
- **Surfaces** — EPL Readiness tab on client detail + band-distribution strip on the dashboard. `GET /broker/epl-portfolio[/{id}]`, `PUT .../attestations/{key}`.

### A6. Employee-benefits broker tooling — ⏸ PAUSED (2026-06-08, "EB-broker, low value")
Built but disabled: eligibility-exception queue (new-hire gaps + termination leaks), renewal-risk radar (company/dept/location), source-agnostic roster CSV ingest, stabilization-kit PDF. `services/benefits_eligibility.py`, `benefit_*` tables. Retained for possible resurrection.

### A7. Admin oversight (platform-admin, not broker-facing)
Create/manage brokers, branding, transitions, deal-flow pricing/proposals. `core/routes/admin.py`, `pages/admin/Brokers.tsx`.

---

## Part B — Coverage vs the WTW 2026 report

Only the report sections relevant to an HR/compliance broker are tracked. **The report's central thesis**: "tomorrow's broker" wins on data — turning clean client data into _risk differentiation_ that earns better terms, via data-driven consultative broking, AI coverage-gap analysis, a client-facing risk portal, and proprietary jurisdiction/hazard risk-index models (exec summary + Newfront/Willis Q&A, pp. 4–13).

### B1. Workers' Comp (report pp. 28–34)
| Report need | Matcha | Status |
|---|---|---|
| TRIR/DART/severity/benchmark/premium | `wc_benchmarks` + `compute_wc_metrics` | ✅ |
| Experience mod (EMR) trajectory | `company_wc_mods` + WC tab | ✅ NEW |
| Cumulative-trauma vs acute + post-termination | `ir_incidents` claim fields + classification control | ✅ NEW |
| Return-to-work / medical management | `return_to_work_date` + RTW metrics | ✅ NEW (RTW; medical-mgmt detail not modeled) |
| State NCCI loss-cost rate trends | `wc_state_rates` overlay | ✅ NEW — 50-state headline seed (licensed feed pending) |
| Class-code (NCCI class) breakdown | `company_wc_class_exposures` + WC tab | ✅ NEW — payroll by NCCI class + est. manual premium (rate feed pending) |

### B2. EPL + Wage & Hour (report pp. 84–87)
| Report need | Matcha | Status |
|---|---|---|
| EPL insurability lens (score + checklist) | `epl_readiness` + EPL tab | ✅ NEW |
| Harassment handling / policy / training hygiene | IR/ER + discipline + handbook + training (derived factors) | ✅ |
| Multi-state wage & hour exposure | compliance coverage factor | ⚠️ PARTIAL — coverage signal, not a min-wage/exempt-threshold/misclassification tracker |
| Pay-transparency compliance | `workforce_compliance` tracker → derives EPL factor | ✅ NEW tool |
| Biometric / BIPA controls | `workforce_compliance` tracker → derives EPL factor | ✅ NEW tool |
| AI hiring-tool bias audit | `workforce_compliance` tracker → derives EPL factor | ✅ NEW tool |
| Pay-equity analysis | attested only | ⚠️ attested, no tool (needs payroll/demographics) |
| DEI posture / EEOC-priority alignment | attested only | ⚠️ attested, no tool (needs demographics) |

### B3. Strategic / platform thesis (report pp. 4–13)
| Report need | Matcha | Status |
|---|---|---|
| Data-driven consultative broking | risk alerts + AI outreach + WC/EPL scoring | ✅ (inward) |
| Proprietary jurisdiction+hazard risk index | `services/risk_index.py` composite (WC+EPL+compliance) | ✅ NEW — one 0–100 index per client, **on- and off-platform** (external = WC+EPL, no compliance) |
| AI coverage-gap analysis | `services/submission_packet.py` (best-effort Gemini) | ✅ NEW |
| Carrier-ready submission packet | `submission_packet.py` + `broker_submission` (tenant + off-platform) | ✅ NEW underwriting submission PDF |
| Client-facing self-serve risk portal | `risk_profile` feature + `/app/risk-profile` | ✅ NEW — own composite index + fixes |

### B4. Healthcare PL / Senior Living (report pp. 142–145, 174–176) — Matcha's vertical
| Report need | Matcha | Status |
|---|---|---|
| Credentialing / license currency | `credential_templates` → currency in resident-care asset | ✅ NEW — packaged in asset PDF |
| Resident-care risk-management program record | `resident_care` feature + asset PDF | ✅ NEW |
| Fall-prevention / safety-program tracking | `safety_programs` (fall_prevention type) | ✅ NEW |
| MVR reviews (hire + annual) | `mvr_reviews` + currency/overdue | ✅ NEW |
| Abuse-incident control narrative | `safety_programs` (abuse_prevention) + asset PDF | ✅ NEW — packaged |

### B5. Out of scope (documented, with reason)
- **Cyber / privacy** (pp. 73–76) — Matcha holds PII but isn't a cyber-posture tool.
- **Fiduciary / ERISA & plan governance** (pp. 93–96) — plan-governance, not Matcha's domain; `benefits_admin` is roster/eligibility only.
- **Pure P&C / specialty** (property, auto, aviation, marine, energy, surety, political risk, etc.) — not Matcha's domain.

---

## Part C — What's missing (prioritized)

### C1. Off-platform broker-only layer ⭐ the standalone product
Everything today requires the client to be a Matcha tenant. To serve a broker's **non-Matcha** clients we need:
1. **External-client entity** — broker-owned, nullable/no tenant (mirror the `fractional_hr` "client may have no tenant" pattern). New tables, parallel to the tenant ones.
2. **Ingest paths** — there is no system tracking these clients, so the broker is the aggregator:
   - **WC**: carrier **loss run** (PDF/CSV) → claim counts + EMR + premium. v1 = manual key of the summary; v2 = AI PDF parse.
   - **EPL**: an underwriting **questionnaire** the broker fills, or a shareable **client-intake link** the company completes without onboarding.
3. **Scoring refactor** — `wc_depth` / `epl_readiness` resolve a tenant `company_id` **or** an external-client id.
> Agreed direction. **v1 scope pending**: broker-keyed only, vs. broker-keyed + loss-run upload + client-intake link.

### C2. Outward "risk-differentiation" layer (the report's actual thesis)
- **Carrier-ready submission packet** — generate an underwriting submission from WC + EPL posture (reuse the WeasyPrint path behind `stabilization-kit.pdf`).
- **AI coverage-gap analysis** — the Newfront flagship; flag gaps in the client's risk posture.
- **Client-facing risk portal** — a self-serve "here's your risk + how to improve terms" surface (today all broker-only).
- **Composite client risk index** — one jurisdiction+hazard score per client (WTW WC/Auto Index analog), rolling WC + EPL + compliance into a single number.

### C3. Turn EPL "attested" factors into real tools
Pay transparency, BIPA, pay equity, AI-hiring audit, DEI are broker-attested today. Each could become a tracked capability (e.g., a pay-transparency job-posting checker, a pay-equity analysis). High effort; only if EPL becomes a headline product.

### C4. WC data completeness
- Full 50-state NCCI rate coverage (only ~16 seeded + 4 demo).
- NCCI class-code dimension.
- Medical-management / provider-network signal.

### C5. Healthcare resident-care risk asset (report's vertical ask)
Package credentialing + incidents + safety/fall-prevention/MVR/RTW programs into the insurer-facing "risk-management program" narrative the report says wins terms in senior living / healthcare PL.

---

## Part D — Suggested sequence

1. **Off-platform broker layer v1** (C1) — the committed direction; makes the scoring engine a standalone broker product.
2. **Outward submission packet + coverage-gap AI** (C2) — the report's thesis; composes the WC + EPL data already built.
3. **Healthcare resident-care asset** (C5) — leans into Matcha's vertical.
4. **WC data completeness** (C4) — ongoing data task, parallelizable.

---

## Appendix — verification & references
- **Status**: WC depth + EPL (`e45f2b2`, `3d3553a`, `dd4df42`); submission packet + coverage-gap + 50-state seed (`3942146`); workforce-compliance EPL trackers (`5472281`); composite risk index + client portal (`1e2ef44`); WC class-codes (`7c67877`); resident-care asset (`00e4faa`). Applied to **dev**; **prod pending** `./scripts/migrate-prod.sh` — migration chain now `wcdeep01 · epldeep01 · brokerpro01 · wcstates01 · wfcomp01 · wcclass01 · rescare01`.
- **Demo data**: `server/scripts/seed_broker_demo.sql` (test broker "Regina George LLC" / `ashVidales+regina@gmail.com`).
- **Key code**: `server/app/matcha/services/{wc_benchmarks,wc_depth,epl_readiness,risk_index,submission_packet,resident_care,workforce_compliance,broker_outreach}.py`; `routes/{broker_portfolio,broker_submission,risk_profile,resident_care,workforce_compliance}.py`; `client/src/pages/{broker/*,app/RiskProfile.tsx,app/ResidentCare.tsx,app/WorkforceCompliance.tsx}`, `client/src/api/{broker,riskIndex,residentCare,workforceCompliance}.ts`.
- **Admin changelog**: entries live at `/admin/updates` (`client/src/data/adminUpdates.ts`).
- **Source report**: WTW _Insurance Marketplace Realities 2026 Spring Update_ — WC pp. 28–34, EPL/wage-hour pp. 84–87, thesis pp. 4–13, healthcare pp. 142–145 + 174–176.
