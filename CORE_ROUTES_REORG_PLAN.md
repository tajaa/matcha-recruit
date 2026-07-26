# Reorganize `server/app/core/routes/`

## Context

`core/routes/` is 36 flat files (~16k lines) + 4 subpackages (`admin/`, `chat/`, `compliance/`, `resources/`) with no organization — hard to navigate, unrelated domains interleaved. `auth.py` alone is 3,699 lines. Goal: domain grouping folders using the repo's two documented idioms (from `server/app/matcha/routes/CLAUDE.md` + the b969858 services-split precedent), plus carve `auth.py` into a split-router package. Follow-up phase: audit core↔matcha overlap for misplaced modules.

Precedent rules (must follow):
- **Rewrite call sites, no shims** (b969858 / `SERVICES_REORG.md` at repo root — read it; its regex-miss gotchas apply verbatim here).
- **Grouping folder** = several independent routers; folder `__init__.py` re-exports each router under its historical `*_router` name so the top aggregator's mount block is unchanged. Absolute imports inside.
- **Split-router package** = one router carved up; `_shared.py` owns the `APIRouter()`, submodules imported for decorator side-effects (see `core/routes/resources/__init__.py`).
- **Name-shadowing trap**: a new folder must not share a name with a surviving top-level `.py` in the same dir.
- Existing 4 subpackages: untouched.

## Target layout

```
core/routes/
├── __init__.py       aggregator — import lines updated, mount block byte-identical
├── admin/ chat/ compliance/ resources/    (existing, untouched)
├── auth/             NEW split-router package (auth.py carved up — see below)
├── identity/         grouping: sso, profile_resume, push, candidate_invite, investigation_invite
├── admin_tools/      grouping: admin_onboarding, admin_compliance_pilot, scope_registry,
│                     legislative_tracker, ai_usage_admin, bulk_import, leads_agent
├── billing/          grouping: stripe_webhook, matcha_lite_pricing_admin, products
├── documents/        grouping: handbooks, policies, handbook_gap_analyzer,
│                     admin_handbook_references, public_signatures,
│                     public_employee_documents, credential_templates
├── content/          grouping: blog, hr_news, newsletter, landing_media, sitemap,
│                     expert_advice, posters, contact
└── telemetry/        grouping: client_errors, server_errors, traffic, usage
```

All 35 flat modules accounted for (auth.py = the package; other 34 across 6 grouping folders). Folder names collide with nothing. Use `git mv` to preserve history. Modules inside grouping folders are unchanged internally (already absolute imports at module level per server/CLAUDE.md).

Multi-router modules — grouping `__init__.py` must re-export ALL router objects: `handbooks` (`router` + `public_router`), `hr_news` (`router` + `public_router`), `newsletter` (`public_router` + `admin_router`), `landing_media` (`public_router` + `admin_router`), `compliance` untouched.

## auth.py → `core/routes/auth/` split-router package

Single `APIRouter()` (line 47) mounted at `/auth`. Split (line ranges from exploration):

| File | Contents |
|---|---|
| `_shared.py` | top-of-file imports, `router = APIRouter()`, `logger`, `_json_object`, `_json_list`, `_table_exists`, `_column_exists`, `_upsert_business_headcount_profile` (multi-group + test-imported) |
| `login.py` | `_LOGIN_*` consts + `_login_attempts` dict + `_check_login_rate_limit`, `_touch_user_last_login`, `login`, `refresh_token`, `logout` — **the `_login_attempts` defaultdict is in-process rate-limit state; must live in exactly one module (here), never duplicated** |
| `google.py` | `GoogleAuthRequest` + `google_auth` (keep google libs lazy) |
| `register_business.py` | `register_business` (1598–2216), `validate_business_invite`, `get_client_invite_info` |
| `verify_email.py` | `EmailVerifyRequest` + `verify_email` |
| `register_users.py` | `register_admin`, `register_client`, `register_employee`, `register_candidate`, `IndividualRegister` + `register_individual` |
| `broker.py` | `BROKER_BRANDING_KEY_RE`, `get_broker_branding_runtime`, `validate_broker_client_invite`, `accept_broker_client_invite`, `accept_broker_terms` |
| `test_accounts.py` | `TEST_ACCOUNT_FEATURES`, `_split_name`, `_seed_test_account_data` (~790 lines), `register_test_account` |
| `profile.py` | `get_current_user_profile` (`/me`), `update_profile`, `_AVATAR_*` + `upload_avatar`, `mark_work_onboarded` |
| `credentials.py` | `change_password`, `change_email`, `ForgotPasswordRequest`/`ResetPasswordRequest`, `_validate_password_strength`, `forgot_password`, `reset_password` |
| `admin_candidates.py` | five `/admin/candidates*` routes |
| `beta.py` | `BetaRegisterRequest`, `validate_beta_invite`, `register_beta` |
| `__init__.py` | `from ._shared import router`; side-effect import every submodule; re-export `_upsert_business_headcount_profile` + `get_broker_branding_runtime` for tests |

