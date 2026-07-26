# Core Routes Zoo

~40 routers, ~16,000 lines. Aggregated in `__init__.py` and mounted onto `core_router` at `/api`. Reorganized 2026-07-25 (previously 36 flat files with no grouping) — see `CORE_ROUTES_REORG_PLAN.md` at repo root for the full rationale.

Loose single-file routers no longer exist at top level; every module lives in either a **grouping folder** (`identity/`, `admin_tools/`, `billing/`, `documents/`, `content/`, `telemetry/`) or a **split-router package** (`auth/`, `admin/`, `chat/`, `compliance/`, `resources/`).

**Naming trap:** a grouping folder must not share a name with a top-level module in the same directory — in Python the package shadows the module, so the module silently becomes unimportable. Check for a same-named `.py` before adding a grouping folder or moving a module into one.

A split-router package is **one** router carved into submodules (`_shared.py` owns the `APIRouter()`; submodules imported for decorator side-effects). A grouping folder namespaces **several independent** routers, each still self-mounted + self-gated in the top `__init__.py`. Its `folder/__init__.py` only re-exports the members' routers under their historical `*_router` names, so the top aggregator's mount block is unchanged by the grouping.

## Router map (by domain)

| Router | Prefix(es) | Owns |
|---|---|---|
| `auth/` | `/auth` | Login/refresh/logout, Google OAuth, all `/register/*` flows, broker branding + invites, `/me` + profile, password/email change, admin candidate tooling, beta invites — **split-router package** (12 submodules, split 2026-07-25 from the 3,699-line `auth.py` monolith; see below) |
| `admin/` | `/admin` | Platform admin: brokers, companies, deal flow, invites, jurisdictions, platform settings, posters, products, research, schedule rules — **split-router package**. `jurisdictions` is itself a nested package (`admin/jurisdictions/`, 9 files, split from a 4,558-line monolith) — include order in its `__init__.py` is load-bearing (reproduces original route registration order). |
| `chat/` | `/chat` (+ `/ws/chat`) | AI chat CRUD + WebSocket — **split-router package** |
| `compliance/` | `/compliance` | Full compliance engine (3 gate tiers: `router`/`lite_router`/`shared_router`) — **split-router package** |
| `resources/` | `/resources` | Free-tier resources hub: checkout, lead-gen, lite add-ons, pins, state guides, upgrade — **split-router package** |
| `identity/` | (own prefixes) | Auth-adjacent surfaces: `sso`, `profile_resume`, `push`, `candidate_invite`, `investigation_invite` — **grouping folder** |
| `admin_tools/` | `/admin/*` | Admin-facing operational tools: `admin_onboarding`, `admin_compliance_pilot`, `scope_registry`, `legislative_tracker`, `ai_usage_admin`, `bulk_import`, `leads_agent` — **grouping folder** |
| `billing/` | (own prefixes) | Stripe webhook + pricing/products admin: `stripe_webhook`, `matcha_lite_pricing_admin`, `products` — **grouping folder** |
| `documents/` | (own prefixes) | Handbooks, policies, credentialing, signature links: `handbooks`, `policies`, `handbook_gap_analyzer`, `admin_handbook_references`, `public_signatures`, `public_employee_documents`, `credential_templates` — **grouping folder** |
| `content/` | (own prefixes) | Blog, news, newsletter, landing/media, SEO, marketing: `blog`, `hr_news`, `newsletter`, `landing_media`, `sitemap`, `expert_advice`, `posters`, `contact` — **grouping folder** |
| `telemetry/` | (own prefixes) | `client_errors`, `server_errors`, `traffic`, `usage` — **grouping folder** |

## `auth/` split-router package

Split from the pre-2026-07-25 `auth.py` monolith along route-group lines, not 1:1 with the endpoints table:

