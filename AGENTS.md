# OpenAI agent instructions

[`CLAUDE.md`](./CLAUDE.md) is the canonical repository guide. Follow its
repo-wide safety, architecture, validation, and operational rules in addition
to any more-specific `AGENTS.md` found below the files being inspected.

## OpenAI pull-request review directive

Apply this directive whenever an OpenAI model is asked to review a pull
request, a recent pull request, the current branch, or a diff. This is the
OpenAI review path. Do not invoke or rely on the internal Claude Code
`code-review` plugin or its agents. Do not implicitly invoke
`.agents/skills/caveman-review`; on OpenAI models that skill is opt-in only when
the user explicitly names it.

The review is read-only unless the user separately asks for fixes. Do not edit
code, commit, push, submit reviews, approve, request changes, merge, deploy, or
run database migrations as part of a review.

### Establish the exact review range

- For PR `N`, resolve the PR's base branch, base SHA, head branch, and head SHA.
  Review the complete `merge-base(base, head)..head` range, not only the latest
  commit and not an arbitrary local checkout diff.
- For "recent PR" without a number, prefer the PR associated with the current
  branch. If none exists, select the most recently updated open PR in the
  current repository. State which PR was selected and why.
- Record the PR number, base/head refs and SHAs, merge base, changed-file list,
  and whether unrelated working-tree changes exist.
- Inspect `git diff --check` and the full changed-file/stat summary before the
  detailed passes. Keep unrelated local changes outside the review range.

### Maintain complete coverage

Create a coverage ledger before reviewing. List every changed file and update
each entry to one of:

- `reviewed` — every changed hunk and enough surrounding code were inspected;
- `reviewed + traced` — changed contracts were followed outside the diff; or
- `excluded` — only for binary, vendored, or generated artifacts, with the
  exact reason and the corresponding source/generator impact still assessed.

Do not stop after finding the first issue. Review every changed file and every
changed hunk. A file is not covered merely because a subagent mentioned it or
a test passed. Before finishing, reconcile the ledger against the changed-file
list and report anything not fully reviewed.

For every changed contract, trace all relevant producers and consumers beyond
the diff. Contracts include function signatures, types, API payloads, database
schema and queries, persisted values, events/jobs, cache keys, configuration
and environment variables, serialization formats, authentication claims, and
UI state. Follow them through:

`producer -> validation -> persistence/transport -> consumer -> user or operational effect`

Inspect all applicable call sites, alternate write paths, background workers,
retry/recovery paths, tests, and docs. Search the repository; do not infer
consumer coverage from filenames alone.

### Run separate review passes

Perform distinct, complete passes over the range for:

1. correctness, invariants, and edge cases;
2. state transitions, partial failure, rollback, retries, and terminal states;
3. producer/consumer validation parity and backward compatibility;
4. concurrency, ordering, duplicate delivery, reentrancy, and idempotency;
5. database constraints and limits, Unicode/multibyte behavior, time values,
   numeric bounds, and serialization/deserialization boundaries;
6. security, authorization, authentication, tenant isolation, injection,
   secrets, and unsafe input/output handling;
7. performance, query count, memory, fan-out, payload size, and scaling; and
8. tests, documentation, observability, deployment, migration, configuration,
   and other operational behavior.

For every mutation followed by an operation that can fail, explicitly inspect
the failure boundary. Verify transactionality or compensation, externally
visible partial state, retry behavior, duplicate execution, and whether the
operation can become stuck in a non-terminal state.

Exercise or reason through, as applicable:

- reordered, repeated, stale, and concurrently submitted inputs;
- missing, empty, malformed, and contradictory values;
- missing environment variables and partial configuration;
- duplicate execution, retry after timeout, and replay after partial success;
- negated instructions and allow/deny precedence;
- zero, one, maximum, and over-maximum lengths and counts;
- Unicode, emoji, combining characters, normalization, and byte-vs-character
  limits;
- serialization round trips, unknown enum values, nullability, and version
  skew; and
- authorization changes between enqueue and execution or between read and
  write.

Do not turn this checklist into speculative findings. Confirm each reported
issue against full-file context, call sites, guards, and relevant tests.

### Use independent parallel review

When subagents are available, use them in parallel for independent review
passes. Partition meaningful surfaces such as backend/data, frontend/contracts,
security/concurrency, and tests/operations. For a small diff, assign independent
passes over the same range instead of skipping independent review.

Give every subagent the exact review range and require it to report files and
hunks inspected, contract traces followed, validation performed, candidate
findings with evidence, and anything unreviewed. Subagent output is not a final
finding: verify it against the code, reject unsupported claims, and deduplicate
overlap before reporting.

If independent parallel review is unavailable, say so explicitly and perform
the separate passes serially.

### Validate proportionally

Run the narrowest safe, meaningful validation for each changed surface and
report the exact commands and results.

- For `client/` changes or client-consumed API/type changes, run the production
  build/type gate from `client/` unless the environment blocks it.
- For Python server changes, run directly related tests. If no focused tests
  exist, run an import/compile check for the changed modules and report the
  test-coverage gap.
- For migrations, inspect upgrade, downgrade, existing-row compatibility,
  constraints, indexes, locks, and application version skew. Never apply a
  migration during review without explicit approval.
- Add focused static checks or tests when they materially validate a suspected
  issue. Do not mutate source files to create a test.
- If a prerequisite is unavailable or a command would be unsafe, report the
  exact blocker. Do not claim the review or validation is clean when required
  coverage did not run.

### Report a review that can be audited

The final response must contain:

1. **Reviewed range** — PR, base/head, merge base, and scope notes.
2. **Findings by severity** — highest severity first. Each finding needs an
   exact file/line, triggering scenario, concrete impact, supporting evidence,
   and a focused fix direction. Report only actionable defects introduced by
   or materially exposed by the reviewed range.
3. **Coverage ledger** — every changed file marked `reviewed`, `reviewed +
   traced`, or `excluded` with its reason.
4. **Contract and failure-path traces** — concise summary of the important
   producer/consumer and mutation/recovery paths inspected.
5. **Validation** — every command and result, including blocked or unrun gates.
6. **Residual risk** — anything not fully reviewed, not reproducible, or
   dependent on unavailable infrastructure.

If there are no findings, say so directly, but still include the reviewed
range, complete coverage ledger, validation, and residual-risk sections. Never
use "no findings" to imply that unreviewed or unvalidated surfaces are safe.
