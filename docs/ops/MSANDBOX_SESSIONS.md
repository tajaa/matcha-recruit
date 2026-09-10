# Msandbox parallel sessions

`msandbox` runs Codex, OpenCode, and Claude in independent Linux containers
without making a feature branch belong to a worktree. A session remains at
detached `HEAD`. The manager can create a local PR branch without checking it
out; publication pushes the validated detached commit to that branch.

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

## Interactive control center

All menus support mouse clicks, scroll wheel, arrows, `j`/`k`, and numbered
selection. The selected action's description stays at the bottom of the screen.
Long session lists scroll within the terminal height. `Esc`, `q`, and `Ctrl-C`
go back; leaving the manager keeps background sessions alive. Long reports use
`less` when available; even short results wait for `q`. Pager interrupts restore
terminal input settings before returning. Redirected terminals retain the
plain numbered interface. Terminal hops that fall back from SGR to legacy X10
mouse reports are consumed as complete six-byte events; coordinate bytes cannot
become menu shortcuts.

Recoverable action errors remain in the active submenu and show their message
before retry. Publication edits also retain the entered branch, title, and commit
while an invalid value is corrected.

Opening an existing session always shows its controls before attaching:

- **Start/Resume harness** opens the selected Codex, Claude, or OpenCode CLI.
  `Ctrl-b d` returns to the manager while the harness continues running. Normal
  harness exit now detaches the dead pane automatically and returns to the menu;
  `Ctrl-C` inside a harness retains that CLI's interrupt behavior. Plain `exit`
  is a shell command, not a universal agent-chat command.
- **Change harness** stops the workspace and switches the selected harness.
  Files, Git history, attachments, ports, and explicit permissions persist.
  Each harness keeps its own conversation history; this opens a new conversation
  and does not translate one harness's transcript into another. Login provisioning
  must succeed before the new harness is saved. Switching removes the other
  harnesses' login files (including Claude's `.claude.json` login/settings file),
  while retaining conversation history. Failed provisioning or saving restores
  the previous login files. A missing target login produces a host-authentication
  instruction and rolls back the switch. Credential rollback uses private disk
  snapshots, so large Claude configuration files do not exceed a memory cap.
  Start it from the session menu.
- **Environment & processes** measures Docker state, harness terminals,
  container executable names/PIDs/uptime, `dev-remote.sh` panes, host development
  endpoints, session endpoints, and database/Redis TCP reachability. Start/stop
  development controls act only inside the selected sandbox, using the existing
  `dev-remote.sh` and shared host development data. They do not manage host services.
  Refresh never starts containers. A configured port, an existing tmux pane, and
  a reachable TCP socket are explicitly different observations. SSH processes
  are identified without exposing argv or destinations; no tunnel-health claim
  is inferred from an SSH process merely existing.
  Workspace discovery filters Docker's exact Compose `workspace` service; session
  names cannot cause database or Redis containers to be selected. Malformed probe
  output is shown as an unreliable measurement instead of closing the manager.
  Missing or malformed endpoint URLs are never probed as loopback addresses.
- **Browser** enables the browser image (stopping current workspace processes),
  starts/stops a managed headless Chromium, or captures a URL into a viewport PNG.
  Managed Chromium's CDP endpoint is `http://127.0.0.1:9222` **inside** the container,
  with no host publication. Screenshot capture uses a separate short-lived browser
  and closes it after success or failure. Browser executable/PID state appears in
  Environment & processes. Browser readiness allows the complete bounded probe
  window, and stopping an absent browser or development tmux session is idempotent.
