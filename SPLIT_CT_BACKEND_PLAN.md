# Split backend: matcha+espresso vs cappe+tellus (same EC2)

## Context

One FastAPI process (`app/main.py` → `matcha-backend` container, blue-green 8002/8003) currently serves all four products. Espresso is only a client of the matcha backend (`mw_*` tables), and cappe/tellus are already code-isolated (0 `cappe→matcha` edges; 1 documented `tellus→matcha` edge: `tellus/services/geo.py` → `matcha.services.property.property_cat.geocode`). Goal: two independently deployable backend stacks on the same EC2 — a matcha deploy never bounces cappe/tellus and vice versa. User chose **full split** (own container + own blue-green port pair + own deploy path).

Key facts discovered:
- `server/app/main.py` mounts everything: core/werk/matcha routers, `cappe_router` (/api/cappe), `tellus_router` (/api/tellus), `cappe_render_router` (host-routed `*.gummfit.com`), stripe webhook, WS routers. Cappe-specific pieces baked in: `DynamicTrustedHostMiddleware` custom-domain DB fallback, `*.gummfit.com` host allowlist entries, Merlin browser-pool shutdown in lifespan.
- Cappe/tellus need at runtime: DB pool, redis cache, notification manager, error reporter, usage flusher, celery *dispatch* (cappe `newsletter.py`). They do NOT need: werk channels-WS fanout, project-WS fanout, inactivity scheduler, mw/er crash-recovery sweeps.
- One backend image (`matcha-backend` ECR), CMD `uvicorn app.main:app --port 8002 --workers 2`. Blue-green script `scripts/deploy-backend-bluegreen.sh` clones volume mounts from the old container, health-gates on `/health`, rewrites `/etc/nginx/upstream/matcha-backend-active.conf`.
- nginx: `deploy/nginx/matcha.conf` defines upstreams `matcha_backend`/`matcha_frontend`; `cappe.conf` (gummfit.com) reuses them. Tellus FE is static files inside the matcha-frontend container at `/tellus/`; tellus API rides the `/api/` catch-all on hey-matcha.com. Cappe admin console (matcha SPA `pages/admin/Cappe.tsx`) calls `/api/cappe` from hey-matcha.com.
- Stripe: single webhook endpoint `hey-matcha.com/api/webhooks/stripe` handles ALL products incl. `tellus_brand` — stays on the matcha app; cross-product effects land via shared Postgres.
- Worker: celery tasks all live in `app/workers/`; `matcha-worker` stays single and serves both stacks (cappe newsletter task included). No change needed.

## Design

**Same Dockerfile / same ECR repo, two image tags, two app modules, two blue-green pairs.**

- `matcha-backend:latest` → `app.main:app` → containers `matcha-backend-8002/8003` (unchanged).
- `matcha-backend:ct-latest` → `app.main_ct:app` (cappe+tellus) → containers `matcha-ct-8004/8005`, host-published `127.0.0.1:8004/8005`, internal port stays 8002. Separate tag (not shared `:latest`) so redeploying CT never silently picks up untested matcha-side changes; same repo so zero ECR/IAM changes. Leaner: `--workers 1`, `--memory=384m`.
- CMD override at `docker run` selects the module — no Dockerfile fork.

### 1. Backend code split — `server/app/`

