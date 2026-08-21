---
name: caveman-review
description: >
  Review a pull request with concise, actionable comments and required
  project-aware build/type/test gates. Use for PR, diff, and code-review requests.
---

Review the requested range, then report concise findings ready to paste into a
PR. A review is incomplete until the applicable validation gates have run or
their environmental blocker is reported.

## Establish the review range

- For a PR or current branch review, compare `merge-base(base, HEAD)..HEAD`;
  do not silently limit review to `HEAD^..HEAD`.
- Review `HEAD^..HEAD` only when the user explicitly asks for the latest
  commit. State that scope in the result.
- Inspect `git status`, the changed-file list, and `git diff --check` before
  reviewing. Do not treat unrelated worktree changes as part of the PR.

## Required validation gates

Run the narrowest meaningful command for each changed surface. Report every
command and result; a failed build/type check is a blocking finding.

- Changes under `client/`, or changes to client-consumed API/type contracts:
  run `npm run build` in `client/`. This runs TypeScript checking and the Vite
  production build. Do not substitute a source scan for this gate.
- Python server changes: run directly related pytest files when they exist.
  If no focused tests exist, run an import/compile check for changed modules
  and say coverage is absent.
- Migrations: inspect upgrade/downgrade, constraints/indexes, and existing-row
  compatibility. Never apply migrations without explicit approval.
- Do not run broad linting unless requested. Lint is not a replacement for the
  build/type gate.

If a prerequisite is unavailable, report the exact blocker and do not claim
the PR is clean. Do not implement fixes during a review unless asked.

## Review focus

Trace renamed or changed public interfaces to all consumers, including client
API functions, types, route handlers, background paths, and tests. Check
authorization and tenant scope on new endpoints. Compare behavior across every
write path that can mutate the same data.

## Output

Start with the reviewed range and validation status. Then write one terse line
per finding:

`<file>:L<line>: 🔴 bug: <problem>. <concrete fix>.`

Use `🟡 risk`, `🔵 nit`, or `❓ q` where appropriate. Keep exact line numbers
and concrete fixes. For security or architectural findings, add a short normal
paragraph when the terse form cannot explain impact safely.

Finish with validation results and any unrun gate. Do not approve/request
changes or write code.
