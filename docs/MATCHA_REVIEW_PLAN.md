# Review Plan: `server/app/matcha` full sweep

## Context

Full issue review of `server/app/matcha` (~117k lines: 40+ route modules, ~100 services, 4 route packages — `ir_incidents/`, `employees/`, `matcha_work/`, `labor_relations/`).

**Lenses:** security + tenant isolation, correctness, performance, code quality / dead code.
**Depth:** multi-agent full sweep (10 domain finder agents → adversarial verify → ranked report).
**Deliverable:** findings report only — no fixes applied until requested.

## Severity rubric (shared by all finders — apply verbatim)

Finders calibrate severity against this table, not their own judgement, so "Critical" means the same thing across all 10 agents:

| Severity | Definition |
|---|---|
| **Critical** | Cross-tenant read/write, auth bypass, or unauthenticated data exposure reachable today with no special preconditions |
| **High** | Same class but requires an authenticated user of another role/company, a leaked-but-plausible token, or a non-default feature flag |
| **Medium** | Correctness bug with real user-visible impact (wrong data, silent failure, jsonb read/write mismatch), or a security weakness needing an unlikely precondition |
| **Low** | Performance, code quality, dead code, hardening suggestions |

Every finding **must quote the exact offending line(s)** from the file — a finding without a verbatim code quote is discarded before verification.

## Pre-scan results (already done)

Router/auth inventory produced. Highlights:

- **SQL f-strings:** exactly 3 in the package, all verified safe (values parameterized, interpolated parts are hardcoded constants). Do not re-flag:
  - `routes/dashboard.py:1380`
  - `routes/ir_incidents/analytics.py:66`
  - `routes/employees/invitations.py:249`
- **Broker endpoints take `company_id` from client input** — need ownership-check verification:
  - `routes/broker_portfolio.py:904` (`company_id: UUID = Query(...)`)
  - `routes/broker_submission.py:267`, `:314` (path/body param)
- **`routes/fake_hris.py`** — `_require_bearer` accepts any `Bearer …` token (line ~36); `/auth/token` + `/health` fully open. Intentional ADP mock, but a real HTTP surface returning worker data.
- **WS routers `project_ws.py` (953 LOC) / `thread_ws.py` (306 LOC)** mounted in `app/main.py`, not `routes/__init__.py` — easy to miss in scoping. JWT via query token.
- **Routers with no mount-level gate** (auth per-endpoint only — confirm every endpoint has a dep): `companies`, `interviews`, `dashboard`, `provisioning`, `onboarding`, `employee_portal`, `notifications`, all `broker_*`, `wc_rates_admin`, `billing.admin_router`.
- **Public/token surfaces (no auth dependency at all):** `inbound_email.py` (`/report/{token}`, `/intake/{token}`, `/request-info/{token}`), `external_intake.py`, `invitations.py`, offer_letters `candidate_router`, er_copilot `public_router` (`/shared/er-export`), matcha_work `public_router` (review-requests, signature webhook, github webhook), discipline signature webhook, legal_defense `/legal-pilot/share/{token}`, `twilio_webhook.py`, `fake_hris.py`.

## Finder chunks (~7–14k LOC each, measured 2026-07-05)

| # | Chunk | Scope |
|---|---|---|
| 1 | **IR package** | `routes/ir_incidents/*`, `ir_onboarding.py`, `ir_surveys.py` + services `ir_ai_orchestrator`, `ir_analysis`, `ir_flow`, `ir_consistency`, `ir_precedent`, `ir_voice_parser`, `ir_report_poster`, `ir_interview_questions`. Branch `matcha/ir-audit` just hardened intake — review new code too. |
| 2 | **Public/token surfaces** (security-focused) | All public endpoints listed above + interview WS token auth + `thread_ws.py`/`project_ws.py` query-token auth. Lens: token entropy/expiry/single-use, enumeration, rate limits, IDOR, webhook signature verification. |
| 3 | **matcha_work routes** | `routes/matcha_work/*` (incl. unmounted helper `ai_turn.py`), `journals.py`, `productivity.py`, `notifications.py`, `project_ws.py`, `thread_ws.py`. Context: journal isolation is app-level only, `created_by`-scoped (RLS dormant); personal vs business identity split. |
| 4 | **matcha_work services** | `matcha_work_document` (2787), `matcha_work_ai`, `project_service`, `project_task_service`, `project_subtask_service`, `project_file_service`, `project_comment_service`, `journal_service`, `billing_service`, `token_budget_service`, `entitlements_service`, `notification_service`, `mentions`, `productivity_service`, `escalation_service`, `task_summary_service`. |
| 5 | **ER / discipline / legal** | `er_copilot.py` (4132), `discipline.py`, `pre_termination.py` + services `er_*`, `discipline_*`, `pre_termination_service`, `legal_defense` (1599), `legal_intake_parser`, `legal_research`, `claims_readiness`. Legal Pilot anti-hallucination gate (`validate_citations`) correctness in scope. |
| 6 | **Employees / portal / HR ops** | `employees/*` pkg, `employee_portal.py`, `onboarding.py`, `training.py`, `i9.py`, `cobra.py`, `separation.py`, `accommodations.py`, `flight_risk.py` + services `hris_service`, `finch_service`, `hris_sync_orchestrator`, `onboarding_*`, `leave_*`, `flight_risk_service`, `training_*`, `accommodation_service`, `resume_parser`. Employee-role vs client-role scoping is the key isolation lens. |
| 7 | **Broker surface** | `brokers.py` (2103), `broker_portfolio.py`, `broker_external.py`, `broker_submission.py`, `broker_loss_runs.py`, `broker_pilot.py`, `benefits.py`, `fractional_hr.py` + services `broker_*`, `external_clients`, `submission_packet`, `submission_readiness`, `epl_readiness`, `benefits_eligibility`. Priority: broker→client ownership checks on every client-supplied `company_id` (pre-flagged sites above). |
| 8 | **Risk / property / WC stack** (~11.2k) | `risk_assessment.py`, `risk_profile.py`, `workforce_compliance.py`, `controls_evidence.py`, `limit_adequacy.py`, `property.py`, `driver_risk.py`, `resident_care.py`, `labor_relations/*` + services `risk_*`, `wc_*`, `property_*`, `loss_*`, `monte_carlo_service`, `venue_severity`, `benchmark_service`, `pay_equity_analysis`, `wage_benchmark_service`, `exclusion_gap`, `contract_parser`, `workforce_*`, `driver_risk`, `resident_care`, `controls_evidence`, `limit_adequacy`, `labor_relations_ai`. |
| 9 | **Platform routes** (~7.6k) | `dashboard.py` (2224), `provisioning.py` (2329), `companies.py`, `billing.py` (incl. `admin_router`), `wc_rates_admin.py`, `matcha_x_onboarding.py`, `offer_letters.py`. |
| 10 | **Interviews + integration services** (~7.1k) | `interviews.py` (1546) + services `conversation_analyzer`, `culture_analyzer`, `google_workspace_service`, `slack_service`, `gmail_service`, `github_service`, `element_*`, `commit_scan_service`, `ticket_draft_service`, `research_browse_service` (SSRF lens — fetches URLs by design), `recruiting_client_service`, `model_pricing`, `signature_provider`, `naics_titles`, `bls_injury_rates_2024` (skim generated data). |

