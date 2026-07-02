# Repo structure: assessment + minimal tidy plan

Written 2026-07-02. Answers: "does our folder structure make sense for all our products, or is it convoluted?"

## Assessment

**Verdict: coherent underneath, cluttered on top.** Product boundaries are genuinely clean:

| Product | Frontend | Backend | Isolation |
|---|---|---|---|
| Matcha (+ Lite/Essentials/X/Compliance/Free tiers) | `client/` main SPA | `server/app/{core,matcha}` `/api` | `companies.signup_source` + feature flags — tiers are config, not code forks (correct design) |
| Matcha-work web + Werk desktop | `client/src/pages/work` + `desktop/Werk` | shared `matcha_work.py` | `mw_*` tables; `/work` vs `/werk` route trees = deliberate two-surface split |
| Werk-lite (slack-style) | inside `pages/work/*` at `/werk-lite` | same channels backend | feature flag `werk_lite` |
| Cappe (gummfit.com) | inside `client/` — host-routed (`cappeHost.ts`) | `server/app/cappe` `/api/cappe` | own `cappe_accounts`, JWT `scope=cappe`, `cappe_*` tables |
| Tellus | `client/tellus/` separate Vite app | `server/app/tellus` `/api/tellus` | own `tellus_accounts`, `scope=tellus`, `tellus_*` tables |
| Ops agent | `agent-ui/` (Preact) | `server/agent/` standalone | own service :9100 |
| MatchaTutor | `ios/` | matcha endpoints | dormant since Feb |

Backend: package + router-prefix + JWT-scope + table-prefix per product, all sharing one core kernel and one Postgres. A sane monolith-monorepo — **not** worth splitting.

**What IS convoluted:**
1. ~15 one-off planning MDs littering repo root
2. Dead deprecated shim dirs `server/app/{models,routes,services}` (app root, not core/matcha)
3. Orphan `client/server/`, stale root `memory/`, empty root `package-lock.json`, 127MB untracked `DerivedData/`
4. Nothing documents the product→path map — every new session re-derives it

**Deliberately NOT touching:** npm-workspace unification, moving cappe/tellus packages, `/work`-`/werk` dedupe (intentional split), tellus→`property_cat.geocode` import (documented single-geocoder reuse), per-filename .gitignore scratch entries (load-bearing — currently ignoring real untracked files in docs/analysis/), `deals/`/`resumes/`/pem/client_secret (untracked by design), `orm/`, gummfit dead-reference contract.

## Changes (4 commits, risk-ordered)

### 0. Local-only (no commit)
```bash
rm -rf DerivedData
```

### 1. Zero-risk tracked deletes
```bash
git rm package-lock.json        # 93-byte empty stub; no root package.json; CI is Docker-only
git rm -r client/server         # orphan: one empty __init__.py, committed by accident (eac1259)
git rm -r memory                # one stale April session note; superseded
```

### 2. Root MDs → docs/ (15 files, 2 reference edits)
Reference-swept: only `CLAUDE_CODE_PLAN.md` has live refs.
```bash
git mv AGENTIC_UPGRADES_PLAN.md BROKER_AB_COMPLETION_PLAN.md LABOR_RELATIONS_PLAN.md \
       WORKFORCE_COMPLIANCE_PLAN.md osha-intake-forms.md CLAUDE_CODE_PLAN.md docs/plans/
git mv BROKER_MARKET_THESIS_GAP_ANALYSIS.md CASUALTY_COVERAGE.md docs/broker/
git mv HRIS_VENDOR_RECOMMENDATION.md finch_hris.md hris_connection.md docs/hris/
git mv MID_TIER_PROPOSAL.md LITE_BROKER_PRICING_BANDS.md LITE_BROKER_PRICING_BANDS.html docs/sales/
mv LITE_BROKER_PRICING_BANDS.pdf docs/sales/     # untracked pdf, keep set together
git mv WC_STATE_RATES_2026_RESEARCH.md docs/references/
```
Edits: `CLAUDE.md:427` "at the repo root" → `docs/plans/CLAUDE_CODE_PLAN.md`; same rename in `server/app/matcha/routes/CLAUDE.md:70`.

### 3. Dead shim removal — fix 3 live imports FIRST
1. `server/app/database.py:4785`: `from .services.auth import hash_password` → `from .core.services.auth import hash_password` (**runtime path** — fresh-DB admin bootstrap)
2. `server/tests/infrastructure/test_leads_agent_logic.py:13-14` → `app.core.models.leads_agent` / `app.core.services.leads_agent`
3. `server/scripts/seed_gumfit_admin.py:11` → `from app.core.services.auth import hash_password` (keep-working collateral, not gummfit cleanup)

Then:
```bash
git rm -r server/app/models server/app/routes server/app/services
rm -rf server/app/models server/app/routes server/app/services   # stray __pycache__
```
Plus: remove stale `services/` line from `server/CLAUDE.md` layout tree.

### 4. Conventions
- `.gitignore`: append `/scratch/` + comment ("throwaway notes go in scratch/, not new per-filename entries"). Existing entries untouched.
- `CLAUDE.md`: new **"Repo layout — products map"** section (the assessment table above, plus cross-product import rule: cappe/tellus import only `app/core/*`; documented exception `tellus/services/geo.py` → `matcha.services.property_cat.geocode`). Insert after "### Auxiliary surfaces".

## Verification
- `cd server && python3 -c "from app.main import app; print(len(app.routes))"` — app boots post-shim-removal
- `python3 -m pytest tests/infrastructure -q` — leads-agent test passes with new imports
- re-grep `from app.models|from app.routes|from app.services|\.services\.auth` under server/ → zero hits
- `git status` clean root: only expected dirs + CLAUDE.md/README/compose/build scripts remain at top level
