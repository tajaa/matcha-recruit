# Msandbox parallel sessions

`msandbox` runs Codex, OpenCode, and Claude in independent Linux containers
without making a feature branch belong to a worktree. A session remains at
detached `HEAD`; its intended PR branch is metadata until publication.

## Create and resume work

```bash
msandbox session create payroll-fix --agent codex
msandbox session create site-editor --agent opencode --dev
msandbox session create ios-fix --agent claude --pr 351

msandbox session list
msandbox session attach payroll-fix
msandbox session shell site-editor
msandbox session exec payroll-fix -- git status --short
```

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

The legacy `msandbox codex|claude|opencode` commands and the interactive shell
opened by bare `msandbox` use the same host-side interception, rewriting into
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

Doctor tests Node, npm, npx, pytest, and Vitest through the same login shell an
agent subprocess uses. The image readiness marker prevents commands from
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
configured repository, while session/controller verbs use the copied release.
On macOS, installation also unloads and removes the obsolete Xcode bridge
LaunchAgent from earlier controller versions.

Each session image is tagged from the immutable controller/Dockerfile,
architecture, Playwright option, and that worktree's dependency manifests.
Sessions with identical inputs share image and dependency caches; different
lockfiles or controller toolchains cannot race through a mutable `latest`
image. Dependency volumes are initialized under a host lock and mounted
read-only into sessions; only per-session tool cache mounts remain writable.

Persistent session state is reconciled against Git, Docker, and tmux on every
list/operation. JSON is written by fsync plus atomic rename, and mutating
operations use kernel advisory locks that release automatically on process
exit. If publication
succeeds but cleanup cannot be proven safe, the session becomes
`submitted_needs_release`; the PR remains available and the worktree remains
untouched for manual inspection.
