# Matcha Work Audit: Web Client vs Mac App (MatchaTutor)

## Summary

The **web client** (`client/src/components/matcha-work/`) is a full AI-powered document generation and conversation platform with 8 task types, compliance reasoning, and PDF export. The **Mac app** (`matcha-features/ios/MatchaTutor/`) is a focused real-time voice interview coaching tool with language testing. They share the same backend auth but serve very different use cases, with minimal feature overlap.

---

## Feature Comparison

### Features ONLY in Web Client (matcha-work)

| Feature | Details |
|---------|---------|
| **AI Chat (general)** | Threaded conversations with streaming SSE responses |
| **Offer Letter Generation** | Structured benefits/contingencies, salary ranges, logo upload, PDF preview |
| **Performance Reviews** | Feedback collection, anonymous mode, rating scales, review request emails |
| **Workbook/Guide Creation** | Section-based content with image uploads |
| **Onboarding Documents** | Employee batch creation with Google Workspace provisioning |
| **Presentation/Slide Decks** | Slide generation with speaker notes, themed slides, PDF export |
| **Handbook Generation** | Upload analysis, compliance red flags, jurisdiction profiling, strength scoring, e-signature requests |
| **Policy Drafts** | Compliance-aware generation, location-specific rules |
| **Compliance Mode** | Jurisdiction requirements injected into AI context, decision tree visualization (ReactFlow) |
| **Payer Mode** | Medicare/insurance coverage data with similarity-scored policy sources |
| **Node Mode** | Internal company data context for AI responses |
| **Thread Management** | Pin, archive, filter by status (all/active/pinned/archived) |
| **Version Control** | Document versioning, revert to previous states |
| **PDF Export** | Multi-format export (PDF, markdown, structured JSON) |
| **Compliance Decision Tree** | Interactive flowchart showing reasoning chains with precedence types |
| **Compliance Reasoning Panel** | Category filtering, location selection, activated profile badges |
| **Token Usage Analytics** | Usage summary endpoint |

### Features ONLY in Mac App (MatchaTutor)

| Feature | Details |
|---------|---------|
| **Voice Interview Simulation** | Real-time voice sessions with 4 interview roles (VP People, CTO, Head Marketing, Junior Engineer) |
| **Language Lab** | English/Spanish fluency testing through natural conversation |
| **Real-time Audio I/O** | 16kHz PCM recording → WebSocket → 24kHz PCM playback, full-duplex |
| **Live Transcript** | Real-time chat bubbles (user/AI/system) during voice session |
| **Session Timer** | Countdown with low-time warnings, auto-disconnect at max duration |
| **Idle Protection** | 5-min idle timeout with 1-min warning before auto-disconnect |
| **Token System (candidate)** | 1 token per session, visible token badge, warning when depleted |
| **Role-Based Access** | Per-candidate allowed interview roles, admin sees all |
| **Duration Selection** | Short (2min), Medium (5min), Long (8min) session options |
| **Native Audio Engine** | AVAudioEngine with shared engine pattern, interrupt handling, Bluetooth support |
| **Keychain Auth** | Secure token storage via iOS Keychain |

### Shared Features (both platforms)

| Feature | Web | Mac |
|---------|-----|-----|
| **Auth** | JWT email/password, token refresh | Same auth system, same endpoints |
| **User Roles** | admin, client, candidate, employee | Same roles from same backend |
| **API Base** | `hey-matcha.com/api` | Same API base |
| **Dark Theme** | Configurable | Forced dark mode |

---

## Gap Analysis: What to Bring FROM Mac App INTO Web Client

### Priority 1: Voice Interview Prep (High Value)

The Mac app's core feature. Bringing this to web would make interview prep accessible without installing a native app.

**What's needed:**
- **WebRTC or MediaRecorder API** for browser microphone capture
- **WebSocket connection** to the existing interview backend (`/ws/interview/{id}`)
- **Audio playback** of AI responses (24kHz PCM → Web Audio API)
- **Transcript view** with real-time message bubbles
- **Session controls**: start/stop recording, end session, timer
- **Role selection UI**: VP People, CTO, Head Marketing, Junior Engineer
- **Duration selection**: Short/Medium/Long

