# Live video broadcast in matcha-work channels (macOS)

## Context

Channel owners want to go live in their channel, optionally bring on existing members as on-stage guests, and let the rest of the channel watch. macOS-first; web/iOS later.

**Locked decisions:**
- SFU: **self-hosted LiveKit Server** (Apache 2.0). Run alongside existing containers on EC2. Free; only AWS infra costs.
- Scale: 10–100 viewers per channel. Need an SFU; existing `voice_signaling.py` peer-mesh (max 4) cannot do this and stays in place for the small audio-call use-case.
- Guests: only existing channel members can be promoted to publishers. No anonymous joins, no email invites in v1.
- Recording: none in v1.

## Existing infra to reuse

- `channels` + `channel_members` (role: `owner|moderator|member`) — `server/alembic/versions/zzd3e4f5g6h7_add_channel_tables.py`, `zzg7h8i9j0k1_channel_permissions.py`
- Channel WebSocket signaling — `server/app/core/routes/channels_ws.py` (`/ws/channels?token=<jwt>`, `ChannelConnectionManager` with `room_members[room_key]`)
- Channel REST routes — `server/app/core/routes/channels.py` (role checks lines 1696–1790)
- Mac WS client — `desktop/Matcha/Matcha/Services/ChannelsWebSocket.swift`
- Mac admin UI — `desktop/Matcha/Matcha/Views/Channels/ChannelAdminWizardView.swift` (gates on `my_role == "owner"`)
- JWT issue/verify util — already used for `/ws/channels?token=...`; reuse same secret material via `livekit.AccessToken` API key

## Architecture

```
┌────────────────┐     ┌──────────────┐     ┌────────────────┐
│  macOS app     │ WS  │  FastAPI     │ HTTP│  LiveKit       │
│  LiveKit Swift │◄───►│  channels_ws │◄───►│  Server (Docker│
│  SDK           │     │  + new       │     │  on EC2)       │
│                │     │  /broadcast  │     │                │
└────────┬───────┘     └──────────────┘     └───────┬────────┘
         │                                            │
         │            WebRTC media (UDP/TURN)         │
         └────────────────────────────────────────────┘
```

Lifecycle = FastAPI routes + channel WS push events.
Media = LiveKit only. Mac client connects directly to LiveKit Server using server-issued JWT.

## Phase 1 — Deploy LiveKit Server on EC2

**Where:** `54.177.107.107` (existing app box) — co-locate to avoid a new instance. Move to a dedicated box if CPU/bandwidth saturates.

**Compose addition** (`docker-compose.yml` on the host, alongside `matcha-backend`/`matcha-frontend`/`matcha-redis`):

```yaml
livekit:
  image: livekit/livekit-server:latest
  command: --config /etc/livekit.yaml
  network_mode: host         # WebRTC needs the host's UDP range
  restart: unless-stopped
  volumes:
    - ./livekit.yaml:/etc/livekit.yaml:ro
```

**`livekit.yaml`:**

```yaml
port: 7880                   # signaling (HTTP/WS)
rtc:
  tcp_port: 7881             # WebRTC over TCP fallback
  port_range_start: 50000
  port_range_end: 60000
  use_external_ip: true
keys:
  matcha_dev: <32+ char secret — generate with openssl rand -hex 32>
turn:
  enabled: true              # built-in TURN, v1 keeps clients on strict NAT working
  domain: hey-matcha.com
  tls_port: 5349
  udp_port: 3478
```

**EC2 security group:** open `7880/tcp`, `7881/tcp`, `3478/udp+tcp`, `5349/tcp`, `50000-60000/udp`.
**Nginx:** add `location /livekit/ { proxy_pass http://127.0.0.1:7880; proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"; }` so the Mac client can use one hostname.

**Env vars added to `matcha-backend`:**
- `LIVEKIT_URL=wss://hey-matcha.com/livekit`
- `LIVEKIT_API_KEY=matcha_dev`
- `LIVEKIT_API_SECRET=<same secret as livekit.yaml keys.matcha_dev>`