Original chunk 9 measured ~14.7k (over target) — split into 9/10 above. Chunk 8 measured within target; kept as-is.

## Every finder gets

- Four lenses + the shared severity rubric above + structured output schema: `{file, line, severity (Critical/High/Medium/Low), category, summary, failure_scenario, code_quote}`.
- Repo gotchas:
  - asyncpg pool has **no jsonb codec** — jsonb columns return raw strings; missing `json.loads` on read (or `json.dumps` on write) is a real bug class.
  - Tenant scoping convention is `get_client_company_id(current_user)` — any query filtering on client-supplied `company_id` without ownership check is a finding.
  - `require_feature` stacking; per-endpoint deps required where no mount gate.
  - Blocking sync calls (requests, WeasyPrint, heavy CPU) in `async def` handlers without `asyncio.to_thread`.
  - S3 key construction / file-upload path handling — user-influenced filenames or IDs concatenated into storage keys or filesystem paths.
  - SSRF where user input reaches an outbound fetch (`research_browse_service` fetches URLs by design — check target validation; also any webhook/URL fields elsewhere).
  - Multi-statement writes without a transaction — partial-write races on failure between statements.
  - Query-string JWTs (WS routers `project_ws.py`/`thread_ws.py`, interview WS) end up in access logs — token-in-URL is a logging-leak finding, separate from token semantics.
  - Celery tasks live in `app/workers/tasks/` (out of scope except callsites).
- Do-not-re-flag list (3 safe f-strings; `fake_hris` intentional mock — unless a new angle beyond known facts).

## Verify stage (pipeline, no barrier)

Chunks are file-disjoint → no cross-finder dedup needed; each finder's findings verify while other finders still run.

- Each **Critical/High** finding → 1 adversarial verify agent (reads actual code + callers, tries to refute). Verdict: CONFIRMED / REFUTED / PLAUSIBLE.
- **Medium**: spot-verify a random sample — 20% per chunk, minimum 3 (all if fewer). If a chunk's sample refutation rate exceeds 1/3, verify the rest of that chunk's Mediums too. Unsampled Mediums are labeled unverified in the report.
- **Low** pass through unverified, labeled as such.
- Findings missing the required `code_quote` are discarded before this stage (see rubric).

## Cross-cutting greps (inline, cheap)

- ~~f-string SQL across package~~ — **done**: only the 3 known-safe sites exist.
- jsonb columns fetched then used as dict without `json.loads`.
- jsonb writes passing a dict/list without `json.dumps` (the write-side twin of the above).
- `@router.` decorators without any `Depends(` auth dep — **must also match `@router.websocket`** (WS endpoints don't take deps the same way; check their in-handler token auth explicitly).

## Report

Ranked report:
1. Confirmed Critical/High with `file:line` + failure scenario
2. Medium (verification status labeled per finding — sampled vs unverified) and Low, grouped by category
3. Quality / dead-code notes

Written to `MATCHA_REVIEW.md` in project root and **committed to the review branch** + summary in chat. (Remote sessions run in an ephemeral container — an uncommitted working-tree file is lost when the container is reclaimed, so "working tree only" would delete the deliverable.) Top 3–5 confirmed findings personally re-read before reporting.

## Non-goals

- No fixes; no commits except the `MATCHA_REVIEW.md` report itself (on the review branch); no other branch changes.
- No DB access; static code review only.
- `server/app/workers/`, `server/app/core/` out of scope (matcha package only), except reading a caller/callee to confirm a finding.
