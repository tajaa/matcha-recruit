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
git mv REPO_TIDY_PLAN.md docs/plans/             # this plan itself, once executed
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

---

# Part 2 — Root reorganization (navigable across products)

Extends the tidy into the layout the user already approved in `docs/plans/ROOT_CLEANUP_PLAN.md` (decisions captured there via Q&A: `platforms/` grouping, scripts into `scripts/`, `agent-ui` → `server/agent-ui`, gitignored `secrets/`, `samples/` bucket). Phases ordered least→most risky; stop after any phase and the repo stays coherent.

**Target root (~12 visible entries):**
```
client/  server/  scripts/  platforms/  deploy/  docs/  samples/  secrets/
CLAUDE.md  README.md  docker-compose.yml  skills-lock.json  (+ dotfiles)
```

### 5. Root README.md — human-facing navigation
Rewrite/extend root `README.md`: one-screen products map (same table as the assessment above, reader-oriented), where each product's FE/BE lives, how each is served (hey-matcha.com / gummfit.com host-routed / `/tellus/` path / desktop app), pointers to `docs/`, `deploy/nginx/README.md`, `docs/ops/DB_WORKFLOW.md`. Read existing README first; keep anything still true.

### 6. secrets/ + agent-ui nesting (touches scripts, not platforms)
```bash
mkdir -p secrets && echo "*" > secrets/.gitignore && touch secrets/.gitkeep
# .gitignore: add secrets/*  +  !secrets/.gitkeep  !secrets/.gitignore
mv client_secret_2_*.json secrets/    # untracked (gitignored) — plain mv
mv roonMT-arm.pem secrets/            # untracked — plain mv
git mv agent-ui server/agent-ui
```
- Update pem path in all referencing files — authoritative list via `grep -rln "roonMT-arm.pem" --exclude-dir=node_modules .` (~15: `scripts/{agent,agent-dev,backups,dev-remote,seed_prod}.sh`, `deploy/setup-db-instance.sh`, `desktop/Werk/run-prod.sh`, `update-ec2.sh`, `CLAUDE.md`, `server/CLAUDE.md`, `docs/soc/*`, deployment docs). Pattern: `PEM="$(git rev-parse --show-toplevel)/secrets/roonMT-arm.pem"`.
- `build-and-push.sh:560` `ui_dir="${SCRIPT_DIR}/agent-ui"` → `"${SCRIPT_DIR}/server/agent-ui"`; `scripts/agent-dev.sh:23` same.
- CLAUDE.md "Requires `roonMT-arm.pem` at repo root" → new path.

### 7. platforms/ + samples/ + daily-driver scripts (riskiest — Xcode gate)
**Gate:** `xcodebuild` BOTH projects from new paths BEFORE committing; if either fails, restore the platforms move and ship the rest.
```bash
mkdir -p platforms samples
git mv desktop platforms/desktop
git mv ios platforms/ios
mv deals samples/deals && mv resumes samples/resumes   # untracked — plain mv; update .gitignore entries
git mv build-and-push.sh scripts/build-and-push.sh
git mv update-ec2.sh scripts/update-ec2.sh
[ -f .landing-build-version ] && git mv .landing-build-version scripts/ || true
```
- Both moved scripts: introduce `REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"`, repoint `BACKEND_DIR`/`FRONTEND_DIR`/`AGENT_DIR`/ui_dir/version-file (exact old→new block in `docs/plans/ROOT_CLEANUP_PLAN.md` lines ~287–304).
- Grep `.github/workflows/` for `build-and-push.sh|update-ec2.sh` → update hits.
- Path sweep `desktop/Werk` → `platforms/desktop/Werk` in CLAUDE.md + docs/.
- Xcode verify: `xcodebuild -project platforms/desktop/Werk/Matcha.xcodeproj -scheme Werk -configuration Debug clean build` + `platforms/ios/MatchaTutor.xcodeproj -scheme MatchaTutor`.
- New daily invocation: `./scripts/build-and-push.sh --frontend-only && ./scripts/update-ec2.sh --matcha`.

## Verification (cumulative)
- `cd server && python3 -c "from app.main import app; print(len(app.routes))"` — app boots post-shim-removal
- `python3 -m pytest tests/infrastructure -q` — leads-agent test passes with new imports
- re-grep `from app.models|from app.routes|from app.services|\.services\.auth` under server/ → zero hits
- `for s in scripts/*.sh deploy/*.sh; do bash -n "$s" || echo "BROKEN: $s"; done`
- `./scripts/build-and-push.sh --no-push --frontend-only` — build dry-run from new path
- `cd client && npx tsc --noEmit --incremental false`
- Xcode: both projects build from `platforms/` paths
- `ls -1 | wc -l` at root → ~12
- Post-completion: update session memory files (deploy-ops, cappe) with new script paths