- **Files & attachments** imports quoted/dragged host paths or the clipboard,
  lists uploaded inputs and generated output, previews text, pastes references
  into the harness, and exports durable copies (revealed in Finder on macOS).
  Uploads stay at `/attachments`; generated files should be written under
  `/workspace/.msandbox/outputs`. Enumeration is bounded to 200 files / 500
  directories; symlinks are refused, and export rechecks every path component.
  Exports are limited to 50 MiB per file and 1 GiB per session and live at
  `~/.local/share/matcha-msandbox/exports/<id>`, outside the releasable worktree.
  **Export wanted generated files before releasing or submitting a session.**
  Generated output is ignored by Git and otherwise disappears with the worktree.
  Creation and explicit lifecycle repair install `/.msandbox/outputs/` in isolated
  Git `info/exclude`. A host exclusion is added only when Git does not already
  ignore outputs, to protect sessions based on older commits. That fallback rule
  is shared by linked worktrees; existing rules are preserved. Routine menu
  redraws do not repeat this repair.
  Binary previews use file type, signatures, and UTF-8 validation. Exports stream
  from the validated file descriptor without buffering the whole file or making
  an intermediate temporary copy.
  Controller commits also exclude `.msandbox` and refuse forcibly staged sandbox files.
  Files with Unicode control-category characters in any path component are hidden
  and cannot be delivered. Harness delivery uses bracketed paste so a pasted path
  cannot submit the current prompt.
- **Testing** offers existing changed-file, full-PR, browser and native validation.
  Results stay visible after a run. Tests use the existing isolated validation
  services and immutable reports, including their existing stop/snapshot behavior.
- **Tools & access** opens the full measured capability report on demand. Its
  remeasure action explicitly starts the workspace if needed. Session overview
  only shows a compact historical summary, with stale/stopped warnings.
- **Branch & pull request** runs `gpt-5.6-luna` with `high` reasoning to suggest
  a branch name, commit subject, title, and description from bounded Git summaries.
  The helper uses a temporary read-only container with writable tmpfs, a read-only
  Codex login mount and no workspace/host-service mounts. Codex runs with read-only
  sandboxing and approval policy `never`; shell/unified execution, browser/computer
  use, host code execution, apps, plugins, subagents, image generation, hooks, and
  web search are explicitly disabled. User config and execution rules are ignored.
  Network remains available for model authentication and inference; this is not
  a network-isolated helper. The draft survives menu navigation and restart.
  Review the copy and displayed changed-file list, then click **Create branch /
  commit** to stop the running harness/workspace and commit all shown changes;
  both the action label and confirmation disclose that stop. The controller rejects stale drafts,
  colliding branches, and invalid model output. Repeated applies advance the local
  branch with a compare-and-swap update; checked-out branches are refused. A local
  branch created by the controller is removed during successful release only when
  it has no commits outside the published session and has not moved concurrently.
  A stale, remote-deleted local ref with no unique commits can be safely adopted
  by a later session and receives the same cleanup protection.
  If optional local-branch cleanup fails after the worktree is removed, release
  still finalizes the session and frees its ports; the result names the retained
  branch cleanup warning.
  Existing PR sessions retain their
  branch. Run **Validate full PR**, then **Publish draft pull request**; the existing
  exact-commit validation, push lease, and release checks still apply. The helper
  needs the current sandbox image built and a valid host `codex login`.
  **Luna is optional:** already committed work can use **Publish draft pull request**
  directly, with the session name and default PR description. Claude and OpenCode
  sessions do not need a Codex login to publish; the same validation and release
  checks apply.
  When reviewed copy would replace an existing PR's title and description, the
  confirmation names that PR and the fields being replaced. A failed or interrupted
  push/GitHub step returns the session to `stopped`; proven pushed state is retained
  so publishing can retry with the correct remote lease.

Submenu loading failures offer Back and Retry. A broken session remains visible
with a repair notice while healthy sessions stay selectable. Testing → Back
returns directly. Terminal headings retain trailing notices, and incomplete mouse
reports time out instead of blocking input.

Equivalent navigation commands:

```bash
msandbox session switch payroll-fix --agent claude
msandbox session start payroll-fix
msandbox session ps payroll-fix
msandbox session ps payroll-fix --json
```

