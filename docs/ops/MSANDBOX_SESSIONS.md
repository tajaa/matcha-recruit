# Msandbox parallel sessions

`msandbox` runs Codex, OpenCode, and Claude in independent Linux containers
without making a feature branch belong to a worktree. A session remains at
detached `HEAD`; its intended PR branch is metadata until publication.

## Create and resume work

Run `msandbox` in a terminal to start the primary sandbox and AutoPR control
plane together, then open the dependency-free interactive wizard. Startup is
fail-closed: the wizard does not open unless the AutoPR timer and four-pane
dashboard are healthy. The wizard lists live sessions and offers New session,
Legacy workspace, AutoPR dashboard, validation, publication, release, and safe
garbage collection.
Names are generated automatically, and leaving an agent returns to the wizard.
Inside a wizard-opened shell, bare `msandbox` returns to the wizard without
exposing a host Docker or tmux socket to the container.

AutoPR and independent sessions share one lifecycle even though their durable
terminal sessions stay on the host side of the container boundary. From an
attached agent, press `Ctrl-b s` and select `matcha-autopr`; use `Ctrl-b d` to
detach. Running `tmux attach -t matcha-autopr` as a command inside the container
addresses the container's isolated tmux server and is therefore not the switch
operation. Direct `msandbox wizard`, `session create`, `session start`,
`session attach`, and `session shell` entrypoints reassert the complete AutoPR
plane before opening interactive work.

Every new session explicitly chooses an agent, a permission mode, development
ports/browser capability, and main or a PR as its starting point. Standard is
always the default. Autonomous must be selected for that session and is stored
in its record. The controller maps Autonomous to Codex's
`--dangerously-bypass-approvals-and-sandbox`, Claude's
`--dangerously-skip-permissions`, or OpenCode's `--auto`. Existing records
created before permission modes were added are
correctly labeled Autonomous because that was their historical behavior.

The command interface remains available for automation and advanced use:

```bash
msandbox session create payroll-fix --agent codex
msandbox session create autonomous-fix --agent codex --autonomous
msandbox session create site-editor --agent opencode --dev
msandbox session create ios-fix --agent claude --pr 351

msandbox session list
msandbox session attach payroll-fix
msandbox session shell site-editor
msandbox session exec payroll-fix -- git status --short
msandbox session stop payroll-fix
```

`msandbox stop` refuses while any independent session or AutoPR agent is running;
`msandbox stop --force` and `msandbox off` stop every independent session as well as
the system plane. Stopping preserves session worktrees, isolated Git state, and
uncommitted files so a session can be resumed later with `msandbox session start`.

One session consists of:

- `~/.local/share/matcha-msandbox/worktrees/<id>/repo`, always detached;
- a `matcha-ms-<id>` Compose project, content-addressed read-only dependencies,
  and session-local writable tool caches;
- an isolated home containing only the selected agent's copied auth file;
- a host tmux session, so disconnecting the terminal does not stop the agent;
- an attachment inbox mounted read-only at `/attachments`;
- optional unique loopback development ports; and
- an immutable JSON validation report tied to the tested commit and dirty tree.

Sessions without `--dev` publish no ports. `--dev` allocates a unique port set
under a cross-process lock. Test runs add private PostgreSQL and Redis services;
parallel sessions do not migrate or mutate the shared host development data.

## Capabilities

```bash
msandbox capabilities payroll-fix
msandbox capabilities payroll-fix --refresh
```

Selecting a session in the picker, confirming a new one, and `msandbox doctor`
all render the same measured report:

```text
Capabilities for payroll-fix
  ✅ Repository read/write       detached worktree at 4a91c02
  ✅ Linux build tools           Python 3.12.7, Node v22.23.2, npm 10.9.2, …
  ✅ GitHub CLI                  octocat on tajaa/matcha; push; workflow dispatch and
                                 merge are reachable — operator approval required
  ❌ Production test database    no restricted production-test PostgreSQL service…
  ⚠️ Host credentials in reach   /workspace/secrets/roonMT-arm.pem, host AWS profile(s)
                                 default — powerful and operator-gated
  ❌ Non-test tenant mutation    denied by API and PostgreSQL
```

Rules that make the report worth trusting:

- **Every `✅` was measured.** A probe exercises the real boundary — Chromium
  launches and closes, `gh` performs an authenticated repository and Actions
  read, the dev ports are bound inside the container and their host publication
  read back from Docker, the builder-broker socket is connected to, the
  restricted database role is asked what it can see. An executable merely
  existing, a socket file merely present, or a session flag merely set never
  renders a check.
- **A `❌` names the reason and the fallback**, so an unavailable capability is
  actionable instead of mysterious.
