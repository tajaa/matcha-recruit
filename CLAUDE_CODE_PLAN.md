# Repo Organization Plan for Claude Code

Ordered from **least breaking → most breaking**. Each item is independently shippable. Stop at any line and the rest can wait.

The goal isn't a tidier repo for humans — it's higher-fidelity Claude Code sessions:
- Less context bloat per task → cheaper, more focused agent turns
- Fewer permission prompts → less interruption
- Patterns scaffolded as skills → fewer repeat-bug classes (yesterday's invitation-default and IR-copilot-close-gap were both repeat-pattern bugs that scaffolded skills would have prevented)
- Smaller files → smaller reads, less context-window churn

---

## 1. Subtree `CLAUDE.md` files (zero risk)

**What**: Add directory-scoped `CLAUDE.md` files. Claude Code auto-loads the nearest `CLAUDE.md` going up from the file being edited — subtree files compose with the root.

**Risk**: None. Pure docs. No code change.

**Files to create**:
- `server/CLAUDE.md` — backend conventions (asyncpg pool over SQLAlchemy, route registration in `matcha/routes/__init__.py`, dependency layout, audit-log pattern)
- `server/app/matcha/routes/CLAUDE.md` — the router zoo. Quick index of which router owns which surface (ir_incidents, employees, matcha_work, discipline, er_copilot, etc.)
- `server/app/matcha/services/CLAUDE.md` — service-layer patterns (`get_connection()`, `ir_ai_orchestrator` Gemini prompt shape, signature provider abstraction)
- `server/app/workers/CLAUDE.md` — celery task contract (scheduler_settings gating, `@worker_ready` re-dispatch, single-concurrency rules)
- `client/CLAUDE.md` — frontend conventions (`api/client.ts` auth pattern, `useMe`, FeatureGate, sidebar dispatch, tier helpers)
- `client/src/components/ir/CLAUDE.md` — IR copilot card schema + action types, how to add a new action type
- `client/src/pages/CLAUDE.md` — route registration in `App.tsx`, tier-routing rules
- `desktop/Werk/CLAUDE.md` — SwiftUI conventions, Subscription/AppState contract, channel WS protocol

**Cost**: ~1 day of writing. Largely lifted from the existing root CLAUDE.md.

---

## 2. Symbol map in root `CLAUDE.md` (zero risk)

**What**: Append a "Where things live" cheatsheet — 30–50 most-touched symbol → `file_path:func_name` mappings. Saves agents from grepping the same things repeatedly.

**Risk**: None. Edits existing doc file.

**Examples**:
```
- Send invitation email → server/app/core/services/email.py:1053 send_employee_invitation_email
- IR copilot orchestrator → server/app/matcha/services/ir_ai_orchestrator.py:350 generate_guidance
- IR copilot card schema → client/src/components/ir/IRCopilotCard.tsx:5 CopilotCardAction
- Feature gating → client/src/components/FeatureGate.tsx + server/app/core/feature_flags.py
- Tier dispatch → client/src/utils/tier.ts + client/src/components/TenantSidebar.tsx
- Bulk employee upload → server/app/matcha/routes/employees.py:1813 bulk_upload_employees_csv
- Stripe checkout → server/app/core/routes/resources.py + server/app/matcha/routes/billing.py
- Anonymous incident intake → server/app/matcha/routes/inbound_email.py
- Email recipient guard → server/app/core/services/email.py _is_reserved_test_domain
- Reminder cron → server/app/workers/tasks/onboarding_reminders.py
```

**Cost**: 1–2 hours.

---

## 3. Ignore noise (zero runtime risk)

**What**: Add ignore globs to `.claude/settings.local.json` so Explore/Grep agents stop trawling generated/built artifacts.

**Risk**: Claude-search only. Zero runtime/code impact.

**Globs**:
```jsonc
{
  "ignore": [
    "node_modules/**",
    "client/dist/**",
    "client/.vite/**",
    "server/.venv/**",
    "server/__pycache__/**",
    "**/__pycache__/**",
    "**/*.lock",
    "**/*.snap",
    "client/src/generated/**",
    "desktop/Werk/**/*.xcodeproj/**",
    "*.bak",
    "*.pem"
  ]
}
```

**Cost**: 10 minutes.

---

## 4. Permission allowlist (zero runtime risk)

**What**: Run the `fewer-permission-prompts` skill — it scans recent transcripts and auto-builds an allowlist of safe read-only commands in `.claude/settings.json`.

**Risk**: Affects only Claude permission prompts. Zero runtime/code impact. Reversible by removing entries.

**Expected hits** (based on this session's friction):
- `git status`, `git log --oneline -n *`, `git diff [^>]*`
- `docker ps`, `docker logs * --tail *`
- `grep -rn *`, `find . -name *`
- `npx tsc --noEmit`
- `python3 -c *`
- `psql ... -c "SELECT *"` (read-only)

**What NOT to allowlist**:
- Anything with `psql ... -c "INSERT|UPDATE|DELETE|DROP|CREATE|ALTER"`
- `ssh ... "docker logs ..."` if it pulls live PII (still keep prompting on prod log reads)
- `git push`, `git reset --hard`, `git rebase`
- `gh pr ...` (PR actions stay prompted)

**Cost**: One skill invocation + review.

---

## 5. Edit hooks (low risk, isolated)

**What**: Add `PostToolUse` hooks in `.claude/settings.json` that run lint/typecheck per-file after edits. Fail-loud so Claude sees errors before committing.

**Risk**: Hooks fail in their own subprocess — never change committed code. Worst case: noisy stderr. Recoverable by removing the hook.

**Hooks to add**:
```jsonc
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "filePattern": "client/src/**/*.{ts,tsx}",
        "command": "cd client && npx tsc --noEmit --pretty false 2>&1 | grep -E '(error|warning)' | head -20 || true"
      },
      {
        "matcher": "Edit|Write",
        "filePattern": "server/app/**/*.py",
        "command": "cd server && python3 -m py_compile $CLAUDE_FILE_PATH 2>&1 || true"
      },
      {
        "matcher": "Edit|Write",
        "filePattern": "server/app/**/*.py",
        "command": "cd server && python3 -m ruff check $CLAUDE_FILE_PATH 2>&1 | head -10 || true"
      }
    ]
  }
}
```

**Caveat**: `npx tsc --noEmit` on the whole project is slow (~10–30s). If that latency hurts, scope it to the single file with a per-file tsconfig include or drop tsc and keep only `py_compile` + `ruff`. Use the `update-config` skill to wire these in.

**Cost**: 30 minutes + one skill invocation.

---

## 6. Project skills for repeated tasks (low risk, additive)

**What**: Create `.claude/skills/` entries that scaffold the boilerplate for the patterns that broke yesterday. Each skill is a markdown file describing the exact steps + file paths.

**Risk**: Additive only — new files under `.claude/skills/`. No existing code touched. A bad skill is just an unused skill.

**Skills to add**:

| Skill | What it does |
|---|---|
| `/add-ir-action-type <name>` | Adds enum value to `IRCopilotCard.tsx:5` union, registers handler branch in `ir_incidents.py:accept_copilot_card`, updates `IR_ACTION_TYPES` set in `ir_ai_orchestrator.py`, adds prompt-template guidance |
| `/add-feature-flag <name> <default>` | Adds entry to `DEFAULT_COMPANY_FEATURES` in `feature_flags.py`, adds row to CLAUDE.md flag table, scaffolds `<FeatureGate flag="..."/>` usage, sidebar entry in `ClientSidebar.tsx` |
| `/new-router <slug>` | Scaffolds `server/app/matcha/routes/<slug>.py` (router, Pydantic models, tenant-isolation dependency, audit-log call, `_get_X_with_company_check` pattern) + mounts it in `routes/__init__.py` |
| `/add-email-template <template_name>` | Scaffolds a new `send_<name>_email` method on `EmailService` with the standard `is_configured()` + `_is_reserved_test_domain()` + html/text + audit pattern. Forces using existing layout helpers, not raw HTML strings |
| `/add-celery-task <name>` | Scaffolds task in `server/app/workers/tasks/<name>.py`, registers in `celery_app.py`, adds `scheduler_settings` row gating (disabled by default), `@worker_ready` re-dispatch entry |
| `/add-bulk-upload <entity>` | Scaffolds the bulk-CSV pattern (template endpoint, multipart upload, default-off invitation toggle, reserved-domain guard, structured errors array). Encodes the lesson from yesterday's `medcenter.com` blast |

**Cost**: ~1 day for all six. Build them as you need them — don't write all six up front.

---

## 7. Split monster files (highest risk, biggest payoff)

**What**: Break the three giant files into per-concern modules.

**Risk**: Real. Imports change, route registration changes, possible test breakage, possible deploy hiccup. Mitigations: one file at a time, behind its own commit/PR; rely on `__init__.py` re-exports so external imports keep working short-term.

**Targets** (by line count, edits/month, and read-cost):

### 7a. `server/app/matcha/routes/ir_incidents.py` (~4900 lines)
```
server/app/matcha/routes/ir_incidents/
├── __init__.py           # re-exports router
├── crud.py               # GET/POST/PUT/DELETE /ir/incidents
├── copilot.py            # /copilot/stream, /copilot/accept, /copilot/skip, /copilot/close
├── osha.py               # /osha/300-log, /osha/export
├── export.py             # CSV/PDF export
├── risk.py               # /risk-insights endpoints
├── _shared.py            # _close_incident_via_copilot, _FIELD_WHITELIST, _get_incident_with_company_check, _coerce_metadata_dict
└── _types.py             # IRCopilotAcceptRequest, IRCopilotStreamRequest, etc.
```
Mount one combined `router` in `__init__.py` so `routes/__init__.py` import is unchanged.

### 7b. `server/app/core/services/email.py` (~3000 lines)
```
server/app/core/services/email/
├── __init__.py           # exports EmailService, get_email_service
├── client.py             # EmailService class, send_email, _is_reserved_test_domain, mailersend adapter
├── templates/
│   ├── _layout.py        # shared html scaffolding (the header/hero/footer divs duplicated across every send_X_email today)
│   ├── auth.py           # broker invite, beta invite, password reset
│   ├── employee.py       # employee invitation, welcome, onboarding reminders, escalations
│   ├── billing.py        # Stripe receipts, upgrade confirmations
│   ├── reports.py        # newsletter, blog moderation, weekly digest
│   └── compliance.py     # legislation watch, compliance reminders
```
The shared layout module is the real prize — every existing `send_X_email` duplicates ~80 lines of inline `<style>` CSS.

### 7c. `server/app/matcha/routes/employees.py` (5,425 lines) — **DONE 2026-05-16**
Split into 13-file package across 14 commits. Final layout:
```
server/app/matcha/routes/employees/
├── __init__.py         # 3-router re-exports + sub-router include_router glue
├── _shared.py          # helpers + invitation service + background tasks
├── crud.py             # owns main `router` (list/get/create/update/status/delete + onboarding-progress)
├── onboarding.py       # /{id}/onboarding/* + /onboarding-draft + lazy assign_rtw_tasks import
├── offboarding.py      # /{id}/offboard/* + assign_rtw_tasks + RTW/offboarding constants
├── invitations.py      # /{id}/invite + /bulk-invite + /invite-all + /invitations/status
├── bulk_upload.py      # CSV templates + bulk-upload (employees + credentials-only)
├── leave.py            # /{id}/leave/eligibility + /place
├── incidents.py        # /incident-counts + /{id}/incidents
├── credentials.py      # /{id}/credentials + credential-documents (upload/approve/reject/download)
├── oig.py              # /oig-summary + /oig-batch-screen + /{id}/oig-status + /{id}/oig-screen
├── pto_admin.py        # sibling router (pto_admin_router) — mounted at /employees/pto
└── leave_admin.py      # sibling router (leave_admin_router) — mounted at /employees/leave
```
See `server/app/matcha/routes/employees/CLAUDE.md` for the layout table + add-endpoint recipe + shadowing notes.

**Cost**: 2–3 days per file. Do under Plan mode every time — these need verification.

**Stop condition**: Don't do 7 until 1–6 are in place. The subtree CLAUDE.md + symbol map + skills do 80% of the productivity win without the refactor risk.

---

## Execution Order

1. **Today**: items 1, 2, 3, 4 — all zero-risk doc/config. ~4 hours total.
2. **This week**: item 5 (hooks) + item 6 first skill (`/add-bulk-upload`, since that's the pattern that broke this week).
3. **Next week+**: remaining skills as needed, only the email split from item 7 (highest payoff, lowest dependency-risk among the three files — most callers are at one level of indirection through `get_email_service()`).
4. **Later**: split `ir_incidents.py` and `employees.py` if context cost is still hurting.

## Verification

- After item 1: open Claude Code in `server/app/matcha/routes/employees.py`, ask "what's the convention for adding a new employee field?" — should answer from the subtree `CLAUDE.md` without spelunking
- After item 4: invitation toggle bug repro session: Claude should not need permission prompts for `git status`, `git log`, `grep`
- After item 5: introduce a syntax error in a `.tsx` file, save — typecheck hook should surface it before the next user turn
- After item 6: invoke `/add-ir-action-type test_dummy` — should produce the cross-file scaffold in one shot
- After item 7a: existing `from .ir_incidents import router` in `routes/__init__.py` should keep working; all existing copilot endpoints still respond