## Phase 2 — Backend

### New table

`server/alembic/versions/<next>_add_channel_broadcasts.py`:

```sql
CREATE TABLE channel_broadcasts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    started_by UUID NOT NULL REFERENCES users(id),
    livekit_room VARCHAR(120) NOT NULL,    -- "channel-{uuid}"
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    title VARCHAR(255)
);
CREATE INDEX idx_channel_broadcasts_active
    ON channel_broadcasts(channel_id) WHERE ended_at IS NULL;
```

One active row per channel at a time (enforced in code, not DB constraint, so we can soft-end and start a new one cleanly).

### New module

`server/app/core/services/livekit_service.py` — wraps `livekit-api` SDK (add `livekit-api>=0.6` to `server/requirements.txt`):

- `mint_token(identity, room, can_publish, can_subscribe, ttl=3600)` → JWT string
- `delete_room(room_name)` — calls LiveKit `RoomService.delete_room`
- `update_participant(room, identity, can_publish)` — toggles publish grant for promote/demote

### New routes

`server/app/core/routes/channel_broadcasts.py` (new file, mounted from `app/main.py`):

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/channels/{channel_id}/broadcast/start` | owner | Insert `channel_broadcasts` row, return publisher token + `livekit_url`. Push `broadcast.started` on channel WS. |
| `POST` | `/channels/{channel_id}/broadcast/stop` | owner | Set `ended_at`, call LiveKit `delete_room`. Push `broadcast.ended`. |
| `GET` | `/channels/{channel_id}/broadcast/token` | any member | Return subscriber-only token if a broadcast row is active. 404 if not. |
| `POST` | `/channels/{channel_id}/broadcast/promote` | owner | Body `{user_id}`. Mints publisher token for that user. Update LiveKit grants. Push `broadcast.publisher_changed` (with the new token in a per-user envelope only that user receives). |
| `POST` | `/channels/{channel_id}/broadcast/demote` | owner | Body `{user_id}`. Revoke publish grant on LiveKit; mint subscriber-only token; push `broadcast.publisher_changed`. |
| `GET` | `/channels/{channel_id}/broadcast` | any member | Returns `{ active: bool, started_at, started_by, publisher_user_ids[] }` for channel detail badge / "Live now" indicator. |

All token endpoints set room name `channel-{channel_id}` and identity `{user_id}` so LiveKit-side participant identity = our user_id (no extra mapping table).

### WS message types

Added to `channels_ws.py` outgoing types (received by Mac client):

- `broadcast.started` — `{channel_id, broadcast_id, started_by, started_at}`
- `broadcast.ended` — `{channel_id, broadcast_id}`
- `broadcast.publisher_changed` — `{channel_id, user_id, can_publish}` (broadcast to all members so the UI can render "X joined the stage")
- `broadcast.token_grant` — `{channel_id, token}` (per-user; only the affected user receives — used for live promote without polling)

Reuse the existing `room_members[channel_id]` set for routing.

### Permissions

Owner-gate via the existing helper at `channels.py:1696–1790` style: `SELECT role FROM channel_members WHERE channel_id = $1 AND user_id = $2`. Hard-fail if not `owner`. Subscriber-token endpoint requires any membership row.

## Phase 3 — macOS client

### SDK

Add LiveKit Swift SDK via SwiftPM. In `desktop/Matcha/Matcha.xcodeproj`:
- Package: `https://github.com/livekit/client-sdk-swift`, version `2.0.0+`
- Add `LiveKit` framework to the `Matcha` target

### New files

- `desktop/Matcha/Matcha/Services/BroadcastService.swift` — wraps `LiveKit.Room` connect/disconnect, surfaces a `@Published` participant list. Methods: `start(channelID:)`, `joinAsViewer(channelID:)`, `leave()`, `setMicEnabled(_:)`, `setCameraEnabled(_:)`. Reuses `APIClient.shared` for the `/broadcast/...` REST calls.
- `desktop/Matcha/Matcha/Views/Channels/BroadcastPanelView.swift` — SwiftUI view that:
  - Tile grid (LazyVGrid) of `VideoView` for each publishing remote participant + local publisher.
  - Bottom toolbar: mic toggle, camera toggle, "Leave" (viewer) / "End broadcast" (owner only).
  - Header: viewer count (subscriber count from LiveKit room) + "LIVE" pill.