- **Three rows are denied by design.** `Non-test tenant mutation`,
  `Production admin/secrets`, and `Code signing / image push` are asserted
  absent. A probe that *finds* one of those identities renders `⚠️ … LEAK` and
  makes `msandbox doctor` exit nonzero; it is never reported as a capability.
- **`Host credentials in reach` is the opposite of a leak.** The repo bind mount
  and the read-only `~/.aws` mount are deliberate (`docs/ops/AGENT_SANDBOX.md`,
  threat model). The report measures what they actually reach — an AWS profile
  counts only when STS answers for it — and renders `⚠️` with an
  operator-gated warning rather than failing a healthy session's own doctor.
  The narrowed AutoPR lane reaches none of it and shows `❌`.
- **Deploy and merge are a policy boundary, not a credential one.** A `gh` token
  that can push can also dispatch `deploy.yml` and merge a pull request, so the
  `GitHub CLI` row states that authority instead of another row claiming it is
  denied. Ask the operator; do not dispatch or merge on your own.
- **One registry.** `scripts/msandbox/capabilities.py` backs the picker, the
  CLI, the create screen's planned list, and the agent's own context. There is
  no second probe list.

The report is written as mode-600 JSON and Markdown to
`/home/agent/.msandbox/capabilities.{json,md}` and injected into the agent
before its first task — Claude Code through `--append-system-prompt-file`,
Codex and OpenCode through their global instructions file in the session home.
The agent is told to test the named invocation before claiming a capability is
absent.

Reports contain no credential, token, connection string, PEM path, response
body, or unredacted command output. Probe output is redacted and truncated
before it reaches the model at all.

Redrawing the picker never starts a container, and never remeasures: the menu
renders the last report from disk, notes when it is older than 15 minutes or was
measured while the container was still running, and says so plainly when nothing
has been measured yet. **Refresh capabilities** in the session menu is the
deliberate remeasure. A stopped session reports every container probe as `the
session container is not running` rather than guessing, and a cached report is
discarded as soon as the container state it was measured under changes.

## Screenshots, PDFs, and dragged files

```bash
msandbox attach payroll-fix "/path/from/Finder/Screen Shot.png" --send
msandbox paste payroll-fix --send
```

`attach` copies explicitly selected regular files into that session's inbox.
It rejects symlinks, device files, path traversal, files over 50 MiB, and a
session total over 200 MiB. The host home and macOS temporary tree are never
mounted into the container.

`session attach` uses a PTY proxy. A complete bracketed paste containing only
existing host file paths—what Terminal sends for a Finder drag—is imported and
rewritten to `/attachments/...`. All ordinary pasted text is forwarded without
interpretation. Clipboard screenshots can always be delivered with
`msandbox paste SESSION --send`.

The legacy `msandbox codex|claude|opencode` commands and wizard-opened legacy
workspace use the same host-side interception, rewriting into
`/workspace/.msandbox/attachments/...`. An interactive shell that was already
open before the proxy was added must be restarted once.

## Validation

```bash
msandbox doctor payroll-fix
msandbox test payroll-fix --changed
msandbox test payroll-fix --pr --browser --xcode affected
msandbox test payroll-fix --all --xcode all
```

Passing `--browser` automatically upgrades that session to a
Playwright-capable content-addressed image and reuses it on later runs.

`msandbox doctor SESSION` repairs the session's GitHub credential and container
first, then remeasures the capability report above and exits nonzero when a
required capability is unavailable or a denied identity leaked into the session.
Repairing first is what keeps a long-lived session's expired in-container token
from being reported as a failed capability. It shares one probe registry with
the picker; it does not keep a second list of checks. The image readiness marker prevents commands from
racing first-use dependency initialization.

`--changed` runs cheap targeted checks. `--pr` runs every relevant package's
tests, lint/build, automation contracts, private data services, and affected
native targets. `--all` selects all Linux targets. A required command reported
as unavailable fails the gate; static review is never presented as a test run.

Xcode remains host-only. There is deliberately no container-to-host request
bridge: an Xcode project can contain shell build phases, so allowlisting the
`xcodebuild` argv alone cannot make an agent-triggered host build safe. An
operator explicitly running `msandbox test ... --pr` invokes only the
registered `espresso`, `matchatutor`, `tellus`, or `gummfit` build/test actions
with per-session DerivedData. Signing, release, notarization, deployment, and
`open` are outside this validation path.

## Submit and free the worktree

Commit changes inside the session, then:

```bash
msandbox test payroll-fix --pr
msandbox session submit payroll-fix --draft
```

