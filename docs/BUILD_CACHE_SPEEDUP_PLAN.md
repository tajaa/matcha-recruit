# Speed up local `build-and-push.sh` on Mac

## Context

`./build-and-push.sh && ./update-ec2.sh --matcha` feels slow; suspicion was that Docker cache isn't being used. Investigation findings:

**Cache IS working** — Dockerfiles are correctly layered (deps installed before `COPY . .`), builder is Docker Desktop with containerd snapshotter (cache export supported), platform is native arm64 on Apple Silicon (no emulation). Local BuildKit layer cache hits on unchanged stages.

**The real per-build overhead is the registry cache round-trip**, which only exists to warm CI/other-machine builds:

1. `--cache-to type=registry,mode=max` (`scripts/build-and-push.sh:432`) runs on **every local push build**, for both images. `mode=max` exports *all* intermediate stages (backend `dependencies` stage = full site-packages, ~1GB+) to ECR every run — upload-bandwidth-bound, pure overhead when building on the same Mac every time (local cache already has everything).
2. `--cache-from` registry reads (lines 420–421) pull cache manifests/layers from ECR — redundant when the local cache is warm.
3. `BUILDKIT_INLINE_CACHE=1` build-arg (line 396) is dead weight (inline cache only matters without explicit `--cache-to`; neither Dockerfile uses it).
4. Minor: backend build context includes `agent-ui/node_modules` (65MB) and `uploads/` (24MB) — not in `server/.dockerignore`.

CI relevance: `.github/workflows/deploy.yml` runs the same script on a cold GitHub runner — registry cache **is** valuable there. So gate it, don't delete it.

## Changes

All in `scripts/build-and-push.sh` + `server/.dockerignore`:

1. **Gate registry cache to CI / opt-in** (`build_image`, lines ~404–437):
   - New flag `--registry-cache` (default off locally); auto-enable when `GITHUB_ACTIONS=true` or `CI=true`.
   - When off (typical Mac run): no `--cache-from`/`--cache-to` — rely on local BuildKit cache. When on (CI): keep current behavior exactly (cache-from buildcache + branch tag, cache-to mode=max zstd).
   - Update usage text.

2. **Drop `BUILDKIT_INLINE_CACHE=1`** build-arg (line 396).

3. **`server/.dockerignore` additions**:
   ```
   agent-ui/node_modules/
   agent-ui/dist/
   uploads/
   ```
   (`agent/static/` stays — runtime asset. `uploads/` is the local temp dir, never needed in image.)

No Dockerfile changes. No `update-ec2.sh` changes (its time is ECR→EC2 pull + blue-green swap, network-bound, out of scope).

## Verification

1. `./scripts/build-and-push.sh --backend-only --no-push` twice in a row — second run should complete in seconds (all layers `CACHED`).
2. Normal `./scripts/build-and-push.sh` — confirm log no longer shows "Cache write: buildcache" locally, build+push wall-time drops (no mode=max upload phase).
3. `./scripts/build-and-push.sh --backend-only --no-push --registry-cache` — confirm cache flags reappear in the docker command (CI path intact).
4. `bash -n scripts/build-and-push.sh` for syntax.

## Expected outcome

Local runs skip the multi-hundred-MB→GB cache upload to ECR each build; only real image layers that changed get pushed. CI keeps warm-start cache.