### Edits to existing files

- `desktop/Matcha/Matcha/Views/Channels/ChannelDetailView.swift` (or wherever the channel page lives — confirm path during implementation):
  - Add toolbar `Button("Go Live")` gated on `channel.myRole == "owner"`. Calls `BroadcastService.shared.start(channelID:)`.
  - Show a "Live now" badge whenever `broadcast.active == true`.
  - When a broadcast is active, render `BroadcastPanelView` above the chat panel; hide it when ended.
- `desktop/Matcha/Matcha/Views/Channels/ChannelMembersListView.swift` (confirm name during implementation):
  - Owner-only contextual menu on each non-owner member while a broadcast is active: "Bring on stage" → `POST /broadcast/promote`. "Remove from stage" if already publishing.
- `desktop/Matcha/Matcha/Services/ChannelsWebSocket.swift`:
  - Handle the four new envelopes; route to `BroadcastService` (lifecycle + token grant).
- `desktop/Matcha/Matcha/Models/MWChannel.swift`:
  - Add `liveBroadcast: BroadcastSummary?` field. Decoded from `GET /broadcast` response when channel detail loads.

### Camera/mic permissions

- Add `NSCameraUsageDescription` and `NSMicrophoneUsageDescription` to `desktop/Matcha/Matcha/Info.plist`.
- BroadcastService prompts via standard AVFoundation flow on first publish.

## Phase 4 — web/iOS (deferred)

Same backend untouched. Add LiveKit JS SDK to `client/`. Wire the same `/broadcast/...` endpoints. Owner UI behind same role check. Out of scope for this plan.

## Open questions / decisions for v1

- **Moderator broadcasting?** Default to "owner-only starts; owner promotes anyone (including moderators)". If you want moderators to also be able to start, the role check is one-line.
- **Owner disconnect:** if owner's app loses connection during broadcast, do we auto-end after N seconds, or keep room open and let promoted publishers continue? Default: keep room open until owner explicitly ends or 30 min idle.
- **Concurrent broadcasts per channel:** enforce max 1 active in code (the start endpoint hard-fails if `ended_at IS NULL` row exists).
- **Bandwidth cap:** LiveKit defaults to ~1 Mbps per video publisher. Acceptable for v1; revisit if cost becomes an issue.

## Verification

1. **Deploy:** `docker compose up -d livekit` on EC2. `curl https://hey-matcha.com/livekit/` returns LiveKit version banner.
2. **Token mint:** unit test `livekit_service.mint_token` decodes with API secret + has expected grants. Integration test against a local `livekit-server` container hits `RoomService.list_rooms()` after `start`.
3. **Broadcast lifecycle:** authed `POST /channels/{id}/broadcast/start` → row in DB, WS `broadcast.started` received, `livekit_url` + token returned. `POST /broadcast/stop` → `ended_at` set, room deleted.
4. **End-to-end on macOS:** launch two builds (owner + viewer accounts in same channel). Owner clicks "Go Live", grants cam/mic. Viewer's BroadcastPanelView opens, plays owner's video. Owner promotes viewer; viewer's UI flips to publisher tile. Viewer count updates.
5. **Permission negative tests:** non-owner POST `/broadcast/start` → 403. Non-member GET `/broadcast/token` → 403.

## Plan review — gaps, issues, fixes (added on review pass)

### Critical (block ship)

1. **Nginx path for LiveKit signaling.** LiveKit's WebSocket endpoint is at `/rtc` on the server, not `/`. Mac client expects `wss://hey-matcha.com/livekit` to land directly at LiveKit signaling. Either:
   - (a) `proxy_pass http://127.0.0.1:7880/;` with location `/livekit/` → strips `/livekit` prefix; client URL `wss://hey-matcha.com/livekit` works
   - (b) Use a dedicated subdomain `livekit.hey-matcha.com` (cleaner, also helps separate TURN cert)
   Recommend (b) — gives one ALPN/HTTP/2 origin for media without colliding with the API path tree.

