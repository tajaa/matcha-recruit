# HRIS / Payroll Unified-API Vendor Evaluation

### Finch vs. Merge — Recommendation & Product-Opportunity Analysis

**Prepared:** 2026-05-25 · **Scope:** Matcha (HR · Employee Relations · GRC) · **Evidence:** this codebase + the live LA Non-Profit proposal (`deals/la-nonprofit/`)

---

> ## Bottom Line
>
> **Pick Finch now.** It is the right tool for Matcha's current roadmap — *deep on people*: ER and GRC computed from rich employment/payroll data, lean data-at-rest, broker-security-review friendly, with write-back for provisioning.
>
> **Merge only becomes the right call if Matcha decides to become a GRC orchestration hub** — sitting over the client's *ticketing, accounting, and document* systems, not just their people data. That is a company-strategy bet, not an integration-plumbing decision.

---

## Table of Contents

1. [The Decision, Reframed](#1-the-decision-reframed)
2. [Recommendation: Finch](#2-recommendation-finch)
3. [Cross-Check Against the LA Non-Profit Proposal](#3-cross-check-against-the-la-non-profit-proposal)
4. [Steelman: Where Merge's Breadth Genuinely Fits ER + GRC](#4-steelman-where-merges-breadth-genuinely-fits-er--grc)
5. [Deeper READ Opportunities](#5-deeper-read-opportunities)
6. [WRITE Opportunities](#6-write-opportunities)
7. [New Feature Concepts (Read + Write)](#7-new-feature-concepts-read--write)
8. [Risks & Open Questions](#8-risks--open-questions)
9. [Integration Approach](#9-integration-approach)
10. [Appendix: Evidence & File Paths](#10-appendix-evidence--file-paths)

---

## 1. The Decision, Reframed

This is **not** a capability contest. It is a strategy fork:

| Strategy | What Matcha becomes | Data it needs | Vendor |
|---|---|---|---|
| **Deep on People** | ER + GRC computed from rich employment/payroll data — misclassification, pay equity, retaliation timing, separation risk | Employment, payroll, pay statements, org, time-off, demographics | **Finch** ✅ |
| **GRC Orchestration Hub** | Matcha sits *over* the client's ticketing + accounting + document systems, orchestrating remediation across them | All of the above **plus** ticketing, accounting, file storage | **Merge** |

> **Key insight:** Deeper *HRIS/payroll* reads (pay statements, demographics, org, time-off) are available in **both** vendors — Finch is actually deeper on payroll. The *only* thing Merge uniquely adds is the **non-HR categories** (ticketing, accounting, file storage, CRM, ATS). So "should we pick Merge?" really means "do we want to expand Matcha's surface beyond people data?"

---

## 2. Recommendation: Finch

Three strongest reasons, each grounded in the codebase and the proposal:

### 2.1 Scope is employment-only — Merge's breadth is dead weight *today*
No CRM, accounting, or ticketing footprint anywhere in the code. The one non-HR category on the roadmap is ATS (Greenhouse/iCIMS) — confirmed a **sales-deck upsell line only** (`docs/sales/HEALTHCARE_PRICING.md`: *"+$1.00 PEPM … Not built"*). The LA proposal sells **zero** payroll/benefits/CRM/ATS features. Merge's multi-category platform buys nothing the current product uses.

### 2.2 Brokerage security review punishes a third-party data-at-rest copy
Sold through brokers → every client triggers a security review. Matcha's posture is already lean and defensible:

- Fernet field encryption (`core/services/credential_crypto.py`, `secret_crypto.py`)
- Postgres Row-Level Security tenant isolation (`alembic/.../add_row_level_security.py`)
- AWS Secrets Manager · S3 SSE-256 · **no SSN / DOB / bank / direct-deposit collected at all**

> **Merge is store-and-sync** — it caches a copy of client HR data on *its* servers. That is a new third-party data-at-rest footprint to disclose and defend in **every** brokerage review. **Finch is API-pass-through** — it keeps the at-rest surface lean, matching what Matcha already tells brokers ("US-based residency, AES-256 at rest").

### 2.3 Read-only + shallow today, and Finch fits the broker long-tail
Matcha stores basic identity + a single `pay_rate` + FLSA `pay_classification` — **no** earnings/tax/deduction breakdowns, **no** benefits, **no** pay stubs. The broker channel = **many small client companies, one connection each** (`brokers` → `broker_company_links` → `companies`, 1-to-many). Those clients run long-tail / no-API payroll → **Finch's managed (assisted) connections cover that tail**, and Finch's employment **write-back** unlocks provisioning value Merge's thin HRIS-write does not.

---

## 3. Cross-Check Against the LA Non-Profit Proposal

The proposal sells **Risk + Compliance + ER Intelligence** (500-employee multi-site CA nonprofit, ~$73k/yr recurring). HRIS is positioned as **plumbing, not a sold feature** — Discovery lists an "HRIS audit"; Employee Directory promises only **CSV bulk import + Google/Slack provisioning**. Neither Finch nor Merge is named.

### 3.1 What the proposal's features actually consume from HRIS

| Consumed field | Feature it feeds |
|---|---|
| Roster + work site + department | Multi-site jurisdiction mapping ("mapped to your sites & roles"); onboarding cohorts |
| FLSA class + employment type + `pay_rate` | Risk Assessment wage-and-hour exposure; "misclassified coordinator" detection |
| Hire / term dates + `employment_status` | Pre-Termination Intelligence; separation & LOA tracking |
| Manager hierarchy | ER cases; dashboards |

> Every consumed field is **basic identity + a single comp rate**. Zero need for deep payroll, benefits, CRM, accounting, or ATS for what is sold today. **The proposal independently confirms Finch.**

### 3.2 ⚠️ Honest caveat — do not oversell credential tracking
The proposal sells license tracking (LCSW / LMFT / ASW, NPI, DEA, background checks) heavily — but **payroll APIs do not carry clinical credentials.** Gusto exposes none; only ADP custom fields do. **Neither Finch nor Merge populates these** — credentials stay CSV/manual regardless of vendor. Do not pitch HRIS sync as solving credential tracking.

---

## 4. Steelman: Where Merge's Breadth Genuinely Fits ER + GRC

This is the case *for* Merge, stated fairly. Finch (employment-only) **cannot touch any of these.**

### 4.1 🟢 Ticketing (ServiceNow / Jira / Zendesk) — strongest fit
GRC remediation *is* ticketing. Today Matcha's corrective actions, ER action items, and accommodation steps live **inside** Matcha; enterprise GRC clients already run remediation in ServiceNow.
- **Read:** pull facilities/IT tickets that correlate with safety incidents (broken-handrail ticket ↔ fall incident) → richer pattern detection.
- **Write:** push Matcha corrective actions / pre-term action items / accommodation steps **into** the client's ServiceNow → status syncs back → Risk dashboard closes the loop.

### 4.2 🟢 Accounting (QuickBooks / NetSuite / Xero) — real nonprofit / grant angle
The proposal sells *"drain restricted funds"* and LAHSA/HUD grant compliance — that exposure lives in the GL.
- **Read:** restricted-fund balances + labor cost by program/grant → Cost-of-Risk ties a wage-and-hour hit to the *actual* grant it drains; grant-compliance labor-allocation reporting.

### 4.3 🟢 File Storage (SharePoint / Box / Drive) — governed-document fit
ER investigations, signed acknowledgments, I-9s, and policy docs often must live in the client's *governed* repo (legal hold, retention).
- **Read:** ingest existing policy / investigation / I-9 docs into ER Copilot + Handbook context.
- **Write:** push counsel-ready ER exports + audit packets back to their retention-governed store. *(Matcha's first-party S3 won't satisfy enterprise legal that requires docs in their own repo.)*

### 4.4 🟡 ATS — marginal
Pre-hire risk scoring upsell; recruiting, not GRC. Low priority.

### 4.5 🔴 CRM — weak
Donor CRM ≠ ER/GRC. Skip.

> **Takeaway:** If Matcha's roadmap is to become a **GRC orchestration hub**, §4.1–4.3 are real value Finch can never deliver. That is the legitimate Merge case — and it is a *bigger-company bet* that also adds the store-and-sync at-rest footprint at exactly the moment you're courting broker security reviews.

---

## 5. Deeper READ Opportunities

Available in **both** vendors (Finch deeper on payroll). These sharpen claims the proposal **already makes**:

| Data pulled | Unlocks |
|---|---|
| **Pay statements** (hours, OT, earnings types, gross/net) | ⭐ Turns the headline wage-and-hour pitch from *estimated* (NAICS sector model + one rate) into *measured, per-employee, dollar-quantified* exposure. Biggest single upgrade to Risk Assessment / Cost-of-Risk. |
| **Org hierarchy / span-of-control** | ER hotspot detection — one manager, disproportionate complaints/terminations = risk concentration. |
| **Time-off / leave data** | FMLA/CFRA compliance + **retaliation timing** (termination N days after leave/complaint = the proposal's exact retaliation narrative, now *detected*). |
| **Precise work address** | Auto-assign Compliance Engine jurisdictions (replaces manual site-mapping). |
| **Comp × protected class** | CA Pay Data Reporting (SB 1162) + pay-equity — a real CA GRC obligation Matcha could own. |
| **Tenure / time-in-role** | Separation-risk weighting + adverse-impact scoring. |
| **Comp history** | Feeds the "4-week trend lines" + separation-risk modeling the proposal advertises (today we COALESCE to a single current rate). |

> ⚠️ **Demographics caveat:** demographic data supercharges adverse-impact analysis (proposal cites EEOC/FEHA/retaliation) but is exactly the sensitive PII that raises brokerage-security stakes — which **reinforces lean-at-rest Finch** over store-and-sync Merge.

---

## 6. WRITE Opportunities

Push data **back into** the HRIS — the inverse of today's pull-only flow:

| Trigger in Matcha | Write to HRIS |
|---|---|
| Onboarding completed | **Create employee** in payroll (provision) |
| Discipline / termination outcome | Update `employment_status` → triggers offboarding |
| Misclassification flag accepted | Write corrected FLSA / employment_type |
| Pay-equity remediation | Write corrected comp rate |
| Accommodation = schedule change | Write to HRIS scheduling / notes |
| Reorg | Sync manager / department changes |

> **Finch** has employment write-back. **Merge's** HRIS-write is thinner — *but* Merge can write to **ticketing**, where GRC action items actually belong (see §4.1).

---

## 7. New Feature Concepts (Read + Write)

Ordered highest-leverage first. The **Vendor** column shows which platform each requires.

| # | Feature | Read → Write | Fits | Vendor |
|---|---|---|---|---|
| 1 | **Closed-loop misclassification remediation** — flag exempt-below-CA-threshold / ABC-fail → human decides → write corrected class | pay/class → FLSA | GRC | **Finch** ✅ |
| 2 | **CA Pay Data / pay-equity engine** — disparity calc → SB 1162 report → write remediation rates | comp + demographics → comp | GRC | **Finch** ✅ |
| 3 | **Retaliation guardrail** — risky-timing detection on proposed terminations → optional hold-flag | leave/complaint/incident dates → flag | ER | **Finch** ✅ |
| 4 | **Auto-jurisdiction** — work address → auto-configure Compliance Engine sites | work address → (internal) | GRC | **Finch** ✅ |
| 5 | **GRC remediation bridge** — incident/ER/compliance action → write ServiceNow ticket → read status → close loop | internal → ticket | GRC | **Merge only** |
| 6 | **Grant labor-allocation compliance** — labor cost by grant → tie exposure to real restricted-fund balances | accounting → (internal) | GRC | **Merge only** |

> **Pattern:** the **four highest-leverage, proposal-aligned** features (1–4) are all **Finch-reachable and deeper on Finch.** The Merge-only plays (5–6) are real but represent the *GRC-hub expansion* bet, not the current roadmap.

---

## 8. Risks & Open Questions

### Biggest risk of choosing Finch
If **ATS sync** ever becomes real (Greenhouse/iCIMS), Finch can't cover it — we'd add a second vendor or revisit Merge. Currently flagged sales-deck-only, so the risk is low. Secondary: Finch's connector count for obscure HRIS is narrower than Merge's, partially offset by managed connections.

### Confirm before signing
- [ ] **Pricing — real quotes, both vendors.** Per-connection cost at many low-headcount broker connections is the cost risk. Confirm who pays (employer-pays vs. we-pay) and per-connection rate under the broker-reseller model.
- [ ] **Small-payroll coverage.** Validate Finch managed-connection coverage against the payroll systems brokerage clients actually run.
- [ ] **Write-back appetite.** Read-only today; confirm scope if we want provisioning / offboarding write-back (picks the Finch endpoints).
- [ ] **GRC-hub intent.** Is orchestrating across ticketing/accounting/docs (§4) a 12–24 month goal? If yes, re-weight toward Merge.

---

## 9. Integration Approach

The codebase is already shaped for this — **extend** the existing provisioning surface rather than build new infrastructure.

### Reuse what exists
- **Schema:** `integration_connections` (provider enum, encrypted `secrets` JSONB), `external_identities`, `hris_sync_runs`, `provisioning_audit_logs` — `server/app/database.py` (~line 4232+). Extend the provider CHECK to include `'finch'` *(Alembic migration → **user approval required**, per `server/CLAUDE.md`)*.
- **OAuth state pattern:** HMAC-signed, company_id-embedded, TTL-bounded — built for Slack/Gusto in `server/app/matcha/routes/provisioning.py` (Gusto OAuth ~line 1629). Finch Connect uses the same authorization-code shape; clone it.
- **Secret encryption:** `core/services/secret_crypto.py` for the Finch token.
- **Sync orchestrator:** `server/app/matcha/services/hris_sync_orchestrator.py` (`start_hris_sync`, `_sync_single_employee`, COALESCE-on-partial upsert) — reuse the upsert/normalize/audit pipeline; only the fetch+normalize source changes.
- **Background jobs:** Celery worker (`server/app/workers/celery_app.py`) for periodic sync.
- **Feature gate:** `hris_import` flag already wraps every HRIS endpoint.

### New code
- `server/app/matcha/services/finch_service.py` — Finch Python SDK wrapper mirroring `GustoHRISService` (`fetch_workers`, `normalize_worker` → existing employee field shape).
- Finch Connect authorize + callback routes in `provisioning.py`, cloning the Gusto pair; store token via `secret_crypto`.
- *Optional later (matches §5–7):* pull `pay_statements`; subscribe to Finch employment events; add write-back behind a new sub-flag (keep read-only default).
- Celery task to dispatch periodic Finch syncs through the existing orchestrator.

### Verification
- **Dev:** connect a Finch **sandbox** company via Connect → run `/hris/sync` → assert rows upserted into `employees` + `external_identities`, and an `hris_sync_runs` row with created/updated counts. **Sandbox data only — never run against production payroll.**
- Confirm `hris_import`-gated endpoints 403 without the flag.
- **Write-back (if built):** test create/update against Finch sandbox exclusively; assert audit rows in `provisioning_audit_logs`.
- The provider-enum migration is the only schema change — present it for explicit approval before applying; **do not run `alembic upgrade` autonomously.**

---

## 10. Appendix: Evidence & File Paths

| Area | Location |
|---|---|
| Existing HRIS integration (Gusto + ADP) | `server/app/matcha/services/hris_service.py`, `hris_sync_orchestrator.py` |
| HRIS routes (connect / sync / OAuth / webhook) | `server/app/matcha/routes/provisioning.py` |
| Feature flag (`hris_import`, default off) | `server/app/core/feature_flags.py` |
| Stored employee fields | `alembic/.../7c1de748641e_add_employee_portal_tables.py`, `0a9bffab08a8_add_employee_compensation_fields.py` |
| Integration schema tables | `server/app/database.py` (~line 4232+) |
| Field encryption (credentials, secrets) | `core/services/credential_crypto.py`, `core/services/secret_crypto.py` |
| Tenant isolation (RLS) | `alembic/.../add_row_level_security.py` |
| Broker → company model | `server/app/database.py` (`brokers`, `broker_members`, `broker_company_links`) |
| ATS as unbuilt upsell | `docs/sales/HEALTHCARE_PRICING.md`; `docs/plans/ONBOARDING_ROADMAP.md` |
| Live proposal cross-checked | `deals/la-nonprofit/LA_NonProfit_Proposal_v1.pdf` |

**Read-only / pull-only confirmed:** OAuth scopes are read-only (`employees:read jobs:read compensations:read employee_addresses:read`); no POST/PUT/PATCH to external HRIS exists except OAuth token exchange. The Gusto webhook is inbound (Gusto → Matcha) only.
