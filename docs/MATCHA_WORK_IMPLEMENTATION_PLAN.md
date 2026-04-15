# MATCHA_WORK_AUDIT Implementation Plan

## Context

The web client (`matcha-work`) has performance issues in MatchaWorkThread.tsx (no memoization, wasteful re-renders, no SSE error recovery) and is missing the voice interview feature that the Mac app already uses against the same fully-built backend. This plan addresses both tracks.

---

## Track A: Performance Improvements

### A1: Extract Memoized MessageBubble Component
**Files:** New `client/src/components/matcha-work/MessageBubble.tsx`, modify `MatchaWorkThread.tsx`
- Extract message rendering (lines 306-354) into `React.memo` wrapped component
- `useMemo` around `<Markdown>` keyed on `m.content`
- Props: `{ message: MWMessage }`
- Includes ComplianceReasoningPanel + payer sources rendering
- Replace inline map in MatchaWorkThread with `<MessageBubble key={m.id} message={m} />`

### A2: Fix Scroll Behavior
**File:** `client/src/pages/work/MatchaWorkThread.tsx` (lines 75-77)
- Add `prevLenRef = useRef(0)`, only scroll when `messages.length > prevLenRef.current`
- Change dependency from `[messages]` to `[messages.length]`

### A3: Consolidate Mode Toggle State
**File:** `client/src/pages/work/MatchaWorkThread.tsx` (lines 30-43, 153-184)
- Replace 6 state vars → `const [togglingMode, setTogglingMode] = useState<'node'|'compliance'|'payer'|null>(null)`
- Read `nodeMode`/`complianceMode`/`payerMode` from `thread` object directly
- Single generic `handleModeToggle(mode)` handler replaces 3 duplicate functions

### A4: Preemptive Token Refresh for SSE
**Files:** `client/src/api/client.ts`, `client/src/api/matchaWork.ts`
- Add `ensureFreshToken()` export to client.ts: decode JWT `exp`, refresh if within 60s of expiry
- Call in sendMessageStream before fetch (async IIFE, AbortController still returned sync)

### A5: SSE Error Recovery
**Files:** `client/src/api/matchaWork.ts`, `client/src/pages/work/MatchaWorkThread.tsx`
- 90-second AbortController timeout on SSE fetch
- Differentiate timeout-abort vs user-abort in catch block
- Show error banner with dismiss/retry in MatchaWorkThread

---

## Track B: Voice Interview in Web Client

### B1: Audio Infrastructure
**New directory:** `client/src/services/audio/`

| File | Purpose |
|------|---------|
| `AudioCapture.ts` | AudioWorklet-based 16kHz mono PCM capture from mic |
| `audio-processor.worklet.ts` | Worklet processor: downsample native→16kHz, Float32→Int16 |
| `AudioPlayback.ts` | Web Audio API playback of 24kHz PCM chunks with gapless scheduling |
| `InterviewWebSocket.ts` | WebSocket client matching `server/app/protocol.py` binary protocol (0x01/0x02 prefixes) |

### B2: Interview UI Components
**New directory:** `client/src/components/matcha-work/interview/`

| File | Purpose |
|------|---------|
| `InterviewSetup.tsx` | Mode (interview prep / language lab), role selection (4 roles), duration, token display |
| `InterviewSession.tsx` | Live transcript, mic controls, timer, recording indicator |
| `SessionTimer.tsx` | MM:SS countdown, pulsing red < 60s |
| `TranscriptBubble.tsx` | React.memo message bubble (user/assistant/system/status) |

### B3: Integration Hook
**New file:** `client/src/hooks/interview/useInterviewSession.ts`
- State machine: `idle → starting → connecting → connected → recording → completed`
- Manages AudioCapture ↔ InterviewWebSocket ↔ AudioPlayback lifecycle
- Timer with auto-end at 0, idle detection (5min warning)
- Cleanup on unmount

### B4: API Integration & Routing
**New files:** `client/src/api/interview.ts`, `client/src/types/interview.ts`, `client/src/pages/work/InterviewPage.tsx`
- API: `createTutorSession()`, `listTutorSessions()` against existing `/interviews/tutor/sessions`
- Types: `SessionState`, `TranscriptMessage`, `InterviewConfig`, `TutorSessionSummary`
- Route: `/work/interview` as separate route under WorkLayout (NOT a matcha-work task type — UX is fundamentally different from text chat)
- InterviewPage: thin shell wiring hook to setup/session components

### B5: Token & Session Management
**Files:** `client/src/types/dashboard.ts`, `client/src/hooks/useMe.ts`
- Extend `MeUser` type with `interview_prep_tokens`, `allowed_interview_roles`, `beta_features`
- Add `refreshMe()` to useMe hook for post-session token count update
- Role filtering: candidates see only `allowed_interview_roles`, admin sees all
- Disable start when tokens = 0

---

## Design Decisions

1. **Separate route, not task type** — Voice interview UX is fundamentally different from text chat threads. `/work/interview` is cleaner than shoehorning into the thread system.
2. **AudioWorklet, not MediaRecorder** — We need raw PCM at 16kHz to match the backend protocol. MediaRecorder outputs encoded formats (WebM/Opus).
3. **Same binary protocol as Mac app** — Backend is already built and proven. No need for WebRTC or protocol changes.
4. **No new npm dependencies** — Web Audio API, WebSocket, MediaDevices are all native browser APIs.

---

## Implementation Order

**Track A first** (smaller, immediately impactful), then **Track B** (larger feature):

```
A1 → A2 → A3 → A4 → A5  (each independently committable)
B1 → B2 → B3 → B4 → B5  (sequential, single PR or per-phase PRs)
```

---

## Verification

**Track A:**
- React DevTools Profiler: type in input → MessageBubble components don't re-render
- Toggle modes → only header buttons re-render
- Send message → scroll fires once per new message, not on every state change
- Network tab: stale JWT triggers `/auth/refresh` before SSE stream
- DevTools offline mid-stream → error banner appears, not permanent spinner

**Track B:**
- Create session → API call fires, WebSocket connects, mic permission granted
- Speak → audio chunks sent (check Network/WebSocket frames), AI responds with audio playback
- Timer counts down → auto-ends session at 0
- Token count decrements after session creation
- Unmount during recording → all resources (AudioContext, MediaStream, WebSocket) cleaned up

---

## Critical Files Reference

| File | Role |
|------|------|
| `client/src/pages/work/MatchaWorkThread.tsx` | Track A primary target (425 lines) |
| `client/src/api/matchaWork.ts` | SSE streaming (147 lines) |
| `client/src/api/client.ts` | Token refresh (205 lines) |
| `client/src/types/matcha-work.ts` | MW types (137 lines) |
| `server/app/protocol.py` | Binary protocol reference (0x01/0x02) |
| `server/app/matcha/routes/interviews.py` | WebSocket endpoint + tutor session API |
| `server/app/core/services/gemini_session.py` | Gemini Live session wrapper |
| `server/app/matcha/models/interview.py` | Interview/tutor data models |