| File | Owns |
|---|---|
| `_shared.py` | imports, `router`, `logger`, `_json_object`/`_json_list`/`_table_exists`/`_column_exists`/`_upsert_business_headcount_profile` (multi-group helpers — `__all__`-gated since they're underscore-prefixed and every submodule does `from ._shared import *`) |
| `login.py` | login rate-limiting state + `/login`, `/refresh`, `/logout` |
| `google.py` | `/google` (Google OAuth) |
| `register_business.py` | `/register/business` + business-invite validation |
| `verify_email.py` | `/verify-email` (completes deferred business signup) |
| `register_users.py` | `/register/{admin,client,employee,candidate,individual}` |
| `broker.py` | broker branding + broker-client invites + broker terms acceptance |
| `test_accounts.py` | `/register/test-account` + the ~790-line demo-data seeder |
| `profile.py` | `/me`, `/profile`, `/avatar`, `/work-onboarded` |
| `credentials.py` | change password/email, forgot/reset password |
| `admin_candidates.py` | `/admin/candidates/*` (beta toggle, tokens, roles, sessions) |
| `beta.py` | `/beta-invite/{token}`, `/register/beta` |

Tests import two symbols by path (re-exported from `auth/__init__.py`): `_upsert_business_headcount_profile` and `get_broker_branding_runtime`. `tests/auth/test_auth_broker_branding.py` monkeypatches `get_connection` on `auth_routes.broker` (the submodule), not the package `__init__` — the function's `get_connection` reference is a `broker.py` module global, patching the parent package does nothing.

## Grouping folders (namespace only — not split-router packages)

Every moved file uses **absolute** imports (`from app.core.services.X import …`, `from app.database import …`, `from app.matcha.dependencies import …`) — no intra-folder relative imports. None of these members cross-import a sibling.

| Folder | Members (file → router) |
|---|---|
| `identity/` | `sso`→sso_router, `profile_resume`→profile_resume_router, `push`→push_router, `candidate_invite`→candidate_invite_router, `investigation_invite`→investigation_invite_router |
| `admin_tools/` | `admin_onboarding`→admin_onboarding_router, `admin_compliance_pilot`→compliance_pilot_router, `scope_registry`→scope_registry_router, `legislative_tracker`→legislative_tracker_router, `ai_usage_admin`→ai_usage_admin_router, `bulk_import`→bulk_import_router, `leads_agent`→leads_agent_router |
| `billing/` | `stripe_webhook`→stripe_webhook_router, `matcha_lite_pricing_admin`→matcha_lite_pricing_admin_router, `products`→products_public_router |
| `documents/` | `handbooks`→handbooks_router + handbooks_public_router, `policies`→policies_router, `handbook_gap_analyzer`→handbook_gap_analyzer_router, `admin_handbook_references`→admin_handbook_references_router, `public_signatures`→public_signatures_router, `public_employee_documents`→public_employee_documents_router, `credential_templates`→credential_templates_router |
| `content/` | `blog`→blog_router, `hr_news`→hr_news_router + hr_news_public_router, `newsletter`→newsletter_public_router + newsletter_admin_router, `landing_media`→landing_media_public_router + landing_media_admin_router, `sitemap`→sitemap_router, `expert_advice`→expert_advice_router, `posters`→posters_router, `contact`→contact_router |
| `telemetry/` | `client_errors`→client_errors_router, `server_errors`→server_errors_router, `traffic`→traffic_router, `usage`→usage_router |

`stripe_webhook` and `sitemap` are also imported directly by `app/main.py` (bypassing the `core_router` aggregator — Stripe dashboard needs `/api/webhooks/stripe` exactly, sitemap needs no `/api` prefix for crawlers). If you move either again, update `main.py`'s two direct imports.

## Mounting convention

Every router lands through `__init__.py` with three knobs:
```python
core_router.include_router(<name>_router, prefix="/<path>", tags=["<name>"],
                           dependencies=[Depends(require_feature("<flag>"))])
```
- `prefix` + gate live **at the mount**, not on the sub-router itself. Sub-routers use bare `APIRouter()`.
- Moving a module between folders never changes its mount line — only the `from .<folder> import <name>_router` line above it.

## Test layout

`server/tests/<domain>/` doesn't mirror this folder structure 1:1 — some tests import route modules directly by path for private helpers (module-level functions/constants, not routes). If you move a module between folders, `grep -rn "app.core.routes.<old_module_name>"` across `server/tests/` and fix both plain imports and string literals (`monkeypatch`/`patch` targets, `MOD = "..."` constants) — string literals don't show up in a normal import-checker pass.
