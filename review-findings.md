# Code review — PR #476 (`autopr/general-tasks-review` vs `main`)

Effort: `max`. Started 2026-09-08 00:32. Interrupted 00:37 by a session rate limit (HTTP 429).

## STATUS: no findings established yet

**Correction to the working assumption:** all 10 finder angles died, not 3. Every angle
subagent (A–E + Reuse/Simplification/Efficiency/Altitude/Conventions) and the orchestrator
itself terminated on the same 429. Their transcripts were recovered from
`~/.claude/projects/.../subagents/agent-*.jsonl` and inspected: each contains 70–169 lines
of *tool traffic only* (diff chunk reads, greps). Total assistant prose per agent is
108–330 characters — all of it opening lines like "I'll start by reading the diff."
Reasoning blocks are encrypted and recover as 0 chars.

So nothing from the first dispatch is salvageable except the gathered diff. Findings below
start empty and get appended one angle at a time.

## What survived

- Diff: `/private/tmp/claude-501/-Users-finch-Documents-github-matcha/c53e1749-1fea-4835-9072-415c39676a43/scratchpad/pr476.diff`
  (151,945 bytes, 36 files, ~1,400 insertions / ~230 deletions)

## Change surface

Feature: AutoPR general-tasks second-pass review — re-entrant publisher, `run_key` staging,
`action_body`, outcome transitions, workflow keys on `outcome`.

| Area | Files | Weight |
|---|---|---|
| Bash — autopr scripts | `scripts/kanban-autopr/{publish-research,select,investigate,checkpoint,dashboard,lib,run-codex-sandboxed,watch-pr}.sh`, 2 prompt txt | +305 / −92 |
| Python — backend | `project_task_service.py` (+153/−30), `task_history.py` (+54/−9), `admin/platform_settings.py` (+22/−2), `project_agent/tools.py`, `task_summary_service.py` | +240 / −42 |
| Swift — Espresso | `TaskViewerSheet+Outreach.swift` (+121/−41), `+Header` (+48/−2), `TaskCompose` (+42), `JournalContentView` (+30/−3), `MatchaWorkService+Tasks` (+27), `ProjectTaskModels`, `TaskViewerSheet`, `TaskViewerGraph`, `+Review`, `AppState+Notifications` | +325 / −59 |
| TS/React — admin + work | `Settings.tsx` (+21/−3), `platformSettings.ts`, `kanbanTemplates.ts`, `TemplateComposeModal.tsx` | +31 / −3 |
| CI | `.github/workflows/kanban-autopr.yml` | +18 / −9 |
| Tests | `test_autopr_staged_actions.py` (+242/−4), `test_kanban_autopr_research.sh` (+139/−11), `test_kanban_autopr_dashboard.sh` (+21), `test_task_categories.py` (+16) | +418 / −15 |
| Docs | `KANBAN_AUTOPR.md` (+66/−17), `AUTOMATION_REVIEW_2026-09.md` (+8) | +74 / −17 |

## Coverage ledger

| # | Angle | Status |
|---|---|---|
| 1 | Efficiency | DONE — 2 findings, both FIXED + tested |
| 2 | Simplification | pending |
| 3 | Conventions / CLAUDE.md | pending |
| 4 | Angle A — line-by-line diff scan | NOT RUN (died) |
| 5 | Angle B — removed-behavior audit | NOT RUN (died) |
| 6 | Angle C — cross-file tracer | NOT RUN (died) |
| 7 | Angle D — language/framework pitfalls (bash/python/swift/ts) | NOT RUN (died) |
| 8 | Angle E — wrapper/proxy/state-machine correctness | NOT RUN (died) |
| 9 | Reuse | NOT RUN (died) |
| 10 | Altitude | NOT RUN (died) |
| — | Verify pass (1-vote adversarial) | pending |
| — | Sweep / dedupe to <=15 findings | pending |

## Findings

### Efficiency angle (Sonnet, 2026-09-08) — 2 findings

**E1. `scripts/kanban-autopr/select.sh:148-158` — per-card read-modify-write of the hint file**
`note_ungranted_hint` does `cat` + 2 `jq` subprocesses + `date` + `mv` — 5 process spawns and
2 file I/O ops — and it is called from inside the per-card loop at `select.sh:420`, which
`continue`s rather than breaking. So every queued card on a board whose capability is not
granted pays the full cycle, sequentially, every pass. Selector runs on a one-minute cadence
(`.github/workflows/kanban-autopr.yml:16`). Board capabilities (`research`, `outreach`, …)
default off and are granted per-board, so "N queued cards on an ungranted board" is a steady
state, not a transient.
*Fix:* accumulate `{id8, capability}` pairs in a bash array across the loop, then do one read +
one `jq` transform + one write after the loop. The batched `jq` must preserve the existing
dedupe-by-`id8` (`map(select(.id8 != $id8))`) and the `.[-50:]` cap.
*Minor, same site:* `autopr_kind_field "$(autopr_kind_for_category "$category")" capability` is
computed twice for the same card (`:420-421` and `:427-428`) when `run_requested_at` is set.
Pure bash `case`, no I/O — cheap, but hoist it to a local.
*Verified:* function body and both call sites read at HEAD. Growth is bounded (`.[-50:]`), so
this is spawn/IO waste, not a leak.