If a harness exits, the manager preserves and offers up to its last 120 lines before
showing a restart action that explicitly replaces them. Opening the manager also
installs this pane lifecycle hook on still-running sessions created by an older
controller. The CLI protects preserved output by default; use `session start
SESSION --replace-exited` only after inspecting it in the manager.

`session ps` exits nonzero whenever its snapshot is unreliable. With `--json`,
the versioned object contains `schema_version`, `checked_at`, `reliable`,
`container_id`, `containers`, `harness_terminals`, `dev_remote_running`,
`connections`, `ssh_process_observed`, `processes`, and stable error-code values
in `errors` (`docker_unavailable`, `connection_probe_unavailable`,
`process_inventory_unavailable`, or `inspection_failed`); it does not expose
the human-readable display lines.

Endpoint inspection reads `HOST_DEV_BACKEND_URL` and
`HOST_DEV_FRONTEND_URL` inside the workspace. They are inherited from
`docker-compose.sandbox.yml` by every session overlay and default to the host
gateway on ports 8001 and 5174; host `HOST_DEV_BACKEND_PORT` and
`HOST_DEV_FRONTEND_PORT` overrides flow through Compose interpolation.

### Terminal dashboard

`msandbox` and `msandbox wizard` open a split-pane dashboard in an interactive
terminal. The left sidebar selects a session; the right side has Overview,
Processes, Tools & access, Files, Testing, Branch & PR, and AutoPR tabs. The harness,
shell, browser, attachment, validation, and publication controls open the same
guarded workflows as the classic manager. Prompts and harnesses take over the
terminal temporarily, then return to the selected session and tab.

- Click a session or action, or use arrows and Enter. Tab / Shift-Tab moves
  focus between the sidebar, tabs, and actions. Keys 1–7 select a detail tab.
- Page Up / Page Down scroll details. Terminals whose curses library reports
  both wheel directions can also scroll the detail pane with the mouse wheel.
  Arrow keys scroll the sidebar through all sessions and global actions.
- `r` reloads saved records and refreshes the selected session's process and
  connection snapshot. Entering Processes also starts its first read-only
  inspection in the background; navigation remains available while Docker
  responds. Measurements show their timestamp and partial/unavailable state.
- `n` creates a session; Escape returns focus to the sidebar; `q` closes the
  dashboard while running sessions continue. Inside a harness, press Ctrl-b,
  then d to detach back to the dashboard. Ctrl-c interrupts that harness.
- Start checks for preserved exit output and offers inspection or confirmation
  before replacing it. Release results wait for dismissal before returning.

The header and sidebar show **saved** session state, not a health guarantee.
Tool and validation reports are historical; publication still validates the
current commit. Unexpected access and missing required capabilities are marked
as warnings in Tools & access. Every dashboard reload reconciles all saved
sessions and surfaces per-session repair failures without hiding healthy ones.
Cached capability reports and file indexes load in the background when their
tabs open. AutoPR activity and takeover are available through **AutoPR runs**
in the sidebar or tab **7**. That tab also links to the full observer dashboard.
No browser, Electron, Python package download, or daemon is required for the UI;
it uses Python's standard `curses` module on macOS/Linux. A 256-color terminal
gets the green palette; basic color and monochrome terminals remain usable.
Resize to at least 73 columns × 20 rows, or press `c` for the classic menu.
`MSANDBOX_UI=classic msandbox wizard` explicitly selects the classic menu;
redirected/custom-reader usage keeps the numbered prompt behavior.

### Take over an AutoPR task

The AutoPR tab lists supervised **Kanban investigations** on this host with their
task, PR/branch, model, effort, ownership, and recent output. Reads refresh in the
background without a GitHub call on every redraw. Runs started before the runner
uses this release cannot be taken over retroactively. Error-autofix and self-audit
lanes remain viewable through the full observer dashboard, not takeover controls.
After merging, update both installed components from the updated checkout with
`./scripts/agent-sandbox.sh install` and
`./scripts/kanban-autopr/install-launch-agent.sh`. The latter preserves the
existing master-switch state; installation is not permission to start AutoPR.

