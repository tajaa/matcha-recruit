Here is Claude's plan:
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
Matcha Work — Chat-Driven Offer Letter Generation

Context

Build a new "matcha-work" module: a chat-driven, AI-powered document generator. Users type natural language and the
AI generates/amends structured offer letters, previewed as PDF in real-time. The canonical source of truth is
structured JSON (validated against Pydantic), not raw LLM text. Each chat turn produces field updates that merge
into the document state, then re-render to PDF via the existing WeasyPrint pipeline.

Phase 1 scope: Gemini only, offer letters only, admin + client access (feature-gated), draft + finalize (no
sending).

---

Architecture

User types "Create offer for John, Senior Eng, $180k, starts March 1"
↓
POST /matcha-work/threads/{id}/messages
↓
Gemini returns JSON: { reply: "...", updates: { candidate_name: "John", ... } }
↓
Validate updates against OfferLetterDocument (Pydantic)
↓
Merge into current_state, bump version, snapshot to mw_document_versions
↓
Render PDF via \_generate_offer_letter_html() + WeasyPrint → upload to S3
↓
Return assistant reply + updated state + pdf_url to frontend

---

New Files

┌──────────────────────────────────────────────────────────┬────────────────────────────────────────┐
│ File │ Purpose │
├──────────────────────────────────────────────────────────┼────────────────────────────────────────┤
│ server/alembic/versions/<hash>\_add_matcha_work_tables.py │ DB migration (4 tables) │
├──────────────────────────────────────────────────────────┼────────────────────────────────────────┤
│ server/app/matcha/models/matcha_work.py │ Pydantic request/response models │
├──────────────────────────────────────────────────────────┼────────────────────────────────────────┤
│ server/app/matcha/services/matcha_work_ai.py │ Gemini provider with structured output │
├──────────────────────────────────────────────────────────┼────────────────────────────────────────┤
│ server/app/matcha/services/matcha_work_document.py │ Document state, versioning, PDF gen │
├──────────────────────────────────────────────────────────┼────────────────────────────────────────┤
│ server/app/matcha/routes/matcha_work.py │ API endpoints │
├──────────────────────────────────────────────────────────┼────────────────────────────────────────┤
│ client/src/types/matcha-work.ts │ TypeScript interfaces │
├──────────────────────────────────────────────────────────┼────────────────────────────────────────┤
│ client/src/pages/MatchaWork.tsx │ Thread list page │
├──────────────────────────────────────────────────────────┼────────────────────────────────────────┤
│ client/src/pages/MatchaWorkThread.tsx │ Chat + PDF viewer workspace │
└──────────────────────────────────────────────────────────┴────────────────────────────────────────┘

Modified Files

