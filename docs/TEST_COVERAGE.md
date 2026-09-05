# Test Coverage Analysis & Improvement Roadmap

_Last updated: 2026-05-31_

This document captures the current state of automated testing in Matcha Recruit
and a prioritized plan for improving it. It is a roadmap, not a status badge —
treat the priorities as the backlog.

## TL;DR

- **CI runs zero tests.** The only workflow (`.github/workflows/deploy.yml`)
  builds and deploys; nothing gates a regression from shipping.
- **The frontend is effectively untested:** ~480 source files, **1** test file.
  Tooling (vitest + testing-library + coverage) is fully configured — only
  tests are missing.
- **The backend has ~67 test files but <5% of routes are tested at the HTTP
  level.** The suite is logic-centric: it exercises functions in isolation,
  rarely the actual endpoints through FastAPI. Auth enforcement, status codes,
  request validation, and per-query `company_id` scoping are almost never
  verified at the boundary where they run.
- **The money & security surfaces are the least covered:** Stripe webhooks,
  billing, HRIS provisioning, and the email send-guards have ~zero coverage.

## The numbers

| Area | Source | Tests | Ratio |
|---|---|---|---|
| Backend (`server/app`) | 342 files / ~189k LOC | 67 test files / ~17k LOC | ~1:11 LOC |
| Frontend (`client/src`) | 480 files / ~103k LOC | **1 test file / 196 LOC** | ~1:530 LOC |

Backend test files by domain: matcha_work (9), infrastructure (7),
employees (7), ir_incidents (5), er_copilot (5), auth (5), compliance (4),
training (3), channels_ws (3), onboarding (2), handbook_audit (2), and one
each for wage_benchmarks, pre_termination, paid_channels, offers, interviews,
handbook, brokers, admin_onboarding — plus 7 loose top-level files (deal_*,
ir_*, main_middleware).

## Critical gaps