1. Select a run and click **Take over / correct course**. Wait for ownership to
   become **you**: the controller stops that model's container before moving the
   checkout to a preserved, per-run location. The interrupted investigation ends;
   it does not retain a workflow slot while you work.
2. Click **Open your Codex session** or **Open sandbox shell**. The manual session
   uses a unique container and tmux session, with no published ports or credentials
   from the broader interactive sandbox. Its initial conversation reads the
   prior task input/report and current edits; it is not the original autonomous
   conversation. Subsequent opens resume the manual conversation. Ctrl-b then d
   returns to the manager without stopping it.
3. **Change model / effort** stops this run's harness and shell; reopen Codex to
   resume with the selected settings. Those settings also carry into handback.
   Model availability and supported efforts still depend on your Codex account.
4. **Hand back to AutoPR** asks for continuation instructions, stops your writers,
   and saves the tracked/new-file diff before requesting the next normal AutoPR
   pass. A queue failure leaves a retry button and the preserved checkout. You can
   reclaim a queued handback before a workflow claims it; an active continuation
   must be taken over through its new live entry.

AutoPR's Actions checkout is already separate from your primary checkout. Manual
takeover uses a managed clone, not a branch checked out on your local `main`.
Ordinary sandbox sessions stay usable throughout. You never merge that clone:
the normal AutoPR publisher updates the PR. After a successful continuation, the
controller archives the saved clone (including Git history and ignored outputs)
as `checkout-recovery.tar.gz` and removes that exact clone. The recovery archive
remains under `~/.local/state/matcha-autopr/runs/<run-id>/`.

Only one owner may write at a time. Paused tasks are skipped even if another queue
signal arrives. A crashed supervisor exposes **Recover interrupted run**; an
unrecognized checkout is never overwritten. Handback patches are limited to
5 MiB and must apply cleanly to the next run's base. Conflicts, forbidden paths,
validation failures, and publication failures keep the saved handback available;
they do not silently drop it or bypass AutoPR's normal guards. Research tasks
retain their existing no-code-change policy. No merge or deployment is implied.

Controller changes are picked up by `msandbox install` from the checkout that
contains them. No terminal GUI dependency or database migration is required.
Unit coverage runs through `bash scripts/tests/test_msandbox_sessions.sh`.
Optional browser smoke (one disposable container, no host data/credentials or
network) uses an existing browser-enabled image:

```bash
python3 -m scripts.tests.msandbox_manager_smoke --image <browser-enabled-image>
```

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

The session's Tools & access screen, a newly created session, and `msandbox doctor`
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

For a one-command smoke test of the current PR against the real local Docker
boundary, run `./scripts/msandbox-live-smoke.sh`. It installs the controller
from the current checkout, creates a disposable no-agent session for the PR
associated with the current branch, runs the focused unit/shell checks, doctor,
capability persistence and isolation checks, and the session's `--pr`
validation plan. A successful run releases its session. A failed run stops but
retains the session for inspection; set `MSANDBOX_LIVE_KEEP_SESSION=1` to retain
it even after success, or `MSANDBOX_LIVE_PR=<number>` to select a PR explicitly.

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
The agent CLIs are pinned *inside* the image: Codex startup checks and in-app
updates are disabled through `/etc/codex/requirements.toml`, and an interactive
updater cannot write to the read-only `/opt/node` toolchain. Which pin a
container carries depends on its lineage — a session image bakes in the npm
`latest` the host resolved at build time, while the AutoPR lanes' `:latest`
image carries the Dockerfile defaults until it is rebuilt. See "Agent CLI
updates" in `docs/ops/AGENT_SANDBOX.md`.

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
