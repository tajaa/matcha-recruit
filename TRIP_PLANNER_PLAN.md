# Channel Trip/Outing Planner

## Why

Channels currently support plain text + file attachments. Users want to collaboratively plan group trips/outings — proposing destinations, RSVPing, voting on where to go, scheduling dates, and getting AI-powered planning help. This adds the first "interactive message" type to channels.

## Feature Flow

1. Member proposes a trip → card appears inline in chat
2. **RSVP poll** — Yes / No / Maybe (all channel members)
3. **Destination vote** — only Yes-RSVP members vote on options (e.g., Disneyland vs Universal vs Disney World)
4. **Date poll** — members mark which dates work for them
5. **AI Trip Assistant** (Gemini) — budget estimates, itinerary, restaurant recs, packing list, weather
6. **Shared checklist** — group to-dos (book flights, reserve hotel, etc.)
7. Creator confirms destination + date → status moves to `confirmed`

---

## Database

### Migration: `server/alembic/versions/zzp6q7r8s9t0_add_channel_trips.py`

Also add DDL to `server/app/database.py` (~line 5220) for startup path.

### Modify `channel_messages`

```sql
ALTER TABLE channel_messages ADD COLUMN IF NOT EXISTS message_type VARCHAR(30) DEFAULT 'text';
ALTER TABLE channel_messages ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;
```

### New Tables

**`channel_trips`** — core entity

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | gen_random_uuid() |
| channel_id | UUID FK → channels | ON DELETE CASCADE |
| created_by | UUID FK → users | proposer |
| message_id | UUID FK → channel_messages | announcement message |
| title | VARCHAR(200) | |
| description | TEXT | |
| status | VARCHAR(20) | planning / confirmed / completed / cancelled |
| confirmed_destination_id | UUID nullable | FK → channel_trip_destinations |
| confirmed_date | DATE nullable | |
| budget_estimate_json | JSONB | AI-generated, cached |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

Index: `(channel_id, status)`

**`channel_trip_destinations`** — voteable options

| Column | Type |
|---|---|
| id | UUID PK |
| trip_id | UUID FK → channel_trips CASCADE |
| name | VARCHAR(200) |
| description | TEXT nullable |
| added_by | UUID FK → users |
| vote_count | INT DEFAULT 0 (denormalized) |
| created_at | TIMESTAMPTZ |

**`channel_trip_rsvps`** — Yes/No/Maybe

| Column | Type |
|---|---|
| id | UUID PK |
| trip_id | UUID FK CASCADE |
| user_id | UUID FK → users |
| response | VARCHAR(10) — yes/no/maybe |
| created_at | TIMESTAMPTZ |
| updated_at | TIMESTAMPTZ |

UNIQUE: `(trip_id, user_id)`

**`channel_trip_destination_votes`** — only yes-RSVP users

| Column | Type |
|---|---|
| id | UUID PK |
| destination_id | UUID FK CASCADE |
| user_id | UUID FK → users |
| created_at | TIMESTAMPTZ |

UNIQUE: `(destination_id, user_id)`

**`channel_trip_date_options`** — proposed dates

| Column | Type |
|---|---|
| id | UUID PK |
| trip_id | UUID FK CASCADE |
| date | DATE |
| added_by | UUID FK → users |

UNIQUE: `(trip_id, date)`

**`channel_trip_date_votes`** — availability per date

| Column | Type |
|---|---|
| id | UUID PK |
| date_option_id | UUID FK CASCADE |
| user_id | UUID FK → users |
| available | BOOLEAN DEFAULT true |

UNIQUE: `(date_option_id, user_id)`

**`channel_trip_checklist_items`** — shared to-dos

| Column | Type |
|---|---|
| id | UUID PK |
| trip_id | UUID FK CASCADE |
| text | VARCHAR(500) |
| is_completed | BOOLEAN DEFAULT false |
| assigned_to | UUID nullable FK → users |
| completed_by | UUID nullable FK → users |
| completed_at | TIMESTAMPTZ nullable |
| sort_order | INT DEFAULT 0 |
| created_by | UUID FK → users |
| created_at | TIMESTAMPTZ |

---

## Pydantic Models

New file: `server/app/core/models/channel_trips.py`

- `TripCreate(title, description, destinations: list[str])` — initial proposal
- `TripUpdate(title?, description?, status?)` — edit/advance status
- `TripResponse(id, title, description, status, destinations, rsvps, date_options, checklist_items, ...)` — full detail
- `TripListItem(id, title, status, rsvp_counts, created_at)` — compact for listing
- `RSVPRequest(response: Literal["yes","no","maybe"])`
- `DestinationCreate(name, description?)`
- `DateOptionCreate(date: date)`
- `ChecklistItemCreate(text, assigned_to?)`
- `ChecklistItemUpdate(text?, is_completed?, assigned_to?)`
- `TripAIRequest(request_type: Literal["budget","itinerary","restaurants","packing","weather"])`

---

## API Endpoints

New route: `server/app/core/routes/channel_trips.py`  
Mount in `server/app/main.py`

