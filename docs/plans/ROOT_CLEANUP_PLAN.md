# Repo root cleanup — bucket non-essentials into subfolders

## Context

Root has 30+ entries today: 12 stale-feeling `*_PLAN.md` files, 3
sample-data directories, an orphan `package-lock.json`, an SSH
private key, a Google OAuth secret, two daily-driver shell scripts,
and several legitimate top-level folders mixed together. Hard to
scan, easy to misplace new work.

User wants root to hold only the essentials. Allow-list per their
brief: `client/`, `server/`, `scripts/`, `CLAUDE.md`, `desktop/`
(originally), `.gitignore` / `.dockerignore`, docker files. Plus
folders like `.git/` / `.github/` / `.claude/` that MUST live at
root for tooling.

User decisions captured (from AskUserQuestion):
- Move `build-and-push.sh` + `update-ec2.sh` + `.landing-build-version`
  into `scripts/`.
- Group `desktop/` + `ios/` under `platforms/`.
- Move `agent-ui/` into `server/agent-ui/`.
- Delete orphan `package-lock.json` (no root `package.json`).
- Move `client_secret_*_apps.json` to `secrets/` (don't delete —
  may be needed for manual OAuth setup).

## Target root layout

```
matcha/
├── client/                    (unchanged)
├── server/
│   └── agent-ui/              ← moved from root
├── scripts/
│   ├── build-and-push.sh      ← moved from root
│   ├── update-ec2.sh          ← moved from root
│   ├── .landing-build-version ← moved from root (written by build script)
│   └── ... (existing)
├── platforms/                 ← new
│   ├── desktop/               ← moved from root
│   └── ios/                   ← moved from root
├── deploy/                    (unchanged — IaC + setup)
├── docs/
│   ├── plans/                 ← new bucket for *_PLAN.md
│   ├── audits/                ← new bucket for audit / smoke output docs
│   ├── compliance/            ← new bucket (BEHAVIORAL_HEALTH_*)
│   └── ... (existing)
├── samples/                   ← new
│   ├── deals/                 ← moved from root
│   └── resumes/               ← moved from root
├── secrets/                   ← new, gitignored
│   ├── roonMT-arm.pem         ← moved from root
│   └── client_secret_*.json   ← moved from root
├── CLAUDE.md                  (unchanged)
├── README.md                  (unchanged)
├── docker-compose.yml         (unchanged)
├── .env.production.example    (unchanged)
├── .gitignore / .dockerignore / .claudeignore  (unchanged)
├── skills-lock.json           (Claude Code managed)
├── .github/                   (GitHub requirement)
├── .claude/                   (Claude Code requirement)
│   ├── HARNESS.md             ← moved from root
│   └── memory/                ← moved from root
└── .agents/                   (Claude Code requirement)
```

Net root contents after migration: 6 directories (`client`, `server`,
`scripts`, `platforms`, `deploy`, `docs`, `samples`, `secrets`) +
4 config files + standard ignore files + tooling-required hidden
folders. Down from 30+ to ~12 visible entries.

## Three-phase rollout

Phases are ordered **least-likely-to-break-prod → most**. Each phase
ships as its own push-to-prod cycle so a regression is isolated.

---

### Phase 1 — Cosmetic moves (zero runtime impact)

Pure file relocations that no scripts, CI, or runtime code touch.
If this phase breaks anything, it's a stale link in docs — recoverable
without prod intervention.

**Moves:**

```bash
# Sample data → samples/
mkdir -p samples
git mv deals samples/deals
git mv resumes samples/resumes

# Markdown plans + audits + compliance docs → docs/
mkdir -p docs/plans docs/audits docs/compliance
git mv ADMIN_ONBOARDING_WIZARD_PLAN.md docs/plans/
git mv CLAUDE_CODE_PLAN.md docs/plans/
git mv EEOC_COMPLAINT_FEATURE_OPTIONS.md docs/plans/
git mv EEOC_POSITION_STATEMENT_PLAN.md docs/plans/
git mv EMPLOYEES_REFACTOR_PLAN.md docs/plans/
git mv IR_INCIDENTS_SPLIT_PLAN.md docs/plans/
git mv MACOS_PARITY_PLAN.md docs/plans/
git mv MENTION_EMAIL_PLAN.md docs/plans/
git mv QSR_RETENTION_PLAN.md docs/plans/
git mv MACOS_SWIFT_GAP_AUDIT.md docs/audits/
git mv HANDBOOK_AUDIT_SMOKE_OUTPUT.md docs/audits/
git mv BEHAVIORAL_HEALTH_CREDENTIAL_REQUIREMENTS.md docs/compliance/

# Claude harness docs + memory → .claude/
git mv HARNESS.md .claude/HARNESS.md
mkdir -p .claude/memory
git mv memory/project_inbox_status.md .claude/memory/project_inbox_status.md
rmdir memory

# Orphan deletion
git rm package-lock.json
```

