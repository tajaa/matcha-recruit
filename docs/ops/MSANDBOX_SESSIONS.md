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
- a `matcha-ms-<id>` Compose project, content-addressed shared dependencies,
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

Xcode remains host-only. `/usr/local/bin/msandbox-host` submits a strict JSON
request containing only session ID, commit, target, and `build|test`. The
LaunchAgent validates the registered worktree and runs one of `espresso`,
`matchatutor`, `tellus`, or `gummfit` with per-session DerivedData. It cannot
run signing, release, notarization, deployment, `open`, or arbitrary argv.

## Submit and free the worktree

Commit changes inside the session, then:

```bash
msandbox test payroll-fix --pr
msandbox session submit payroll-fix --draft
```

Submission requires a clean tree and a passing, current PR report. It fetches
the expected remote branch, pushes detached `HEAD` to
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
complete release and installs the narrow Xcode host LaunchAgent on macOS.

Each session image is tagged from the immutable controller/Dockerfile,
architecture, Playwright option, and that worktree's dependency manifests.
Sessions with identical inputs share image and dependency caches; different
lockfiles cannot race through a mutable `latest` image.

Persistent session state is reconciled against Git, Docker, and tmux on every
list/operation. JSON is written by fsync plus atomic rename, and mutating
operations use PID-owned locks with stale-owner recovery. If publication
succeeds but cleanup cannot be proven safe, the session becomes
`submitted_needs_release`; the PR remains available and the worktree remains
untouched for manual inspection.
