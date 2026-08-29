# Docker disk reclamation + msandbox image GC

**Status: done, 2026-08-29.** Durable reference lives in
`docs/ops/AGENT_SANDBOX.md` § "Disk reclamation (`msandbox gc`)". This file is
the record of what was wrong and what shipped.

## The problem

Host disk was at **97% (15GB free of 460GB)**; `Docker.raw` was **68GB**.

1. **No image GC existed.** Every workspace build is content-addressed
   (`docker_runtime.build_identifier`) over the Dockerfile, the dockerignore,
   the entrypoint, and seven lockfiles. Any edit mints a new multi-GB image and
   strands the old one; the four `matcha-ms-deps-*` volumes key off the same
   identifier and rotate with it. Nothing in the controller ever deleted either.
2. **The image was 22% pure waste** — a trailing `chown -R /opt/bootstrap`
   rewrote 1.65GB of baked node_modules and venv into a duplicate 1.69GB layer,
   for no observable effect: `entrypoint.sh` chowns the *destination* after
   rsync and reads `.dependencies-sha` as root before `gosu agent`.
3. **Build cache sat at its own 24GB ceiling** (`~/.docker/daemon.json`).

Every content-addressed artifact on the box turned out to be dead: zero session
records existed, and recomputing the identifier across the repo plus both
installed releases × `playwright ∈ {False, True}` produced six tags, none of
which matched the `2f17fab940b712d1a0cb` on disk.

## Results

| | Before | After |
|---|---|---|
| `Docker.raw` | 68G | **35G** |
| Host free | 15GB (97% full) | **50GB (89%)** |
| Images | 26 | 5 |
| Volumes | 57 (8.8GB) | 16 (4.4GB, 0B reclaimable) |
| Build cache | 25.4GB | 8.4GB |
| Sandbox image | 7.4GB | **5.28GB** |

## What shipped

**`msandbox gc [--apply]`** — new `scripts/msandbox/docker_gc.py`, wired into
`cli.py`, `agent-sandbox.sh`, and the installed launcher. Dry-run by default
like `worktree gc`. Sweeps unreachable images, `matcha-ms-*` volumes, stopped
`matcha-ms-*` containers, and orphaned `build-contexts/` + `homes/` dirs. Runs
automatically after each successful build (`MSANDBOX_SKIP_GC=1` opts out).

Reachability is conservative by design:

- `:latest` is never collected — not content-addressed, and both the legacy and
  AutoPR lanes run it.
- The four non-session compose projects are protected by name. They have no
  `SessionRecord`, and `matcha-agent-sandbox_sandbox_home` holds every agent
  login.
- **Every installed release** contributes tags, because `install --rollback`
  can activate any of them. Missing this would have deleted a rollback target.
- Dependency volumes match by recomputed name, never by Compose label — a
  shared content-addressed volume keeps the label of whichever project created
  it first.
- If any live session's build inputs are unreadable, GC collects nothing.

**Dockerfile slim** — the four bootstrap `COPY`s take `--chown=`; the trailing
recursive chown became a two-path non-recursive one. Verified: ownership is
`501:20` identically top-to-bottom, the entrypoint's rsync-into-volume path
still works, and the venv `activate` path rewrite still applies.

**Refactor** — `_materialize_build_context` split into `build_context_sources` +
a pure `build_identifier`, so GC can compute candidate tags without
materializing a context directory for each one.

**Tests** — 6 new cases in `scripts/tests/test_msandbox_v2.py` (36 pass), plus
the 14-case lifecycle suite. They cover the protected lanes surviving with zero
session records, the per-release rollback tags, the shared-label hazard, and GC
refusing to act on incomplete reachability.

## Two traps found the hard way

- **`docker builder prune --max-used-space` can corrupt a `type=cache` mount**
  by evicting part of it, and the next build dies on
  `E: LZ4F: ..._Packages.lz4 Unexpected end of file`. Drop cache mounts
  wholesale first (`--filter type=exec.cachemount`), then LRU-trim the rest.
- **`docker-compose.sandbox.yml` has no `restart:` policy**, and
  `dispatch-if-idle.sh` gates AutoPR on a *running* container labelled
  `com.docker.compose.project=matcha-agent-sandbox`. After any Docker restart,
  run `msandbox` or AutoPR silently stops dispatching.

## Remaining

`~/.docker/daemon.json` now sets `defaultKeepStorage: "8GB"` (was 24GB), but the
running daemon still holds the old policy — it takes effect on the next Docker
Desktop restart. The cache is already trimmed to 8.4GB by hand, so this only
governs future automatic GC.

The sandbox containers are currently stopped; `msandbox` restarts them together
with the AutoPR control plane.

Not done: `build-and-push.sh` still never `rmi`s locally, so ECR tags accumulate
at ~100MB per frontend deploy (19 had built up, ~5.6GB, now cleared).
