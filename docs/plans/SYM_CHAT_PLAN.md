# Sym-chat MVP — intent-shaped micro group chats (Espresso web, business `/work`)

## Context

New tab on the matcha-work web surface. A sym-chat is a small group chat with an
*objective* (find a meeting time; pick a dinner place). Participants type raw input in a
**private tunnel** (only they + the assistant see it); one Gemini flash-lite JSON call
re-derives that participant's structured **stance** from their full transcript; a
**deterministic per-kind aggregator** recomputes the **shape** (consensus state); when the
shape changes materially a shared **shape update** line is appended ("So far 2:00 PM looks
best (3/4 responded)" → "All 4 agree on 5:30 PM. Sent invites…"). On consensus the chat
auto-resolves and invites go out to every participant's email + Matcha inbox.

Decisions (user, 2026-09-27): kinds `schedule` + `decide`; auto-send on consensus; business
users on `/work` only (same-company `client`/`admin` users); new company flag `sym_chat`
(default off, `FEATURE_REQUIRES: (matcha_work,)`). The symlink token/passcode/public-route
architecture is NOT reused — everyone is an authenticated app user. Only the chat-engine
shape (stateless flash-lite turn, no pooled conn across the model call, never raises) is
borrowed from `services/symlink/chat.py`.

## Data model — `server/alembic/versions/symchat01_sym_chat.py` (`down_revision="mcpconn01"`)

- `mw_sym_chats(id, company_id→companies CASCADE, created_by→users CASCADE, kind CHECK
  ('schedule','decide'), title VARCHAR(120), objective TEXT, config JSONB, status CHECK
  ('open','resolved','cancelled') DEFAULT 'open', shape JSONB, resolution JSONB, resolved_at,
  created_at, updated_at)` + index `(company_id, created_at DESC)`
- `mw_sym_chat_participants(id, sym_chat_id CASCADE, user_id CASCADE, stance JSONB,
  responded_at, created_at, UNIQUE(sym_chat_id,user_id))` + index `(user_id)`
- `mw_sym_chat_messages(id, sym_chat_id, user_id, role CHECK ('user','assistant'), content,
  created_at)` + index `(sym_chat_id, user_id, created_at)` — the private tunnels
- `mw_sym_chat_updates(id, sym_chat_id, seq INT, content TEXT, shape JSONB, created_at,
  UNIQUE(sym_chat_id, seq))` — the shared feed
- Organizer is auto-added as a participant. One statement per `op.execute`; real downgrade.

## Backend — `server/app/matcha/services/sym_chat/`

- `kinds.py` — `KINDS` registry (`schedule`, `decide`), `materialize_config(kind, raw) -> dict`
  (schedule: `date` ISO, `window_start/end` HH:MM, `duration_min` 15..480, `step_min` 15,
  `timezone` zoneinfo-validated; decide: `options` ≤20 seed names), `stance_template(kind)`.
- `extract.py` — `coerce_stance(kind, raw, config, known_options) -> dict` (schedule:
  `available/unavailable` = list of `{start,end}` HH:MM clipped to the window, `preferred` =
  list HH:MM; decide: `proposals/ok_with/vetoes` strings ≤60 chars canonicalised
  case-insensitively against known options, `top_pick`), `build_prompt(...)`,
  `next_turn(kind, objective, config, transcript, current_stance, known_options,
  participant_name) -> {reply, stance, error}` — `GEMINI_FLASH_LITE`, JSON mime, temp 0.2,
  20 s timeout, never raises; on error keeps `current_stance`. Stance is **re-derived from
  the whole transcript each turn** (replace, not merge) so "3pm no longer works" overrides.
- `aggregate.py` — `compute_shape(kind, config, participants) -> shape`.
  schedule: enumerate slots `window_start..window_end-duration` by `step_min`; a participant
  covers a slot iff some `available` window contains it and no `unavailable` window overlaps;
  best = max count → most `preferred` hits → earliest; `consensus = responded==total and
  best.count==total`. decide: options = seed ∪ proposals (first-seen order); per option
  `ok` (ok_with ∪ proposals ∪ top_pick), `top`, `vetoes`; leading = zero vetoes → ok desc →
  top desc → first-seen; `consensus = responded==total and leading.ok==total`.
- `narrate.py` — `describe_change(kind, old_shape, new_shape) -> str|None`; emits only on a
  material delta (responded count, best/leading, consensus). Exact template strings; `fmt_time`.
- `service.py` — `create_sym_chat`, `list_for_user`, `get_detail`, `cancel`, and
  `run_turn(chat_id, company_id, user_id, content)` which: (1) opens a conn, loads chat +
  membership + my transcript + known options, inserts the user message, releases; (2) calls
  `extract.next_turn`; (3) reopens in a transaction, `SELECT … FOR UPDATE` the chat row,
  upserts stance/`responded_at`, recomputes shape, inserts an update row when
  `describe_change` returns text, flips `status='resolved'` + `resolution` on consensus,
  inserts the assistant message; (4) after commit: `send_invites` (only when THIS turn
  resolved — FOR UPDATE + status check makes it idempotent) via
  `notification_service.create_notification(send_email=True)` per participant, then
  `notification_service.push_to_users(user_ids, {"type":"sym_chat.updated", ...})`.
- `notification_service.py` — new `TYPES` `sym_chat_invited`, `sym_chat_resolved`; new
  `push_to_users(user_ids, payload)` wrapping the already-present lazy `manager` import (no
  third matcha→werk import site).
- `feature_flags.py` — `DEFAULT_COMPANY_FEATURES["sym_chat"]=False`,
  `FEATURE_REQUIRES["sym_chat"]=("matcha_work",)`; root `CLAUDE.md` flag row.

## Routes — `server/app/matcha/routes/matcha_work/sym_chat.py` (+ include in `__init__.py`)

`router = APIRouter(prefix="/sym-chats", dependencies=[Depends(require_feature("sym_chat"))])`,
every handler `Depends(require_admin_or_client)` + `_business_scope()` (403 on
`companies.is_personal`). Models in `server/app/matcha/models/sym_chat.py`.

- `GET  /sym-chats` — mine (created or participant), newest first
- `POST /sym-chats` — `SymChatCreate{kind, title≤120, objective≤500, participant_ids 1..20, config}`
- `GET  /sym-chats/people?q=` — same-company `clients`-joined active users (excl. me), ≤20
- `GET  /sym-chats/{id}` — chat + participants (name, responded) + updates + my transcript
- `POST /sym-chats/{id}/messages` — `{content≤2000}` → `run_turn`; Redis budgets
  `check_rate_limit(chat_id,"sym_chat_turn",200,3600)` + `(company_id,"sym_chat_turn_company",1000,3600)`
- `POST /sym-chats/{id}/cancel` — organizer only

## Frontend — `client/src/work/`

- `api/matchaWork/symChat.ts` (types + `listSymChats/createSymChat/getSymChat/
  sendSymChatMessage/cancelSymChat/searchSymChatPeople`), barrel export in `api/matchaWork.ts`.
- `api/channelSocket.ts` — `SymChatEvent`, `addSymChatListener/removeSymChatListener`,
  `case 'sym_chat.updated'`.
- `pages/SymChat/` — `SymChatList.tsx`, `SymChatDetail.tsx` (ShapeCard → UpdatesFeed →
  private TunnelChat with "Only you and the assistant see this"), `NewSymChatModal.tsx`
  (kind, title, objective, per-kind config, people picker), `useSymChatDetail.ts` (WS
  subscribe + 15 s poll), `format.ts`. `w-*` tokens only.
- `routes/WorkRouteTree.tsx` — `<FeatureGate feature="sym_chat">` block with `sym-chat` and
  `sym-chat/:chatId` (static, so they outrank the `:threadId` catch-all).
- Sidebar row (`WorkSidebar.tsx`, `showSymChat = !isPersonal && hasFeature('sym_chat')`) +
  `CollapsedRail.tsx` twin (new `showSymChat` prop).

## Tests

- `server/tests/sym_chat/test_aggregate.py`, `test_narrate.py`, `test_extract.py` (patched
  `genai_env_client` on `extract`), `test_service.py` (QueryConn; resolve once, invites once),
  `test_routes_smoke.py` (every route carries `require_feature("sym_chat")` via
  `iter_api_routes`; personal 403), `tests/alembic` single-statement guard passes.
- Client: `pages/SymChat/useSymChatDetail.test.ts`, `SymChatDetail.test.tsx`,
  `routes/EspressoRoutes.test.tsx` extension (`/work/sym-chat` renders before catch-all).

## Verification

1. `cd server && ./venv/bin/python -m pytest tests -q` (whole suite) ; `cd client && npx tsc -p tsconfig.app.json --noEmit && npm run test:run`.
2. User runs `./scripts/migrate-dev.sh` (local dev only) and enables the flag on Po Coffee Co:
   `UPDATE companies SET enabled_features = COALESCE(enabled_features,'{}'::jsonb) || '{"sym_chat": true}'::jsonb WHERE id = 'c4c256c3-60ef-4cf5-8d4c-55e963c58416';`
3. Two browser sessions on `:5174` (`tessu2022+pocoffee@gmail.com` + a second client user in the same
   company): create a `schedule` sym-chat, each types availability, watch the shape feed and the
   bell/inbox notification on consensus.