**E2. `platforms/desktop/Espresso/.../Journals/JournalContentView.swift:324-333` — `parseHeading` builds 6 strings per non-heading line**
The diff replaced 3 zero-allocation `hasPrefix` literal compares with a
`stride(from: 6, through: 1, by: -1)` loop that constructs
`String(repeating: "#", count: level) + " "` on each iteration. `parseHeading` is called
unconditionally at `:263` for every line that isn't a fence/table/divider/image — i.e. every
plain paragraph line. A non-heading line now costs 6 string constructions + 6 `hasPrefix`
calls before returning nil. Whole-document re-parse fires from `.task(id: content)` (`:49-51`),
so this is per-keystroke in the live editor.
*Fix:* `guard trimmed.hasPrefix("#") else { return nil }` before the loop.
*Verified:* loop body and the `:263` call site read at HEAD.

**Checked and dismissed** (single queries or bounded by small fixed N — 4 watched boards,
≤10 staged actions): the new staged-action queries in `project_task_service.py`,
`task_history.py`, the re-entrancy logic in `publish-research.sh`, `platform_settings.py`,
and the sequential awaits in `TaskViewerSheet+Outreach.swift`.

### Efficiency fixes applied (2026-09-08)

**E1 — `scripts/kanban-autopr/select.sh`** — `note_ungranted_hint` now only queues into a
newline/tab-delimited string; a new `flush_ungranted_hints` does the single read-modify-write.

Two traps found while implementing, neither in the original finding:
- The selection loop `exit 0`s the instant it picks a runnable card, so a flush placed after
  the loop would be skipped on exactly that path. Flush runs from `trap ... EXIT` instead.
  Verified an EXIT trap preserves the original status, so the load-bearing `exit 3`
  (`NOTHING_TO_DO`, which the workflow treats as success-and-stop) still propagates.
- Accumulating into a bash *array* would have reintroduced the known bash 3.2 `set -u`
  empty-array bug — the runner is bash 3.2.57. String accumulator instead, no arrays.
- Also caught in testing: the first batched `jq` used `index(.id8)` inside `($ids | index(...))`,
  where `.` is `$ids`, not the element — `Cannot index array with string "id8"`. Fixed by
  binding `.id8 as $i` first.

Dedupe-by-`id8` and the `.[-50:]` cap are preserved. All hints in a pass now share one
timestamp; the dashboard reads `ts` only through a 1-hour cutoff (`dashboard.sh:415`), so
nothing observable changes. Duplicate `autopr_kind_field "$(autopr_kind_for_category …)"`
hoisted into `ungranted_capability`.

**E2 — `JournalContentView.swift:331`** — `guard trimmed.hasPrefix("#") else { return nil }`
ahead of the level loop. Behaviour-identical: any string matching `"#"*level + " "` starts
with `#`. A bare `"#"` still returns nil, as before.

**Verification**
- `scripts/tests/test_kanban_autopr_research.sh` — 66 passed, 0 failed (incl. "an ungranted
  skip leaves a hint the dashboard can name, even on a read-only pass")
- `scripts/tests/test_kanban_autopr_dashboard.sh` — 17 passed, 0 failed (incl. "control board
  … names cards held for a missing grant")
- Targeted batch test (no existing test covers >1 held card): 3 ungranted cards in one pass →
  3 hints, 1 distinct `ts` (one write); rerun → still 3 entries / 3 distinct `id8` (dedupe
  holds); `rc=3` preserved; stderr empty.
- `bash -n select.sh` OK; `swiftc -parse JournalContentView.swift` clean. shellcheck not
  installed on this machine.

**Not fixed, noted:** the per-card loop at `select.sh:396-410` re-parses the whole `$ranked`
array with `jq -c ".[$i]"` and then spawns ~10 more `jq` calls to pull fields out of the same
card — roughly 11 subprocesses per card per pass, which dwarfs E1. It is pre-existing code,
untouched by this PR, so it is out of review scope. Worth its own ticket.

