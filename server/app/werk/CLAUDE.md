# Werk backend (channels / calls / job postings)

Werk / Werk-Lite's real-time layer: channel chat, LiveKit audio/video calls, channel job postings. **Not a separate product identity** — this is a *matcha tenant* feature (`werk_lite` + `matcha_work` flags, `client`/`employee` roles, the same `companies` row). See root `CLAUDE.md`'s `werk_lite` feature-flag row and the "fourth backend app" paragraph at the end of the products-map section — that paragraph is the canonical statement of this package's import rules; read it before changing any cross-app import here, since it documents exact edge counts that must stay accurate.

## Layout

- `routes/channels.py` + `channels_ws.py` — channel CRUD + WebSocket fan-out (`channels_ws.py` owns `manager`, the live object matcha imports back for notification fan-out)
- `routes/channel_calls.py` — LiveKit call start/join, invite-only via `channel_call_invites`
- `routes/channel_broadcasts.py`, `channel_job_postings.py`, `inbox.py`
- `services/channel_job_posting_service.py`, `channel_payment_service.py`, `inactivity_worker.py`
- There is no `channels_service.py` — channel logic lives directly in the two route modules.

## Import boundary (the nuanced part — don't re-derive, read this)

`werk → matcha.services` is **allowed and intentional**: 9 files / 44 import statements (verified 2026-08-01 — the EMS/scheduling additions to `channels_ws.py` had drifted this count well past the last-recorded 25 before this recount), reaching nine things — `notification_service` (the bulk of them), `matcha_work.project_file_service`/`mentions`, `billing.entitlements_service`, `billing.token_budget_service.FREE_TOKEN_GRANT`, `matcha.dependencies` (`resolve_accessible_company_scope`, `require_admin_or_client`), `ems.*` (`ask`/`intent`/`protocols`/`event_intake`/`urgent_notify` — channels_ws.py's Huume/EMS message dispatch), `scheduling.schedule_chat`/`schedule_chat_rules`, `ir.report_links`, and `_shared.uploads.read_upload_capped` (new — `inbox.py`'s capped-read upload gate). All lazy in-function imports **except one**: `routes/channels.py:18` imports `matcha.dependencies` at module level (FastAPI route dependencies must resolve at decoration time) — don't "fix" that into a lazy import.

The reverse edge (`matcha → werk`) is exactly 2 sites, both lazy in-function imports of `werk.routes.channels_ws.manager` (`services/notification_service.py`, `services/matcha_work/project_task_notifications.py`) — a real bidirectional dependency on one shared WebSocket fan-out object. Adding a *third* kind of matcha→werk import is the thing to refuse.

**What must stay 0 in both directions: routes importing routes.** `werk → matcha.routes` is 0 and should remain so — werk reaches services, never handlers.

## Cross-cutting rules

DB safety rules, test-data email domain rules, and deploy rules are in root `CLAUDE.md` — they apply here unchanged, not restated.