2. **Token refresh mid-broadcast.** TTL=1h. Long broadcasts will expire. LiveKit Swift SDK fires `Room.participantDisconnected` on token expiry. Add: server endpoint `POST /channels/{id}/broadcast/refresh-token` that re-mints the same identity's current grants. Mac `BroadcastService` schedules re-fetch at TTL−5min and calls `room.updateConnectOptions` (LiveKit SDK supports live token swap via `Room.updateLocalParticipant(token:)` in 2.x).

3. **LiveKit webhook receiver.** Without webhooks, server has no idea if owner closed app and the room emptied. Add `POST /webhooks/livekit` route — verify signature with `LIVEKIT_API_SECRET` per LiveKit's webhook docs. Handle:
   - `room_finished` → set `channel_broadcasts.ended_at`, push `broadcast.ended`
   - `participant_left` (when participant was the `started_by` user and is the last publisher) → end broadcast
   Update `livekit.yaml`:
   ```yaml
   webhook:
     api_key: matcha_dev
     urls:
       - https://hey-matcha.com/api/webhooks/livekit
   ```

4. **Force-unpublish on demote.** Revoking `canPublish` in token alone does NOT stop already-published tracks. Demote must also call `RoomService.mute_published_track(room, identity, track_sid, muted=True)` for each published audio+video track, OR `RoomService.remove_participant(room, identity)` to fully kick (more disruptive — they lose subscription). Recommend: server iterates the participant's tracks and force-unpublishes via `RoomService.update_subscriptions(..., subscribe=False)` and reissue a subscriber-only token.

5. **`matcha_work` feature flag gate.** Channels live under matcha-work. `feature_flags.py:7` shows `"matcha_work": False` by default. All `/broadcast/*` endpoints must check `companies.enabled_features.matcha_work=true` before issuing tokens. Reuse the same gate that channels.py already uses.

### Schema / infra

6. **TLS cert for LiveKit TURN/TLS port 5349.** Plan says `domain: hey-matcha.com` but doesn't specify cert. Either share existing nginx cert (mount as volume) or run certbot in livekit container. Document this in the deploy section.

7. **Docker `network_mode: host` consequences.** Conflicts with existing port allocations on the box. Inventory existing host-port bindings before deploy:
   - `matcha-frontend` 127.0.0.1:8082, `matcha-backend` 127.0.0.1:8002, `matcha-redis` 0.0.0.0:6379
   - LiveKit needs 7880, 7881, 3478, 5349, 50000-60000. No conflicts expected, but verify `ss -tulpn` first.

8. **Concurrent publisher cap.** Plan doesn't specify. LiveKit defaults to ~50 publishers/room. For the "host + a few guests" model, set `room.maxParticipants` or per-token cap. Recommend max 5 publishers; everyone else stays subscriber.