### 1. CI runs no tests
`.github/workflows/deploy.yml` triggers on `push` and `pull_request` but its
only jobs are **Build & push Docker images** and **Deploy to EC2**. There is no
`pytest` step and no `vitest` step. Tests only run when a developer remembers
to run them locally — and many silently skip without a DB (see #4). This is the
single highest-leverage gap: until CI runs tests, every other test investment
is unprotected.

### 2. The frontend is effectively untested
One test (`client/src/components/er/ERTimelinePanel.test.tsx`) across ~480
source files. The infrastructure cost is already paid (`vitest.config.ts`,
`src/test/setup.ts`, v8 coverage). Untested product-critical logic includes:

- `client/src/utils/tier.ts` — pure functions (`isIrOnlyTier`,
  `isMatchaLitePending`, `isResourcesFreeTier`) that decide **which of the four
  products a user sees**. Pure and dependency-free — highest value-per-effort
  target in the repo.
- `client/src/components/TenantSidebar.tsx` — the only place that picks the
  sidebar shell.
- `client/src/api/client.ts` (325 LOC) — JWT attach + 401 refresh-and-retry. A
  bug here logs everyone out.
- `client/src/components/FeatureGate.tsx`, `client/src/hooks/useMe.ts` —
  feature gating + `hasRole`/`hasFeature`.

### 3. No HTTP-level route tests (the dominant structural weakness)
Across ~67 test files, essentially **none** use `TestClient(app)` /
`AsyncClient` against the mounted app (4 files touch ASGI transport, narrowly).
Even "tested" modules (`compliance_service.py`, `matcha_work.py`,
`interviews.py`) only have pure-logic tests — they never go through the
endpoint. As a result the following are almost never verified at the boundary:

- Status codes & request validation
- Authorization enforcement — `require_admin` / `require_client` /
  `require_feature` actually returning 403 for the wrong role/missing feature
- Per-query `company_id` scoping (multi-tenant isolation). Note:
  `tests/infrastructure/test_rls_isolation.py` validates DB **policies**, but
  nothing validates that routes **apply** the company filter.

### 4. DB-gated tests silently skip
Real-DB tests use `pytest.mark.skipif(not DATABASE_URL)`. In any environment
without a tunnel (including CI, if it ran them) these vanish to green with no
signal. ~40 of the test files are pure-logic and need no DB; these are the safe
CI-on-every-PR subset.

### 5. No shared test infrastructure
- No `conftest.py` anywhere, no `pytest.ini` / pytest config.
- No shared fixtures: no app fixture, no JWT-token helper, no test-company
  factory. Each test reinvents setup; Gemini stubbing is re-done per file.

## Untested high-risk backend modules

Confirmed zero (or logic-only) coverage, by cross-referencing imports:

| Module | LOC | Why it matters |
|---|---|---|
| `core/routes/admin.py` | 10,260 | Feature-flag toggles, jurisdiction/compliance config, Stripe ops, account mgmt. Zero direct route tests. |
| `core/routes/stripe_webhook.py` | 582 | **Webhook signature validation, event dedup/idempotency, subscription/channel activation.** Broken signature = auth bypass; broken idempotency = double-charge/double-provision. |
| `core/services/stripe_service.py` | 588 | Stripe API wrapper — checkout session creation, subscription ops. |
| `matcha/routes/billing.py` | 541 | Token packs, personal subs, `checkout.session.completed` → `enabled_features.incidents=true` (the webhook that gates the whole Matcha-lite paid experience). |
| `core/routes/resources.py` | 989 | Matcha-lite Stripe checkout (`POST /resources/checkout/lite`). |
| `matcha/routes/provisioning.py` | 2,329 | HRIS sync (Gusto/Finch), Google Workspace/Slack OAuth — money & PII. |
| `matcha/routes/dashboard.py` | 2,141 | Primary platform surface; cross-domain aggregation queries. |
| `matcha/routes/employee_portal.py` | 1,290 | Employee self-service (mobility routes partially covered). |
| `matcha/services/project_service.py` | 1,710 | Matcha-work project CRUD, file handling, ownership checks. |
| `matcha/routes/discipline.py` + `services/discipline_engine.py` | 1,328 | Progressive discipline workflow — legal exposure. |
| `matcha/services/signature_provider.py` | 282 | E-signature for offer letters / separation agreements. |
| `core/services/email/**` | ~1,000 | Send paths + the reserved-domain guard (`_is_reserved_test_domain`). |

Also unverified at route level: `accommodations`, `handbooks`, `separation`,
`cobra`, `i9`, `newsletter`.

### Special call-out: the reserved-email-domain guard
`email.py:_is_reserved_test_domain` is the defense-in-depth against the
medcenter.com bounce-storm that CLAUDE.md treats as a near-incident — yet no
test asserts `@example.com` / `*.test` / `*.invalid` are blocked. Cheap to test,
high consequence if it regresses.

## What IS covered well

- Multi-tenant RLS at the DB-policy level — `tests/infrastructure/test_rls_isolation.py`.
- Feature-flag merge/overlay logic — `tests/infrastructure/test_feature_flags.py`.
- Paid-channel payment service + inactivity worker — `tests/paid_channels/`.
- Compliance dedup/jurisdiction filtering — `tests/compliance/test_compliance_service.py`.
- Handbook service logic — `tests/handbook/test_handbook_service.py`.
- The "deal" pricing engine — `tests/test_deal_*.py`.
- Broker flows (registration, scope resolution, referral) — `tests/auth/`.

…all valuable, but all **logic-level**, not endpoint-level.

## Prioritized roadmap

### Tier 1 — stop the bleeding (low effort, high value)
1. **Add a CI `test` job that gates deploy.** Run the ~40 no-DB pytest files +
   `vitest run` on every PR. Nothing protects anything until this exists.
2. **Frontend: test `tier.ts` and `client.ts` (401 refresh).** Pure logic, huge
   product impact, tooling already configured.
3. **Test the email reserved-domain guard.** One small file; guards a known
   near-incident.

### Tier 2 — close the money/security holes
4. **`conftest.py` harness** — app fixture + JWT-token helper + centralized
   Gemini stub (+ optional mocked-asyncpg or opt-in real-DB marker so DB tests
   don't silently skip). This is a prerequisite, not a nicety: it makes every
   route test below cheap to write.
5. **`stripe_webhook.py` tests** — signature rejection, idempotency/dedup, event
   routing. Highest security risk.
6. **Billing / checkout flow tests** (`billing.py`, `resources.py`) — mock
   Stripe, assert feature flips on `checkout.session.completed`.
7. **Authorization-denial matrix** — HTTP-level: wrong role / missing feature →
   403 across `require_*` dependencies; confirm `company_id` scoping on read
   routes.

### Tier 3 — fill the big untested modules
8. `dashboard.py`, `provisioning.py` (HRIS), `discipline_engine.py`,
   `project_service.py`, `signature_provider.py`.
9. Frontend component coverage: `FeatureGate.tsx`, `TenantSidebar.tsx`, key
   product surfaces.

## How to run tests today

```bash
# Backend (requires pytest installed; DB-gated tests skip without DATABASE_URL)
cd server && python3 -m pytest tests/ -v

# Frontend
cd client && npm run test:run          # or: npm run test:coverage
```