**Reuse from Mac app backend:**
- Same WebSocket protocol (0x01/0x02 audio prefixes + JSON messages)
- Same `/tutor/sessions` API for session creation
- Same scoring/analysis pipeline

**New web components needed:**
- `InterviewPrepView.tsx` — role/duration selection + session launcher
- `ActiveSessionView.tsx` — transcript + controls + timer
- `useInterviewSession()` hook — WebSocket + audio state machine
- Audio utilities for PCM capture/playback in browser

### Priority 2: Language Lab (Medium Value)

Same architecture as interview prep but with language selection instead of role selection.

**What's needed:**
- Language selector (English/Spanish)
- Same audio/WebSocket infrastructure as interview prep
- Different system prompt on backend (already exists)

### Priority 3: Token System for Candidates (Low-Medium Value)

The Mac app shows interview prep tokens and enforces limits.

**What's needed:**
- Display token count in web UI header/sidebar
- Deduct tokens on session start
- Show warning when tokens depleted
- Token count already available via `/auth/me` → `interview_prep_tokens`

### Priority 4: Session Timer & Idle Protection (Include with P1)

Should come bundled with voice interview feature.

**What's needed:**
- Countdown timer component
- Low-time warning (pulsing red when < 60s)
- Idle timeout with warning toast
- Auto-disconnect on max duration

---

## Gap Analysis: What's Missing FROM Mac App (nice-to-have backports)

These are lower priority since the web client is the preferred system.

| Missing in Mac App | Effort | Notes |
|-------------------|--------|-------|
| Thread history/management | Medium | Mac app has no persistent thread list |
| Document generation | High | Not suited for mobile — web is better |
| Compliance features | High | Not suited for mobile — web is better |
| PDF preview | Medium | Not suited for mobile — web is better |
| Multiple AI modes (Node/Compliance/Payer) | Medium | Could add compliance context to interviews |

**Recommendation:** Don't backport document/compliance features to the Mac app. Its strength is focused voice interaction. If anything, backport session history so users can review past interview practice sessions.

---

## Implementation Plan: Voice Interview in Web Client

### Phase 1: Audio Infrastructure
1. Create `client/src/services/audio/` with:
   - `AudioCapture.ts` — MediaRecorder/AudioWorklet for 16kHz PCM capture
   - `AudioPlayback.ts` — Web Audio API for 24kHz PCM playback
   - `InterviewWebSocket.ts` — WebSocket client matching Mac app's binary protocol

### Phase 2: Interview UI Components
1. Create `client/src/components/matcha-work/interview/` with:
   - `InterviewSetup.tsx` — Role + duration selection (mirrors TutorHomeView)
   - `InterviewSession.tsx` — Active session with transcript + controls
   - `SessionTimer.tsx` — Countdown timer component
   - `TranscriptBubble.tsx` — Message bubble component

### Phase 3: Integration Hook
1. Create `client/src/hooks/interview/useInterviewSession.ts`
   - State machine: idle → starting → connecting → connected → recording → completed
   - Audio capture/playback lifecycle
   - WebSocket message handling
   - Timer management
   - Idle detection

### Phase 4: API Integration
1. Add to `client/src/api/matchaWork.ts`:
   - `createTutorSession(mode, language?, duration?, role?)`
   - `getTutorSessions()`
2. Add interview as a new task type in matcha-work threads, or as standalone route under `/work/interview`

### Phase 5: Token & Session Management
1. Surface `interview_prep_tokens` from AuthContext
2. Add token deduction flow
3. Session history view (past interviews with scores)

---

## Open Questions

1. **Should interview prep be a matcha-work task type or a separate route?** Adding it as a task type (`interview_prep`) keeps it in the thread system but the UX is fundamentally different (real-time voice vs. text chat). A separate `/work/interview` route may be cleaner.

2. **Audio format**: The Mac app uses raw PCM over WebSocket. For web, should we use the same protocol or switch to WebRTC for better browser compatibility?