- New `server/app/app_common.py`: extract from `main.py` the shared, product-agnostic pieces — logging setup (request-id record factory, basicConfig, health-access filter), `_unwrap_excgroup`/`_format_exc_chain`, the three middleware bodies (`add_security_headers`, `track_api_usage`, `capture_errors`), the unhandled-exception handler, `_host_in_allowlist` + `DynamicTrustedHostMiddleware`, and shared lifespan steps (pool init, `install_error_logging`, redis cache + notification manager init/teardown, usage flusher). Parameterize what differs (CORS origins list, host allowlist, whether cappe custom-domain fallback is active).
- `server/app/main.py` (matcha+werk+core, serves matcha SPA + Espresso): imports from `app_common`; keeps `init_db()`, crash-recovery sweeps (er docs, mw research, channel_broadcasts), werk fanout subscribers, project-WS fanout, inactivity scheduler, all `/ws/*` routers, stripe webhook, sitemap. **Drops**: `cappe_router`, `tellus_router`, `cappe_render_router`, Merlin browser-pool shutdown, cappe custom-domain DB fallback (keep the static `*.gummfit.com` allowlist entries for one release as rollback cushion, then trim).
- New `server/app/main_ct.py` (cappe+tellus): mounts `cappe_router` at `/api/cappe`, `tellus_router` at `/api/tellus`, `cappe_render_router` at root, `/uploads` static, `/health` returning `{"service": "matcha-ct"}` (distinct name = sanity signal). Lifespan: shared steps only + Merlin browser-pool shutdown; **no** `init_db()` (matcha container owns bootstrap), no werk/mw machinery. Trusted hosts: gummfit apex/www/wildcard + hey-matcha (tellus + cappe-admin API calls arrive with that Host) + custom-domain DB fallback. CORS: gummfit + hey-matcha origins + localhost dev.
- Verify no other module-level `matcha`/`werk` imports leak into the CT import graph beyond the documented `geo.py` edge (it's fine — it imports a pure service module, no router/side effects).

### 2. Deploy scripts

- `scripts/deploy-backend-bluegreen.sh`: parameterize via env with defaults preserving current behavior — `BG_IMAGE_TAG` (latest|ct-latest), `BG_NAME_PREFIX` (matcha-backend|matcha-ct), `BG_PORT_A/BG_PORT_B` (8002/8003 | 8004/8005), `BG_ACTIVE_CONF`, `BG_NETWORK_ALIAS` (matcha-backend | none for CT), `BG_APP_MODULE` → CMD override, `BG_MEMORY`, `BG_WORKERS`. First-run bootstrap for CT: no old CT container exists, so allow cloning uploads-volume/credentials mounts from the live matcha backend container instead of failing.
- `scripts/build-and-push.sh`: after backend image build, also `docker tag` → `matcha-backend:ct-latest` + push (same bytes, push is instant — layers dedup). New `--ct-only` narrows to tag+push of ct-latest (still requires a backend build or reuses last local build).
- `scripts/update-ec2.sh`: new `--ct` target → seed `/etc/nginx/upstream/matcha-ct-backend-active.conf` (default `server 127.0.0.1:8004;`), scp + run the parameterized bluegreen script with CT env. `--matcha` no longer implies CT; CT deploys are explicit. `--status` unchanged (docker ps shows all).
- `.github/workflows/deploy.yml`: add `ct` target choice wired to the same flags.
- `scripts/logs.sh`: add `ct` target resolving the 8004/8005 suffix.

### 3. nginx (`deploy/nginx/`, applied via scp per its README)

- `matcha.conf`: add `upstream matcha_ct_backend { include /etc/nginx/upstream/matcha-ct-backend-active.conf; }`. Add `location ^~ /api/tellus/` and `location ^~ /api/cappe/` → `matcha_ct_backend` (before the `/api/` catch-all) — tellus app + cappe admin console both call from hey-matcha.com.
- `cappe.conf`: repoint the two `/api/` blocks and the `*.gummfit.com` renderer block from `matcha_backend` → `matcha_ct_backend`. Never hardcode ports (standing rule).

### 4. Frontend + worker — no change now

- Frontend container keeps serving matcha SPA + cappe pages + tellus static app; frontend deploys were already independent of backend. Splitting the frontend image is a possible later step, not part of this.
- `matcha-worker` stays single, deploys with `--backend`/`--matcha` as today. CT container only *dispatches* celery tasks over redis.
- Stripe webhook stays on the matcha app (single dashboard endpoint); tellus/cappe billing effects flow through shared Postgres.

### Rollout order (safe, reversible)

1. Land code: `app_common.py`, `main_ct.py`, trimmed `main.py`, script + nginx + workflow changes. Run `python3 -m py_compile` (hook does it) + backend tests.
2. `./scripts/build-and-push.sh --backend-only` (pushes both `:latest` and `:ct-latest`).
3. `./scripts/update-ec2.sh --ct` — first CT pair comes up on 8004; upstream conf seeded; health-gated.
4. Apply updated `matcha.conf` + `cappe.conf` per `deploy/nginx/README.md`; `nginx -t && reload`. From this instant cappe/tellus traffic hits the CT container.
5. `./scripts/update-ec2.sh --backend` — matcha pair swaps to the trimmed image (cappe/tellus routes now 404 there, which nginx no longer routes to it anyway).
6. Rollback at any point before step 5 = revert the two nginx confs (old matcha image still serves everything). After step 5, rollback = redeploy previous `:latest`.

### Memory budget (measured on the EC2, 2026-08-06)

Box: 2 vCPU (Neoverse-N1, t4g.small class), **1.8Gi RAM**, 2G swap (204M used), 16G disk (7.4G free). Measured steady-state: matcha-backend 735MiB (2 uvicorn workers × ~360MB), worker 85M, redis 6.5M, frontend 11M, livekit 20M, host overhead ~200M → **~524Mi available**.

Decisions:
- CT container: **1 uvicorn worker, `--memory=384m`**. Its trimmed import graph (no matcha/werk services) should land ~250–330MB resident; matcha's trim (drops cappe/tellus imports) claws back a bit per worker.
- Blue-green overlap windows already lean on swap today (735M×2 during a matcha swap); CT's own overlap is only ~2×330M. **Never deploy matcha and CT simultaneously** — document in update-ec2.sh help text.
- No instance upgrade now. Revisit t4g.medium only if swap thrashing appears (watch `swapon --show` / CloudWatch after rollout).

## Files touched

- `server/app/app_common.py` (new), `server/app/main_ct.py` (new), `server/app/main.py` (trim + import from common)
- `scripts/deploy-backend-bluegreen.sh`, `scripts/build-and-push.sh`, `scripts/update-ec2.sh`, `scripts/logs.sh`
- `deploy/nginx/matcha.conf`, `deploy/nginx/cappe.conf`
- `.github/workflows/deploy.yml`
- `CLAUDE.md` blue-green/deploy notes (port table gains 8004/8005 pair)

## Verification

- Local: `PORT=8006 UVICORN_RELOAD=false python -c "import uvicorn; uvicorn.run('app.main_ct:app', port=8006)"` → `curl :8006/health` (`matcha-ct`), `curl :8006/api/tellus/...` public endpoint, confirm `/api/ir/...` 404s there; matcha app on :8001 still serves `/api/auth/*` and 404s `/api/cappe/*` (after trim).
- `cd server && python3 -m pytest tests/ -v` — existing suites; any test importing `app.main` keeps working (module path unchanged).
- `cd client && npx tsc -p tsconfig.app.json --noEmit` only if client touched (it isn't).
- Prod smoke after rollout: gummfit.com loads + a tenant subdomain renders; hey-matcha.com/tellus/ loads + tellus login works; Espresso connects; matcha login works; `./scripts/logs.sh ct` shows traffic.