Submission first stops the managed agent/container, then requires a clean tree
and a passing PR/all report for the exact captured commit and tree fingerprint.
It compares origin to the remote SHA recorded when the session was created and
pushes that captured commit to
`refs/heads/codex/payroll-fix` with a lease, opens or updates the PR, verifies
the remote SHA, stops the agent/container, and removes the clean worktree.

The feature branch is never checked out in the session, so immediately after
submission this works without Git's “already used by worktree” error:

```bash
msandbox pr checkout <number>
```

Cleanup refuses dirty files, unpublished commits, lease conflicts, and active
foreign Codex/Claude worktrees. Use Codex Handoff for an app-managed worktree.
`msandbox worktree gc` is dry-run; add `--apply` to prune metadata only when the
recorded path no longer exists.

## Stable installation and recovery

```bash
msandbox install
msandbox install --rollback <release-id>
```

The launcher is a real file at `~/.local/bin/msandbox`, not a symlink into the
repository. It selects a copied release using `MSANDBOX_RUNTIME_ROOT`, so
switching the main checkout cannot silently remove commands or alter session
Compose behavior. Installation swaps the `current` link only after copying the
complete release. Legacy control-plane verbs are deliberately routed to the
configured repository. Bare `msandbox` invokes that checkout's `system up`
first and opens the copied-release wizard only after it succeeds; explicit
wizard and session/controller verbs use the copied release directly.
On macOS, installation also unloads and removes the obsolete Xcode bridge
LaunchAgent from earlier controller versions.

Installation retains the active controller plus one rollback release. Rollback
source inputs are small and immutable; its Docker image is rebuilt on demand
instead of reserving another multi-gigabyte image indefinitely. Session images
are built once per content hash in a dedicated `matcha-msandbox` BuildKit cache,
which is capped at 2 GB by default (`MSANDBOX_BUILD_CACHE_MAX` overrides it).
The controller gives that private builder 45 seconds to start. If Docker Hub
cannot supply its BuildKit image in time, the build continues with Docker
Desktop's built-in builder instead of leaving session creation hung. Cancelling
a first build also removes the pristine session worktree and resources.

Each session image is tagged from the immutable controller/Dockerfile,
architecture, Playwright option, and that worktree's dependency manifests.
The Playwright variant layers Chromium and its system libraries onto the exact
non-browser image; it does not rebuild agent CLIs or dependency trees and both
variants share the same content-addressed dependency volumes.
Sessions with identical inputs share image and dependency caches; different
lockfiles or controller toolchains cannot race through a mutable `latest`
image. Dependency volumes are initialized under a host lock and mounted
read-only into sessions; only per-session tool cache mounts remain writable.
The agent CLIs are deliberately pinned in the image. Codex startup checks and
in-app updates are disabled through `/etc/codex/requirements.toml`; update the
Dockerfile pin and rebuild/install the controller instead of accepting an
interactive updater that cannot write to the read-only `/opt/node` toolchain.

Host fetch, verification, and publication rewrite GitHub SSH remotes to HTTPS
for that command only. This works on networks that block SSH port 22 while
leaving the repository's common Git configuration untouched. Private session
Git directories use the host's active `gh` account for the same HTTPS remote.
The controller resolves a macOS Keychain-backed token on the host and writes it
only to that session's mode-600 home; it never places the token in Compose
environment variables, Docker metadata, a command line, or shared Git config.
Credentials refresh on create, start, attach, shell, and `session exec`, so an
existing session picks up a renewed host login when it is reopened. One-time
host setup is `gh auth login --hostname github.com --git-protocol https --web`.

Inside the sandbox, ordinary GitHub work is available directly:

```bash
git add ... && git commit -m "..."
git push origin HEAD:refs/heads/codex/my-change
gh pr create --base main --head codex/my-change
gh workflow run workflow.yml --ref codex/my-change
gh run list --workflow workflow.yml
gh run watch RUN_ID
```

`msandbox doctor SESSION` verifies both GitHub CLI authentication and Actions
API access. `msandbox session submit` remains the safer publication path when
its validation/lease/release contract fits the task. Workflow dispatch is a
real repository mutation and can invoke production jobs; use each workflow's
dry-run input when it provides one.
Wizard action failures remain visible until Enter is pressed instead of being
covered immediately by the next full-screen menu.

Persistent session state is reconciled against Git, Docker, and tmux on every
list/operation. JSON is written by fsync plus atomic rename, and mutating
operations use kernel advisory locks that release automatically on process
exit. If publication
succeeds but cleanup cannot be proven safe, the session becomes
`submitted_needs_release`; the PR remains available and the worktree remains
untouched for manual inspection.