9. **Auto-end stale broadcasts.** Plan mentions "30 min idle" default but no implementation. With webhooks (#3) + `room_finished` event, this becomes free — LiveKit auto-closes empty rooms after `empty_timeout` (default 5 min). Set `empty_timeout: 1800` in livekit.yaml.

10. **Container/server restart cleanup.** If `matcha-backend` restarts mid-broadcast and we miss a webhook, `channel_broadcasts.ended_at` stays NULL. Add a startup task in `app/main.py` lifespan: `UPDATE channel_broadcasts SET ended_at = NOW() WHERE ended_at IS NULL AND started_at < NOW() - INTERVAL '6 hours'` (any broadcast older than that is definitely dead). LiveKit Server itself is durable; it'll surface live rooms via `RoomService.list_rooms()` so we can also reconcile on boot.

### Backend behavior

11. **Coexistence with existing `voice_signaling.py`.** Both currently dispatched in `channels_ws.py:14-15`. If a P2P voice call is active in a channel and owner clicks Go Live, what happens? Recommend: starting a broadcast emits `voice_kick_all` for any active P2P participants. Mutually exclusive: a channel is either in a P2P voice call OR a broadcast, not both.

12. **Title param + start endpoint body.** Schema has `title VARCHAR(255)` but no API contract. Add to `POST /broadcast/start` body: `{ title?: string }` so owner can label the broadcast ("Q&A with Maya from XYZ Co").

13. **WS event for late joiners.** Server WS push on connect should include current `liveBroadcast` state (server reads `channel_broadcasts WHERE ended_at IS NULL` for the channel and emits `broadcast.started` retroactively to a newly-connecting member who joins mid-broadcast). Otherwise late joiners see the channel but don't know to fetch a viewer token.

### Mac client

14. **LiveKit Swift SDK bundle size impact.** Pulls Apple's `WebRTC.framework` and ~50–100 MB to the .app bundle. Verify it doesn't break code-signing config or App Store size limits.

15. **macOS sandbox entitlements.** Info.plist usage strings are necessary but not sufficient. App also needs:
    - `com.apple.security.device.camera` and `com.apple.security.device.microphone` entitlements
    - `com.apple.security.network.client` (already enabled for HTTP)
    Verify at `desktop/Matcha/Matcha/Matcha.entitlements`.

16. **LiveKit Swift SDK reconnect behavior.** Built-in reconnect on transient network drops is on by default. No code needed but call out in plan: `Room.reconnectMode = .quick` for ≤30s drops, otherwise `.full`.

17. **Token grant on promote.** Plan says server pushes `broadcast.token_grant` per-user. Mac flow: `BroadcastService.handlePromotion(token:)` → `room.disconnect()` → `room.connect(url, token: newToken)`. LiveKit 2.x supports in-place token replace; confirm SDK version supports it.

18. **Empty-channel / ghost broadcasts on Mac.** If user backgrounds the app while broadcasting, macOS suspends WebSocket but LiveKit continues. They become a "ghost publisher" with no incoming media. Plan: on `NSApplication.willResignActive`, owner gets a sticky banner; on `willTerminate`, BroadcastService calls stop endpoint synchronously.

### Decisions locked (review pass)

- **Broadcasts available to any channel owner** — no paid-channel gate in v1
- **Owner-only initiates broadcast** — moderators cannot `POST /broadcast/start`. Owner can promote moderators as publishers
- **In-app live indicator only** — no macOS system notifications in v1. NotificationManager Redis pub/sub still used for in-app sidebar badge updates

## File checklist

New:
- `server/alembic/versions/<next>_add_channel_broadcasts.py`
- `server/app/core/services/livekit_service.py`
- `server/app/core/routes/channel_broadcasts.py` (mounted in `app/main.py`)
- `desktop/Matcha/Matcha/Services/BroadcastService.swift`
- `desktop/Matcha/Matcha/Views/Channels/BroadcastPanelView.swift`

Edit:
- `server/requirements.txt` — add `livekit-api>=0.6`
- `server/app/main.py` — mount new router
- `server/app/core/routes/channels_ws.py` — emit/relay 4 new message types
- `server/app/config.py` — `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` settings
- `desktop/Matcha/Matcha.xcodeproj/project.pbxproj` — add LiveKit SwiftPM dep
- `desktop/Matcha/Matcha/Info.plist` — camera + mic usage strings
- `desktop/Matcha/Matcha/Services/ChannelsWebSocket.swift` — new envelopes
- `desktop/Matcha/Matcha/Models/MWChannel.swift` — `liveBroadcast` field
- `desktop/Matcha/Matcha/Views/Channels/ChannelDetailView.swift` — Go Live button + live badge
- `desktop/Matcha/Matcha/Views/Channels/ChannelMembersListView.swift` — Bring-on-stage menu
- EC2 host `docker-compose.yml` + new `livekit.yaml`
- EC2 nginx config — `/livekit/` proxy block