┌──────────────────────────────────────┬───────────────────────────────────────────────────────────────────────┐
│ File │ Change │
├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────┤
│ server/app/core/feature_flags.py │ Add "matcha_work": False │
├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────┤
│ server/app/core/routes/admin.py │ Add "matcha_work" to KNOWN_PLATFORM_ITEMS (line 36) │
├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────┤
│ server/app/matcha/routes/**init**.py │ Import + mount matcha_work_router with require_feature("matcha_work") │
├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────┤
│ server/app/database.py │ Add CREATE TABLE IF NOT EXISTS for 4 tables in init_db() │
├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────┤
│ client/src/api/client.ts │ Add matchaWork API namespace │
├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────┤
│ client/src/App.tsx │ Add routes: /app/matcha/work and /app/matcha/work/:threadId │
├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────┤
│ client/src/components/Layout.tsx │ Add sidebar nav item with feature: 'matcha_work' │
└──────────────────────────────────────┴───────────────────────────────────────────────────────────────────────┘

---

1.  Database Schema (4 tables)

CREATE TABLE IF NOT EXISTS mw_threads (
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
title VARCHAR(255) NOT NULL DEFAULT 'Untitled Offer Letter',
task_type VARCHAR(40) NOT NULL DEFAULT 'offer_letter'
CHECK (task_type IN ('offer_letter')),
status VARCHAR(20) NOT NULL DEFAULT 'active'
CHECK (status IN ('active', 'finalized', 'archived')),
current_state JSONB NOT NULL DEFAULT '{}'::jsonb,
version INTEGER NOT NULL DEFAULT 0,
linked_offer_letter_id UUID REFERENCES offer_letters(id) ON DELETE SET NULL,
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mw_messages (
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
thread_id UUID NOT NULL REFERENCES mw_threads(id) ON DELETE CASCADE,
role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
content TEXT NOT NULL,
version_created INTEGER,
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mw_document_versions (
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
thread_id UUID NOT NULL REFERENCES mw_threads(id) ON DELETE CASCADE,
version INTEGER NOT NULL,
state_json JSONB NOT NULL,
diff_summary TEXT,
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
UNIQUE(thread_id, version)
);

CREATE TABLE IF NOT EXISTS mw_pdf_cache (
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
thread_id UUID NOT NULL REFERENCES mw_threads(id) ON DELETE CASCADE,
version INTEGER NOT NULL,
pdf_url TEXT NOT NULL,
is_draft BOOLEAN NOT NULL DEFAULT true,
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
UNIQUE(thread_id, version)
);

Indexes: company_id, created_by, (company_id, status) on threads; thread_id and (thread_id, created_at) on
messages; thread_id on versions and pdf_cache.

---

2.  Pydantic Models (server/app/matcha/models/matcha_work.py)

- OfferLetterDocument — all OfferLetterBase fields but all Optional (document builds incrementally)
- CreateThreadRequest — title?: str, initial_message?: str
- CreateThreadResponse — id, title, status, current_state, version, created_at
- SendMessageRequest — content: str (1-4000 chars)
- SendMessageResponse — user_message, assistant_message, current_state, version, pdf_url?
- ThreadListItem, ThreadDetailResponse, DocumentVersionResponse, RevertRequest, FinalizeResponse

---

3.  AI Service (server/app/matcha/services/matcha_work_ai.py)

Provider abstraction:
@dataclass
class AIResponse:
assistant_reply: str
structured_update: dict | None

class MatchaWorkAIProvider:
async def generate(self, system_prompt, messages, current_state) -> AIResponse: ...

class GeminiProvider(MatchaWorkAIProvider): # Uses google.genai SDK (same pattern as gemini_compliance.py) # response_mime_type="application/json" for forced JSON mode # temperature=0.2, sliding window of last 20 messages # Validates updates against OfferLetterDocument.model_fields.keys()

System prompt injects current_state JSON and instructs Gemini to return {"reply": "...", "updates": {...}}. Field
allowlist in prompt + server-side Pydantic validation as defense-in-depth.

Reuse from codebase:

- Client init pattern from gemini_compliance.py (lazy \_client property, LIVE_API env var fallback)
- \_clean_json_text() for stripping markdown fences

---

4.  Document Service (server/app/matcha/services/matcha_work_document.py)

Key methods:

- create_thread(company_id, user_id, title) → INSERT into mw_threads
- get_thread(thread_id, company_id) → SELECT with company scoping
- list_threads(company_id, status?) → paginated list
- add_message(thread_id, role, content, version_created?) → INSERT into mw_messages
- apply_update(thread_id, updates, diff_summary?) → merge into current_state with FOR UPDATE lock, bump version,
  create snapshot
- revert_to_version(thread_id, version) → load snapshot, create NEW version with old state
- generate_pdf(state, thread_id, version, is_draft, logo_src?) → check cache → render HTML → WeasyPrint → S3 upload
  → cache URL
- finalize(thread_id, company_id) → lock status, generate final PDF (no watermark), optionally create linked
  offer_letters row

Reuses:

- \_generate_offer_letter_html() from server/app/matcha/routes/offer_letters.py:886 (pure function, no route deps)
- get_storage().upload_file() from server/app/core/services/storage.py
- WeasyPrint HTML(string=html).write_pdf()

---

5.  API Endpoints (server/app/matcha/routes/matcha_work.py)

All gated via require_feature("matcha_work") + require_admin_or_client.

┌────────┬────────────────────────────────────┬──────────────────────────────────────────────────────────┐
│ Method │ Path │ Description │
├────────┼────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ POST │ /matcha-work/threads │ Create thread (optionally with initial message) │
├────────┼────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ GET │ /matcha-work/threads │ List threads (?status=active|finalized|archived) │
├────────┼────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ GET │ /matcha-work/threads/{id} │ Get thread with all messages │
├────────┼────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ POST │ /matcha-work/threads/{id}/messages │ Send message → AI response → state update → PDF │
├────────┼────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ GET │ /matcha-work/threads/{id}/versions │ List document versions │
├────────┼────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ POST │ /matcha-work/threads/{id}/revert │ Revert to version (creates new version) │
├────────┼────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ POST │ /matcha-work/threads/{id}/finalize │ Finalize (lock, remove watermark, link to offer_letters) │
├────────┼────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ GET │ /matcha-work/threads/{id}/pdf │ Get/generate PDF (?version=N) │
├────────┼────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ DELETE │ /matcha-work/threads/{id} │ Archive (soft delete) │
├────────┼────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ PATCH │ /matcha-work/threads/{id} │ Update title │
└────────┴────────────────────────────────────┴──────────────────────────────────────────────────────────┘

---

6.  Frontend

Types (client/src/types/matcha-work.ts)

TypeScript interfaces mirroring Pydantic models: MWThread, MWMessage, MWThreadDetail, MWSendMessageResponse,
MWDocumentVersion, MWFinalizeResponse.

API Client (add to client/src/api/client.ts)

matchaWork namespace with methods: createThread, listThreads, getThread, sendMessage, getVersions, revert,
finalize, getPdf, archiveThread, updateTitle.

Pages

MatchaWork.tsx — Thread list landing page:

- List of threads with status badges, version count, timestamps
- "New Offer Letter" button → creates thread → navigates to thread page
- Click row → navigate to /app/matcha/work/{threadId}

MatchaWorkThread.tsx — Main workspace (split layout):

- Left panel: Chat thread (scrollable messages + input box)
  - Role indicators (user/assistant/system)
  - Loading spinner while AI processes
  - Input disabled when finalized
- Right panel: PDF viewer (<iframe> with pdf_url)
  - Version selector dropdown
  - "Revert to this version" when viewing historical
  - "Finalize" button (with confirmation)
  - "Download PDF" link
- Responsive: mobile tabs toggle Chat ↔ Preview

Routes (in App.tsx)

<Route path="matcha/work" element={
<ProtectedRoute roles={['admin', 'client']} requiredFeature="matcha_work">
<MatchaWork />
</ProtectedRoute>
} />
<Route path="matcha/work/:threadId" element={
<ProtectedRoute roles={['admin', 'client']} requiredFeature="matcha_work">
<MatchaWorkThread />
</ProtectedRoute>
} />

Sidebar (in Layout.tsx)

Add to HR Ops section:
{ path: '/app/matcha/work', label: 'Matcha Work', roles: ['admin', 'client'], feature: 'matcha_work', icon: <...> }

---

7.  Implementation Order

1.  Alembic migration — 4 tables
1.  Pydantic models — matcha_work.py
1.  Document service — state management, PDF gen
1.  AI service — Gemini provider
1.  API routes — endpoints
1.  Server integration — **init**.py, feature_flags.py, admin.py
1.  Frontend types — TypeScript interfaces
1.  API client — add methods to client.ts
1.  Pages — MatchaWork.tsx, MatchaWorkThread.tsx
1.  Frontend integration — App.tsx, Layout.tsx

---

8.  Verification

1.  Run migration: cd server && alembic upgrade head
1.  Start server: cd server && python3 run.py
1.  Enable feature: via admin panel or direct DB update to companies.enabled_features
1.  Test API flow:

- POST /api/matcha/matcha-work/threads with initial_message
- POST /api/matcha/matcha-work/threads/{id}/messages with amendments
- GET /api/matcha/matcha-work/threads/{id}/pdf → verify PDF renders
- POST /api/matcha/matcha-work/threads/{id}/finalize → verify no watermark

5.  Frontend: navigate to /app/matcha/work, create thread, send messages, verify PDF updates
6.  Build check: cd client && npm run build — must pass with no new errors

---

Notes

- No task_type registry: Phase 1 is offer_letter only. The task_type column and CHECK constraint leave a seam for
  future types without over-engineering now.
- \_generate_offer_letter_html import: Import directly from the routes module (it's a pure function). If circular
  import issues arise, extract to server/app/matcha/services/offer_letter_pdf.py.
- PDF latency: WeasyPrint is sync/CPU-bound. Phase 1 runs inline. If slow, move to Celery in Phase 2.
- Context window: System prompt always contains full current_state. Message history uses sliding window (last 20).
  State is never lost.
- Provider abstraction: MatchaWorkAIProvider base class with GeminiProvider. Adding Claude later means implementing
  a ClaudeProvider with the same generate() interface.
