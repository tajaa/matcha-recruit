# Werk backend (channels / calls / job postings)

Werk / Werk-Lite's real-time layer: channel chat, LiveKit audio/video calls, channel job postings. **Not a separate product identity** — this is a *matcha tenant* feature (`werk_lite` + `matcha_work` flags, `client`/`employee` roles, the same `companies` row). See root `CLAUDE.md`'s `werk_lite` feature-flag row and the "fourth backend app" paragraph at the end of the products-map section — that paragraph is the canonical statement of this package's import rules; read it before changing any cross-app import here, since it documents exact edge counts that must stay accurate.

## Layout

- `routes/channels.py` + `channels_ws.py` — channel CRUD + WebSocket fan-out (`channels_ws.py` owns `manager`, the live object matcha imports back for notification fan-out). `channels.location_id` (migration `oploc01`) optionally binds a channel to a `business_locations` row — `POST/GET/PATCH /channels` accept/return it, `GET /channels/locations` is the store picker (active, non-`is_company_wide` rows only). `channels_ws._channel_location(conn, channel_id_str)` is the one lookup every @huume dispatch handler uses to thread that scope into `ems`/`inventory`/`schedule_chat`.
- `routes/channel_calls.py` — LiveKit call start/join, invite-only via `channel_call_invites`
- `routes/channel_broadcasts.py`, `channel_job_postings.py`, `inbox.py`
- `services/channel_job_posting_service.py`, `channel_payment_service.py`, `inactivity_worker.py`
- There is no `channels_service.py` — channel logic lives directly in the two route modules.

## Import boundary (the nuanced part — don't re-derive, read this)

`werk → matcha.services` is **allowed and intentional**: 10 files / 83 import statements (verified 2026-09-01 with `rg -n "^\s*(from|import)\s+(app\.|\.\.\.)matcha" server/app/werk -g '*.py'`), reaching these service families — `notification_service` (the bulk of them), `matcha_work.project_file_service`/`mentions`/`project_agent` (`@espresso`'s read-only repo-question dispatch), `billing.entitlements_service`, `billing.token_budget_service`/`FREE_TOKEN_GRANT`, `matcha.dependencies` (`resolve_accessible_company_scope`, `require_admin_or_client`), `ems.*` (`ask`/`intent`/`protocols`/`event_intake`/`urgent_notify`/`channel_grounding`/`channel_agent` — channels_ws.py's Huume/EMS message dispatch; `channel_agent` is the bounded tool-calling loop `_bg_ems_ask` calls for schedule/incidents/inventory/HR-ops grounding beyond `ems_events`, `channel_grounding` its policy registry), `scheduling.schedule_chat`/`schedule_chat_rules`, `ir.report_links`, `inventory.*` (`movements`/`orders`/`pills`/`extraction`/`reorder`/`rules`/`receipts` — channels_ws.py's `_bg_inventory_request`/`_bg_inventory_reply`; `receipts.receive_channel_lines` is the channel-side receive-against-order path, added when a chat delivery claim stopped auto-writing a bare `in` movement), and `_shared.uploads.read_upload_capped` (`inbox.py`'s capped-read upload gate). All lazy in-function imports **except one**: `routes/channels.py:18` imports `matcha.dependencies` at module level (FastAPI route dependencies must resolve at decoration time) — don't "fix" that into a lazy import.

The reverse edge (`matcha → werk`) is exactly 2 sites, both lazy in-function imports of `werk.routes.channels_ws.manager` (`services/notification_service.py`, `services/matcha_work/project_task_notifications.py`) — a real bidirectional dependency on one shared WebSocket fan-out object. Adding a *third* kind of matcha→werk import is the thing to refuse.

**What must stay 0 in both directions: routes importing routes.** `werk → matcha.routes` is 0 and should remain so — werk reaches services, never handlers.

## Cross-cutting rules

DB safety rules, test-data email domain rules, and deploy rules are in root `CLAUDE.md` — they apply here unchanged, not restated.

## Feature flags (full specs, moved from root CLAUDE.md)

## `werk_lite` (default ❌)

**Werk Lite** — standalone business work-chat surface at `/werk-lite` with its **own login** (`/werk-lite/login` → same `/api/auth/login`, lands all roles on `/werk-lite`; `WerkLiteAuthGuard` redirects unauthenticated there, not the main `/login`). Channel chat + LiveKit audio/video calls + collaborative kanban boards only (Slack/Teams-style). **Whole-company** access, not admin-only: business admins (`role='client'`) AND employees (`role='employee'`) — `/auth/me` carries `enabled_features` for both. Boards are matcha-work projects, so the kanban backend needs `matcha_work` too — a Werk-Lite company needs **both** `werk_lite` + `matcha_work`. Employee board access is via the new `require_company_member` dep on the project view + task/subtask routes (company-scoped); board *creation*/rename stays admin/client. Entry: `<FeatureGate flag="werk_lite">` + a `ClientSidebar` AI-group entry (admins). Not in any tier overlay.

## `werk_lite_calls_all_members` (default ❌)

Werk Lite call-start policy. `false` = only admins/business-admins start calls; `true` = any channel member starts. Joining is always open to members. Only consulted for `werk_lite` companies, in `channel_calls.start_call` (which also skips the per-user Werk Pro gate for werk-lite).