3. **Gemini Live API**: The web client already has Gemini Live integration for video interviews. Should interview prep reuse that path instead of the Mac app's custom WebSocket protocol?

4. **Mobile web**: Will interview prep need to work on mobile browsers? If so, MediaRecorder API support varies — may need fallbacks.

---

## Performance Improvements: Porting Mac App Patterns to Web Client

The Mac app uses disciplined performance patterns (enum state machines, preemptive token refresh, timer lifecycle management) that the web client lacks entirely: 19 scattered `useState` calls, zero `React.memo`/`useMemo`, Markdown re-parsed every render, scroll fires on every state change, no SSE resilience.

### Files to Modify

- `client/src/pages/work/MatchaWorkThread.tsx` (425 lines) — main target
- `client/src/api/matchaWork.ts` (147 lines) — SSE streaming
- `client/src/api/client.ts` (205 lines) — token refresh
- **New**: `client/src/components/matcha-work/MessageBubble.tsx` — memoized message component

### Step 1: Extract Memoized MessageBubble Component

**Problem**: Every message re-renders on any state change (input typing, streaming status, mode toggles). Markdown parsing is expensive and runs every render for every assistant message.

**Fix**: Extract message rendering (lines 306-354 of MatchaWorkThread.tsx) into a `React.memo` component with `useMemo` on Markdown content.

- Props: `message: MWMessage`
- `React.memo` wrapper (messages are immutable once received)
- `useMemo` around `<Markdown>{m.content}</Markdown>` keyed on `m.content`
- Includes ComplianceReasoningPanel and payer sources rendering

### Step 2: Fix Scroll Behavior

**Problem**: `useEffect(() => { scrollIntoView() }, [messages])` fires on every messages array change, not just new messages.

**Fix**: Track `messages.length` and only scroll when it increases:
```ts
const prevLenRef = useRef(0)
useEffect(() => {
  if (messages.length > prevLenRef.current) {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }
  prevLenRef.current = messages.length
}, [messages.length])
```

### Step 3: Consolidate Mode Toggle State

**Problem**: 6 state variables for 3 mode toggles (nodeMode + togglingNode, complianceMode + togglingCompliance, payerMode + togglingPayer). Three near-identical handler functions.

**Fix**: Single `togglingMode` state + generic handler:
```ts
const [togglingMode, setTogglingMode] = useState<'node' | 'compliance' | 'payer' | null>(null)
```
Removes 2 state variables and ~20 lines of duplicate handler code.

### Step 4: Preemptive Token Refresh for SSE

**Problem**: `sendMessageStream` reads token from localStorage without checking expiry. If token expires mid-stream, it fails silently. The Mac app checks expiry *before* every request.

**Fix**:
- Add `ensureFreshToken()` to `client.ts` (parse JWT `exp` claim, refresh proactively)
- Call `await ensureFreshToken()` before SSE fetch in `matchaWork.ts`
- Retry once on auth failure

### Step 5: SSE Error Recovery

**Problem**: If SSE stream drops mid-response (network blip, server timeout), user sees permanent spinner.

**Fix**:
- 90-second timeout on SSE fetch via AbortController
- On network error, call `onError` with actionable message
- Show retry option in MatchaWorkThread.tsx when streaming fails

### Not Doing (intentionally skipped)

- **Message virtualization** — Thread lengths are short (<100 messages). Premature.
- **Request caching/dedup** — Not justified for matcha-work usage patterns.
- **WebSocket migration** — SSE is fine for text chat. Only needed for voice features.
- **useReducer** — State isn't complex enough. Consolidating toggles is sufficient.

### Verification

1. Open thread with 10+ messages → type in input → confirm message list does NOT re-render (React DevTools Profiler)
2. Toggle Node/Compliance/Payer → confirm only header buttons re-render
3. Send message → confirm scroll fires once (when assistant reply arrives)
4. Check Network tab during SSE → confirm token is fresh before stream starts
5. Kill network mid-stream (DevTools offline) → confirm error message appears, not permanent spinner
