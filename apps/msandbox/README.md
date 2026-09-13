# msandbox

The agent sandbox, its session manager, and the AutoPR harness — one piece of
operator software (part harness, part sandbox, part protocol) for running
coding agents against this repo and the apps built from it.

```
msandbox                      # session manager (installed launcher)
msandbox --dashboard          # the AutoPR observer first
msandbox doctor               # are the installed copies current?
./apps/msandbox/bin/agent-sandbox.sh install   # (re)install the launcher + LaunchAgents
```

Three lanes share `cli/` and `sandbox/`:

- **Sessions** — `cli/` creates isolated git worktrees and containers per task
  and drives Codex / Claude Code / OpenCode inside them.
- **AutoPR** — `harness/` picks a kanban card, investigates it in a sandbox,
  and publishes a draft PR or a research/email artifact. Runs from GitHub
  Actions on the self-hosted Mac; dispatched by LaunchAgents.
- **Error autofix / self-audit / scope** — sibling lanes with the same shape.

Layout, invariants, and the install story: `CLAUDE.md` in this directory.
Deep docs: `docs/`.