| Method | Path | Purpose |
|---|---|---|
| POST | `/channels/{cid}/trips` | Create trip (inserts trip + trip_card message) |
| GET | `/channels/{cid}/trips` | List trips (status filter) |
| GET | `/channels/{cid}/trips/{tid}` | Full detail |
| PATCH | `/channels/{cid}/trips/{tid}` | Update title/desc/status |
| DELETE | `/channels/{cid}/trips/{tid}` | Cancel trip |
| POST | `.../trips/{tid}/rsvp` | Upsert RSVP |
| POST | `.../trips/{tid}/destinations` | Add destination |
| POST | `.../trips/{tid}/destinations/{did}/vote` | Toggle vote (RSVP=yes only) |
| POST | `.../trips/{tid}/confirm-destination` | Lock winner |
| POST | `.../trips/{tid}/dates` | Add date option |
| POST | `.../trips/{tid}/dates/{did}/vote` | Mark available/unavailable |
| POST | `.../trips/{tid}/confirm-date` | Lock date |
| POST | `.../trips/{tid}/checklist` | Add item |
| PATCH | `.../trips/{tid}/checklist/{iid}` | Toggle/edit/reassign |
| DELETE | `.../trips/{tid}/checklist/{iid}` | Remove item |
| POST | `.../trips/{tid}/ai-assist` | SSE stream AI response |

All endpoints verify channel membership.

---

## WebSocket Events

Single event type `trip_update` with sub_type field. Broadcast via existing `manager._broadcast_to_room()`.

```json
{"type": "trip_update", "room": "<channel_id>", "sub_type": "rsvp_changed", "trip_id": "...", "user_id": "...", "response": "yes"}
{"type": "trip_update", "sub_type": "vote_changed", "trip_id": "...", "destination_id": "...", "vote_count": 5}
{"type": "trip_update", "sub_type": "date_vote_changed", "trip_id": "...", "date_id": "...", "available_count": 7}
{"type": "trip_update", "sub_type": "checklist_updated", "trip_id": "...", "item": {...}}
{"type": "trip_update", "sub_type": "status_changed", "trip_id": "...", "status": "confirmed"}
{"type": "trip_update", "sub_type": "destination_confirmed", "trip_id": "...", "destination_id": "..."}
```

Client: add `onTripUpdate` callback to `ChannelSocket` (channelSocket.ts line 67 switch block).

---

## Frontend

### New Files

| File | Purpose |
|---|---|
| `components/channels/TripCard.tsx` | Inline card in message stream — title, status badge, RSVP buttons, vote summary, date overlap, checklist progress |
| `components/channels/TripDetailPanel.tsx` | Full detail with tabs: Overview, Destinations, Dates, Checklist, AI Assistant |
| `components/channels/TripCreateModal.tsx` | Modal: title, description, initial destinations |
| `components/channels/TripAIAssistant.tsx` | Chat-like panel streaming Gemini responses |
| `hooks/useTrip.ts` | State + WS event handling (follows useVoiceCall pattern) |
| `api/channelTrips.ts` | All trip API functions |

### Message Render Integration

In ChannelView.tsx (line 449), branch on `msg.message_type`:

```tsx
if (msg.message_type === 'trip_card') {
  return <TripCard key={msg.id} tripId={msg.metadata.trip_id} channelId={channelId} />
}
```

Extend `ChannelMessage` type with optional `message_type` and `metadata` fields.

### Trip Creation

Icon button in composer area (alongside paperclip at line 524). Opens TripCreateModal.

---

## AI Integration

New file: `server/app/core/services/trip_ai.py`

Reuses `AIChatService` from `ai_chat.py`. Builds trip context and streams Gemini responses via SSE.

### Context Builder: `build_trip_context(trip_id)`

Queries trip and assembles: destination (or top candidates), group size (yes-RSVP count), member names, date range, company context.

### Prompt Templates

| Type | Focus |
|---|---|
| `budget` | Per-person breakdown: flights, hotel, food, activities, transport |
| `itinerary` | Day-by-day plan for group size + dates |
| `restaurants` | Cuisine variety, price ranges, group-friendly options |
| `packing` | Weather-appropriate, activity-specific |
| `weather` | Temperature, precipitation, preparation tips |

### Bonus AI Features

- **Smart checklist generation** — after destination confirmed, auto-generate starter to-dos
- **Date conflict resolution** — when no perfect date, suggest best compromise with reasoning
- **Group preference synthesis** — summarize preferences mentioned in chat

---

## Implementation Order

1. Alembic migration + DDL in database.py
2. Pydantic models (`server/app/core/models/channel_trips.py`)
3. REST endpoints (`server/app/core/routes/channel_trips.py`)
4. WS integration (broadcast trip_update events)
5. AI service (`server/app/core/services/trip_ai.py`)
6. Client API (`client/src/api/channelTrips.ts`)
7. Client socket (add `onTripUpdate` to ChannelSocket)
8. `useTrip` hook
9. UI components: TripCreateModal → TripCard → TripDetailPanel → TripAIAssistant
10. Wire into ChannelView message rendering + composer

## Files to Modify

- `server/app/database.py` (~line 5220) — DDL + modify channel_messages
- `server/app/core/routes/channels_ws.py` — import manager for broadcasts
- `server/app/main.py` — mount trip router
- `client/src/pages/work/ChannelView.tsx` (line 449) — message_type branching
- `client/src/api/channelSocket.ts` (line 67) — trip_update case
- `client/src/api/channels.ts` — extend ChannelMessage type

## New Files

- `server/alembic/versions/zzp6q7r8s9t0_add_channel_trips.py`
- `server/app/core/models/channel_trips.py`
- `server/app/core/routes/channel_trips.py`
- `server/app/core/services/trip_ai.py`
- `client/src/api/channelTrips.ts`
- `client/src/hooks/useTrip.ts`
- `client/src/components/channels/TripCard.tsx`
- `client/src/components/channels/TripDetailPanel.tsx`
- `client/src/components/channels/TripCreateModal.tsx`
- `client/src/components/channels/TripAIAssistant.tsx`