Split rules: submodules start `from app.core.routes.auth._shared import *` (resources/ pattern); single-group helpers move with their group; drop the redundant shadowing lazy re-imports (`get_settings` at 2945/3023, `DEFAULT_COMPANY_FEATURES` at 3487/3569/3637) — they're no-ops; keep genuinely lazy imports (email service, `FREE_TOKEN_GRANT`, `werk.routes.channels_ws.manager`, google oauth libs) lazy.

## Import rewrites (complete list — exploration found no others)

Production (3 sites):
- `server/app/main.py:530` → `from .core.routes.billing.stripe_webhook import router as stripe_webhook_router`
- `server/app/main.py:562` → `from .core.routes.content.sitemap import router as sitemap_router`
- `server/app/main.py:528` (`from .core.routes import core_router, chat_ws_router`) — unchanged
- `server/app/matcha/dependencies.py:440` lazy `from ..core.routes.admin import KNOWN_PLATFORM_ITEMS` — unchanged (admin/ untouched)

`core/routes/__init__.py`: update only the import lines (e.g. `from .telemetry import usage_router, traffic_router, ...`); mount block + gates byte-identical. Dead `__all__` back-compat list: drop.

Tests (the real churn — 8 files need edits; string literals are the trap):
- `tests/auth/test_auth_registration.py` — `from app.core.routes import auth as auth_routes` still works via `__init__` re-export; no change needed.
- `tests/auth/test_auth_broker_branding.py` — `monkeypatch.setattr(auth_routes, "get_connection", ...)` must become patches on `app.core.routes.auth.broker` (the submodule whose global the function closes over). ~4 lines (32, 38, 44, 77).
- `tests/paid_channels/test_paid_channels.py` — imports of `routes.stripe_webhook` + **3 string patch targets** `"app.core.routes.stripe_webhook.get_connection"` → `app.core.routes.billing.stripe_webhook...`.
- `tests/test_matcha_lite_pricing_admin.py` — `MOD = "app.core.routes.matcha_lite_pricing_admin"` string → `app.core.routes.billing.matcha_lite_pricing_admin`.
- `tests/handbook_audit/test_audit_report_html.py` — `routes.handbook_gap_analyzer` → `routes.documents.handbook_gap_analyzer`.
- `tests/ir_incidents/test_review_fixes.py` — `routes.investigation_invite` → `routes.identity.investigation_invite`.
- `tests/scope_registry/test_dispatch_worker_health.py` — `routes.scope_registry` → `routes.admin_tools.scope_registry` (module alias `sr`, monkeypatches module attrs — alias keeps working once import path fixed).
- `tests/compliance/*`, `tests/*/test_*jurisdiction*`, broker-transition tests — target untouched packages; no change.

Implementation checkpoint: `server/app/core/services/ai_usage.py` derives cost labels from caller `__name__` with a positional segment strip keyed on `app.matcha.services.` (see `SERVICES_REORG.md`). Check whether moved AI-calling route modules (`handbook_gap_analyzer`, `leads_agent`, `expert_advice`, `blog`, `hr_news`) feed it; if labels shift, apply the same positional fix so labels stay byte-identical.

## Docs

- Add `server/app/core/routes/CLAUDE.md` — index of the zoo, mirroring `matcha/routes/CLAUDE.md` (folder map, grouping-vs-split idiom note, name-shadow warning).
- Root `CLAUDE.md` Symbol Map: update `stripe_webhook.py` path, `resources.py` (already stale) — sweep for `core/routes/` path refs.

## Phase 2 (after reorg lands): core↔matcha overlap audit — REPORT ONLY

Sweep `server/app/matcha/routes/` + `matcha/services/` vs `core/` for misplaced modules; deliver findings + proposed moves for approval, move nothing. Known candidates spotted already:
- `matcha/routes/billing.py` (Stripe checkout for matcha-work) vs new `core/routes/billing/` — two Stripe surfaces in two apps.
- `matcha/routes/companies.py` vs `core/routes/admin/companies.py`.
- `core/routes/documents/credential_templates.py` vs matcha employees credentialing.
- General rule from repo layout: cross-product shared infra belongs in `core/` (cappe/tellus import only `app/core/*`).

## Verification

1. Hook runs `py_compile` per edit; additionally `cd server && python3 -m compileall -q app/core/routes`.
2. `cd server && python3 -c "import app.main"` — import chain intact.
3. **Route-table parity**: before starting, dump `sorted((r.path, tuple(sorted(r.methods or []))) for r in app.routes)` (incl. sub-apps via `app.router`) to scratchpad; after, diff must be empty. This proves mount block + prefixes + gates unchanged.
4. `cd server && python3 -m pytest tests/ -q` — failure set must match pre-reorg baseline (record baseline first; known pre-existing collection failures listed in server/CLAUDE.md).
5. Leftover sweep: `grep -rn` for each moved module's old dotted path (`core.routes.auth` handled specially — package keeps the name; grep the other 34) across `server/`, `docs/`, `CLAUDE.md`, incl. string literals.

Git: stay on current branch (main) per user rule — no branch creation. Leave uncommitted for review (services-split precedent), summary at end.