**Reference sweep** (only doc-level, no script changes needed):
- Any `git grep "HANDBOOK_AUDIT_SMOKE_OUTPUT.md"` → update to
  `docs/audits/HANDBOOK_AUDIT_SMOKE_OUTPUT.md`. Mostly inside
  `server/tests/handbook_audit/test_handbook_audit_service.py`
  docstring.
- Sweep CLAUDE.md (root) for `deals/`, `resumes/`, `HARNESS.md`,
  `memory/` mentions. Update paths where present.

**Verify:**
```bash
cd server && ./venv/bin/python -m pytest tests/ -q
cd client && npx tsc --noEmit
ls -1 | grep -E '^(deals|resumes|memory|HARNESS|.*_PLAN|package-lock)' && echo "LEFTOVER" || echo "clean"
```

**Phase 1 commits:**
1. `chore(root): bucket samples + plans + audits under samples/ + docs/`
2. `chore(root): move HARNESS + memory under .claude/, delete orphan package-lock.json`

**Push to prod**. Nothing runtime touches these paths.

---

### Phase 2 — Secret hygiene + agent-ui nesting (touches scripts, not platforms)

Moves the SSH key + OAuth secret out of root, and nests `agent-ui/`
inside `server/` where its build target lives. Both require script /
docs edits. No Xcode involvement. No CI workflow path changes.

**Moves:**

```bash
# Secrets bucket (gitignored)
mkdir -p secrets
echo "*" > secrets/.gitignore       # gitignore EVERYTHING inside
touch secrets/.gitkeep              # keep the dir tracked
echo "secrets/*" >> .gitignore      # defense in depth
# (re-allow .gitkeep so the dir persists in git)
echo "!secrets/.gitkeep" >> .gitignore
echo "!secrets/.gitignore" >> .gitignore

git mv client_secret_2_*.json secrets/
git mv roonMT-arm.pem secrets/roonMT-arm.pem

# agent-ui → server/agent-ui
git mv agent-ui server/agent-ui
```

**Reference updates — 15 files reference `roonMT-arm.pem`. Pattern:**

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
PEM="${REPO_ROOT}/secrets/roonMT-arm.pem"
ssh -i "$PEM" ec2-user@3.101.83.217
```

Scripts (behavior-critical):
- `scripts/agent.sh`
- `scripts/agent-dev.sh`
- `scripts/backups.sh`
- `scripts/dev-remote.sh`
- `scripts/seed_prod.sh`
- `deploy/setup-db-instance.sh`
- `desktop/Werk/run-prod.sh` (note: desktop still at root — Phase 3
  moves it under platforms/)
- `update-ec2.sh` (still at root in this phase)
- `build-and-push.sh` if it references the pem (verify with grep —
  it usually doesn't SSH)

Docs (path swap only):
- `CLAUDE.md`
- `server/CLAUDE.md`
- `docs/SHARED_EC2_DEPLOYMENT.md`
- `docs/DEPLOYMENT.md`
- `docs/soc/SOC1-ASSESSMENT.md`
- `docs/soc/SOC1-REMEDIATION-PLAN.md`

**Reference updates — `agent-ui/` references:**
- `build-and-push.sh:530` — `local ui_dir="${SCRIPT_DIR}/agent-ui"`
  → `local ui_dir="${SCRIPT_DIR}/server/agent-ui"` (still uses
  SCRIPT_DIR because build-and-push.sh is still at root in this
  phase)
- `scripts/agent-dev.sh` — grep for `agent-ui` and update
- CLAUDE.md if mentioned

**Verify:**
```bash
# All scripts still parse
for s in scripts/*.sh build-and-push.sh update-ec2.sh deploy/*.sh; do
  bash -n "$s" || echo "BROKEN: $s"
done

# dev-remote still tunnels (manually)
./scripts/dev-remote.sh

# build dry-run
./build-and-push.sh --no-push --agent
./build-and-push.sh --no-push --all

# Tests
cd server && ./venv/bin/python -m pytest tests/ -q

# Pem actually moved + no leftover at root
[ -f secrets/roonMT-arm.pem ] || echo "PEM MISSING"
[ -f roonMT-arm.pem ] && echo "LEFTOVER PEM AT ROOT"
```

**Phase 2 commits:**
1. `chore(secrets): create secrets/ + move pem and client_secret out of root`
2. `chore(scripts): update 8 callers to read pem from secrets/`
3. `docs: update pem path references after secrets/ move`
4. `chore(server): nest agent-ui under server/agent-ui + update build script`

**Push to prod**. dev-remote.sh, build-and-push.sh, update-ec2.sh
all keep working from same root locations — only the file they READ
moves. Lowest risk of breaking prod deploy mechanics.

---

### Phase 3 — Platform nesting + script relocation (Xcode + workflow risk)

Two highest-risk moves. Xcode project relocation can break Schemes,
and moving the daily-driver shell scripts changes user habit + CI.

**Moves:**

```bash
# Platforms grouping
mkdir -p platforms
git mv desktop platforms/desktop
git mv ios platforms/ios

# Daily-driver scripts → scripts/
git mv build-and-push.sh scripts/build-and-push.sh
git mv update-ec2.sh scripts/update-ec2.sh
git mv .landing-build-version scripts/.landing-build-version
```

**Xcode verification BEFORE committing the platforms move:**

```bash
# desktop (Werk macOS app)
open platforms/desktop/Werk/Matcha.xcodeproj
# Confirm Project Navigator shows no RED file references.
xcodebuild -project platforms/desktop/Werk/Matcha.xcodeproj \
           -scheme Werk -configuration Debug clean build

# ios (MatchaTutor)
xcodebuild -project platforms/ios/MatchaTutor.xcodeproj \
           -scheme MatchaTutor -configuration Debug clean build
```

If EITHER build fails: `git restore --staged --worktree desktop ios`
and **abandon the platforms move**. Daily desktop builds matter more
than directory cosmetics. Document the abandon and ship the rest of
Phase 3 without it.

**Reference updates for `desktop/` → `platforms/desktop/`:**
- `platforms/desktop/Werk/run-prod.sh` already uses the new pem
  path from Phase 2; just verify its own location-relative paths
  still resolve.
- CLAUDE.md (root): `desktop/Werk/` mentions → `platforms/desktop/Werk/`
- Any `.github/workflows/*.yml` that build/test desktop or ios
- Any docs in `docs/` mentioning `desktop/Werk/...` paths

**Reference updates for build-and-push.sh + update-ec2.sh move:**

`scripts/build-and-push.sh` needs REPO_ROOT computed from SCRIPT_DIR's
parent (it currently treats SCRIPT_DIR as repo root):

```bash
# OLD (when script was at root):
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly BACKEND_DIR="${SCRIPT_DIR}/server"
readonly FRONTEND_DIR="${SCRIPT_DIR}/client"
readonly AGENT_DIR="${SCRIPT_DIR}/server/agent"
readonly LANDING_BUILD_VERSION_FILE="${SCRIPT_DIR}/.landing-build-version"
# build_agent ui_dir: "${SCRIPT_DIR}/server/agent-ui"   (from Phase 2)

# NEW (script now at scripts/):
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly BACKEND_DIR="${REPO_ROOT}/server"
readonly FRONTEND_DIR="${REPO_ROOT}/client"
readonly AGENT_DIR="${REPO_ROOT}/server/agent"
readonly LANDING_BUILD_VERSION_FILE="${SCRIPT_DIR}/.landing-build-version"
# build_agent ui_dir: "${REPO_ROOT}/server/agent-ui"
```

Same pattern for `scripts/update-ec2.sh` — anything that references
sibling files via `SCRIPT_DIR` needs `REPO_ROOT` instead.

CI / GitHub Actions:
```bash
grep -rln "build-and-push.sh\|update-ec2.sh" .github/
# Update each hit to scripts/build-and-push.sh / scripts/update-ec2.sh.
```

User habit change: from now on
`./scripts/build-and-push.sh` (or shell alias). Document at top of
CLAUDE.md.

**Verify Phase 3:**

```bash
# Scripts compile
for s in scripts/*.sh; do bash -n "$s" || echo "BROKEN: $s"; done

# Build dry-run from new path
./scripts/build-and-push.sh --no-push --all

# .landing-build-version still readable + writable
ls -la scripts/.landing-build-version

# Xcode (re-run from Step 6)
xcodebuild -project platforms/desktop/Werk/Matcha.xcodeproj -scheme Werk -configuration Debug build -quiet
xcodebuild -project platforms/ios/MatchaTutor.xcodeproj -scheme MatchaTutor -configuration Debug build -quiet

# Tests
cd server && ./venv/bin/python -m pytest tests/ -q
cd client && npx tsc --noEmit

# Root inventory
ls -1 | wc -l   # expect ~10-12
```

**Phase 3 commits:**
1. `chore(root): nest desktop/ + ios/ under platforms/ + path-update sweep`
2. `chore(scripts): move build-and-push.sh + update-ec2.sh + .landing-build-version into scripts/, switch to REPO_ROOT`
3. `ci: update workflow paths to scripts/build-and-push.sh`
4. `docs(claude): final path refresh after Phase 3 relocations`

**Push to prod**. This is the riskiest cycle — schedule it for a
window where you can monitor a deploy and roll back if Xcode or the
new script paths misbehave.

---

## Commit hygiene (across all phases)

- Every move uses `git mv`. Never copy-then-delete (loses history).
- One PR per phase, multiple commits inside each PR per logical unit.
- Each PR ships as one push-to-prod cycle. Wait 24h between phases
  to surface any latent breakage before the next batch.

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Xcode breaks on `platforms/` nesting | Verify with `xcodebuild` after Step 6. Roll back single commit if broken. |
| GitHub Actions workflows reference root paths | Grep `.github/workflows/*.yml` before Step 8; update in same commit. |
| `.dockerignore` rules reference moved paths | Re-read after each move; update if old paths appear. |
| User's muscle memory for `./build-and-push.sh` | Document the new path in CLAUDE.md + offer a shell alias as a one-liner suggestion. |
| Forgotten 3rd-party docs reference `roonMT-arm.pem` at root | Step 10 grep sweep catches this. |
| `roonMT-arm.pem` gitignore — was it ignored at root? | Verify: `git check-ignore roonMT-arm.pem`. Add `secrets/` to root `.gitignore` to be safe. |

## Out of scope

- Splitting any of the moved files. This is purely a relocation.
- Rewriting CLAUDE.md beyond path updates.
- Renaming `scripts/` itself or its contents.
- Cleaning up `.pytest_cache/` / `.ruff_cache/` / `DerivedData/` —
  already gitignored, harmless presence.
- Moving `deploy/` into `infra/` — leave at root, it's tightly
  coupled to update-ec2.sh and admin docs reference it.

## Critical files

- All 15 files that reference `roonMT-arm.pem`
- `build-and-push.sh` (now `scripts/build-and-push.sh`)
- `update-ec2.sh` (now `scripts/update-ec2.sh`)
- `.github/workflows/*.yml` (path-update sweep)
- `CLAUDE.md` (path-update sweep)
- `.gitignore` (defensive `secrets/` rule)

## Verification

After completion:
```bash
# Visible root entries (excluding . / .. / dotfiles)
ls -1 | wc -l   # expect ≤ 12

# All scripts still execute
for s in scripts/*.sh; do bash -n "$s" || echo "BROKEN: $s"; done

# Backend tests
cd server && ./venv/bin/python -m pytest tests/ -q

# Frontend tsc
cd client && npx tsc --noEmit

# Build dry-run
./scripts/build-and-push.sh --no-push --all

# Xcode
xcodebuild -project platforms/desktop/Werk/Matcha.xcodeproj -scheme Werk -configuration Debug build -quiet
xcodebuild -project platforms/ios/MatchaTutor.xcodeproj -scheme MatchaTutor -configuration Debug build -quiet
```

