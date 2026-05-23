# EEOC Position Statement Module — Implementation Plan

## Context

When a business receives an EEOC Charge of Discrimination, they have ~30 days to submit a **position statement** — a formal written response to each allegation. The EEOC publishes guidelines at https://www.eeoc.gov/employers/effective-position-statements: respond to each allegation, include factual background with dates, reference supporting documents by exhibit number, avoid boilerplate, invoke affirmative defenses where applicable.

Matcha needs a platform feature (top-level sidebar item, **not** a matcha-work project type) that lets a client:

1. Upload the received EEOC charge PDF/DOCX.
2. Have Gemini extract the claim structure (complainant, respondent, charge #, filing date, claim types, allegations).
3. Be guided through a fact-gathering chat with targeted follow-ups keyed to each allegation's claim type (Title VII / ADA / ADEA / retaliation / harassment).
4. Upload supporting exhibits (personnel files, policies, emails, training logs).
5. Generate a multi-section position statement that an attorney can review before submission.

Decisions (user-confirmed):
- Feature flag: **top-level `eeoc_position`** in `enabled_features`.
- Legal safeguard: **disclaimer checkbox before export**, plus per-section AI-assistance disclaimer text. No hard attorney-review lock at MVP.
- Applicable-policies section: **auto-pull from company handbook** in Phase 1 when the `policies` / `handbook` feature is enabled.
- Client scope: **web platform only**. This is a sidebar feature, NOT a matcha-work project. Mirrors ER Copilot / IR Incidents.

## Closest existing analog: ER Copilot

Mirror ER Copilot almost end-to-end. Read these before executing:
- `server/app/matcha/routes/er_copilot.py` — list/detail/document-upload/analysis endpoints.
- `server/app/matcha/routes/__init__.py` line 52 — `require_feature("er_copilot")` mount pattern.
- `server/app/matcha/services/er_document_parser.py` — PDF/DOCX → text + speaker-turn / timestamp detection.
- `server/app/workers/tasks/er_analysis.py` — Celery task pattern for background document parse.
- `client/src/pages/app/ERCopilot.tsx`, `client/src/pages/app/ERCaseDetail.tsx` — list / detail pages.
- `client/src/components/er/*` — document panel, streaming analysis panels (`ERSimilarCasesPanel.tsx` is the SSE-consumer reference).
- `client/src/components/ClientSidebar.tsx` lines 11–53 — Safety group where the new item lands.
- `client/src/App.tsx` lines 129–133 — router registration.

## Phase 1 (MVP — this plan)

### 1. Feature flag plumbing

Edit:

- `server/app/core/feature_flags.py` line 4 `DEFAULT_COMPANY_FEATURES`: add `"eeoc_position": False`.
- `server/app/core/routes/admin.py` line 298 `KNOWN_FEATURES`: add `"eeoc_position"` so the existing `PATCH /company-features/{company_id}` endpoint (line 914) can toggle it.
- Client `useMe().hasFeature("eeoc_position")` works with no change (reads JSONB).

### 2. Database (Alembic migration)

New migration under `server/alembic/versions/`. Tables:

```sql
CREATE TABLE eeoc_statements (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id         UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  created_by         UUID NOT NULL REFERENCES users(id),
  title              TEXT NOT NULL,
  charge_number      TEXT,
  filing_date        DATE,
  response_due_date  DATE,
  agency             TEXT NOT NULL DEFAULT 'EEOC',  -- EEOC | state_FEPA
  jurisdiction       TEXT,
  status             TEXT NOT NULL DEFAULT 'intake', -- intake|gathering|drafting|final|submitted
  claim_json         JSONB NOT NULL DEFAULT '{}'::jsonb,
     -- { complainant:{name,role,pronouns,dates_of_employment?},
     --   respondent:{legal_name,dba?},
     --   allegations:[{id,claim_type,summary,dates[],protected_class?}],
     --   claim_types:[...enum...],
     --   relief_sought:[], raw_text_excerpt }
  disclaimer_acknowledged_at TIMESTAMPTZ,
  submitted_at       TIMESTAMPTZ,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_eeoc_statements_company ON eeoc_statements(company_id);

CREATE TABLE eeoc_statement_documents (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  statement_id       UUID NOT NULL REFERENCES eeoc_statements(id) ON DELETE CASCADE,
  document_type      TEXT NOT NULL,  -- charge|policy|personnel_file|email|training|other
  filename           TEXT NOT NULL,
  file_path          TEXT NOT NULL,  -- S3 / storage URL
  mime_type          TEXT,
  file_size          BIGINT,
  extracted_text     TEXT,           -- cached parse output
  processing_status  TEXT NOT NULL DEFAULT 'pending', -- pending|done|error
  processing_error   TEXT,
  parsed_at          TIMESTAMPTZ,
  uploaded_by        UUID NOT NULL REFERENCES users(id),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_eeoc_docs_statement ON eeoc_statement_documents(statement_id);

CREATE TABLE eeoc_statement_facts (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  statement_id   UUID NOT NULL REFERENCES eeoc_statements(id) ON DELETE CASCADE,
  allegation_ref TEXT,                       -- id from claim_json.allegations
  fact           TEXT NOT NULL,
  source         TEXT NOT NULL,              -- user|doc|ai
  doc_id         UUID REFERENCES eeoc_statement_documents(id) ON DELETE SET NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE eeoc_statement_questions (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  statement_id  UUID NOT NULL REFERENCES eeoc_statements(id) ON DELETE CASCADE,
  question      TEXT NOT NULL,
  claim_type    TEXT,
  resolved      BOOLEAN NOT NULL DEFAULT FALSE,
  answer_fact_id UUID REFERENCES eeoc_statement_facts(id) ON DELETE SET NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE eeoc_statement_sections (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  statement_id   UUID NOT NULL REFERENCES eeoc_statements(id) ON DELETE CASCADE,
  order_index    INT NOT NULL,
  section_key    TEXT NOT NULL,   -- intro|company_bg|profile|facts|response|policies|conclusion
  title          TEXT NOT NULL,
  content        TEXT NOT NULL DEFAULT '',
  content_source TEXT NOT NULL DEFAULT 'ai',  -- user|ai
  pending_revision TEXT,
  pending_change_summary TEXT,
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_eeoc_sections_statement_order ON eeoc_statement_sections(statement_id, order_index);

CREATE TABLE eeoc_statement_messages (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  statement_id  UUID NOT NULL REFERENCES eeoc_statements(id) ON DELETE CASCADE,
  role          TEXT NOT NULL,  -- user|assistant
  content       TEXT NOT NULL,
  metadata      JSONB,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_eeoc_messages_statement ON eeoc_statement_messages(statement_id);
```

User confirmation required before running the migration per CLAUDE.md (production DB).

### 3. Server routes — `server/app/matcha/routes/eeoc_statements.py` (new)

Mirror `er_copilot.py`. Mount in `routes/__init__.py` with `dependencies=[Depends(require_feature("eeoc_position"))]`. All handlers use `require_admin_or_client` from `server/app/matcha/dependencies.py`.

Endpoints:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/eeoc/statements` | Create statement (title, optional charge_number, optional response_due_date). |
| `GET` | `/eeoc/statements` | List for company. |
| `GET` | `/eeoc/statements/{id}` | Fetch with sections, facts, open questions, documents, messages. |
| `PATCH` | `/eeoc/statements/{id}` | Update metadata (title, charge_number, filing_date, response_due_date, jurisdiction, status, disclaimer_acknowledged). |
| `DELETE` | `/eeoc/statements/{id}` | Hard delete. |
| `POST` | `/eeoc/statements/{id}/documents` | Multipart upload. `document_type` form field. 50 MB cap. Allowed: `.pdf .docx .doc .txt .csv .xlsx .xls .png .jpg .jpeg`. Celery task parses in background. |
| `GET` | `/eeoc/statements/{id}/documents` | List. |
| `DELETE` | `/eeoc/statements/{id}/documents/{doc_id}` | Delete. |
| `POST` | `/eeoc/statements/{id}/extract-claim` | (Idempotent) extract structured claim from the doc flagged `document_type='charge'`. Fills `claim_json` + seeds initial `eeoc_statement_questions` per claim type. |
| `POST` | `/eeoc/statements/{id}/facts` | Add a manually-entered fact. |
| `PATCH` | `/eeoc/statements/{id}/facts/{fact_id}` | Edit. |
| `DELETE` | `/eeoc/statements/{id}/facts/{fact_id}` | Remove. |
| `POST` | `/eeoc/statements/{id}/questions/{q_id}/resolve` | Mark resolved; optionally create a fact in the same call. |
| `POST` | `/eeoc/statements/{id}/chat` | SSE stream. Body: `{message}`. Persists user + assistant messages; emits directive events that mutate facts / questions / sections. |
| `POST` | `/eeoc/statements/{id}/generate` | SSE stream. Generates the full 7-section statement into `eeoc_statement_sections` (ordered). Returns final state. |
| `POST` | `/eeoc/statements/{id}/sections/{section_id}/accept-revision` | Promote `pending_revision` → `content`. |
| `POST` | `/eeoc/statements/{id}/sections/{section_id}/reject-revision` | Clear pending. |
| `PATCH` | `/eeoc/statements/{id}/sections/{section_id}` | User edit (sets `content_source='user'`). |
| `GET` | `/eeoc/statements/{id}/export/{fmt}` | Export PDF / DOCX / MD. `pdf` and `docx` require `disclaimer_acknowledged_at IS NOT NULL` → 412 otherwise. |

Section-revision, accept/reject, and user-edit semantics mirror the blog pattern shipped this week (`desktop/.../SectionEditorView.swift` + `project_service.py:apply_blog_directives`). Key invariants: AI revisions always stage as `pending_revision`; user edits do NOT clear pending.

### 4. Server services — `server/app/matcha/services/` (new)

- `eeoc_document_parser.py` — thin wrapper over `er_document_parser.ERDocumentParser`. Adds EEOC-specific post-processing for charge documents (regex extraction of charge # pattern `\d{3}-\d{4}-\d{5}`, filing date).
- `eeoc_service.py` — CRUD helpers (`create_statement`, `list_statements`, `get_statement_with_children`, `upsert_fact`, `resolve_question`, mutate_section under row lock mirroring `_mutate_sections`).
- `eeoc_ai.py` — Gemini prompts + calls (see §5).
- `eeoc_export.py` — PDF/DOCX render. Reuse WeasyPrint + `python-docx` tooling already used by `matcha_work.py:5078-5229`. Exports always include:
  - Cover page: title, charge #, response due date, respondent/complainant.
  - Body: 7 sections in order.
  - Final disclaimer paragraph: "This statement was prepared with AI assistance and requires attorney review prior to submission to the EEOC. All facts herein were provided by the respondent."
- Celery task in `server/app/workers/tasks/eeoc_document_parse.py` — invoked after document upload, mirrors `process_er_document`.

### 5. Gemini prompts (`eeoc_ai.py`)

Three distinct calls, each using `google.genai` with `response_mime_type="application/json"` and `_clean_json_text` helper (pattern from `matcha_work_ai.py:1116–1137` and `gemini_compliance.py:381–436`).

#### 5a. Claim extraction (`extract_eeoc_claim(text) -> dict`)

One-shot. Pydantic-validated schema:

```python
class EeocClaimExtraction(BaseModel):
    complainant: ComplainantInfo
    respondent: RespondentInfo
    charge_number: Optional[str]  # pattern \d{3}-\d{4}-\d{5}
    filing_date: Optional[date]
    agency: Literal["EEOC", "state_FEPA"]
    jurisdiction: Optional[str]
    claim_types: list[Literal[
        "title_vii_race", "title_vii_sex", "title_vii_religion",
        "title_vii_national_origin", "title_vii_color",
        "ada", "adea", "gina", "equal_pay",
        "retaliation", "harassment", "other"
    ]]
    allegations: list[AllegationInfo]  # {id, claim_type, summary(≤3 sentences), dates[], protected_class?}
    relief_sought: list[str]
    raw_text_excerpt: str  # first ~3000 chars
```

System prompt bans inference — only extract what's literally in the document. On parse failure, retry once with stricter wording.

#### 5b. Fact-gathering chat (`chat_turn(statement, user_message, history) -> StreamingDirectives`)

Static prompt baked with EEOC effective-statement guidelines + "say it, do it" rule (copy from blog prompt `matcha_work_ai.py:169`). Dynamic prompt injects per turn:

- Charge #, filing date, response_due_date countdown.
- Claim summary + claim_types.
- Allegations list (id, claim_type, summary).
- Facts gathered (compact bullets with ids + allegation_ref).
- Open questions (UNRESOLVED first, with ids + claim_type).
- Section ids with `USER-EDITED` / `HAS-PENDING-AI-SUGGESTION` flags.
- Supporting documents (file_id + label + category).
- Disclaimer acknowledged flag.

**Follow-up catalog keyed to claim_type** (the prompt enumerates):
- `title_vii_race / sex / religion / national_origin / color`: comparator analysis (similarly-situated employees outside class, identical treatment), legitimate non-discriminatory reason, documentary evidence thereof, decision-makers and their awareness of protected class, timeline.
- `ada`: accommodation request details, interactive-process timeline, essential job functions, undue hardship facts, medical documentation requested.
- `adea`: RIF selection criteria, age distribution, documentary evidence of non-age-based reason.
- `retaliation`: protected activity timeline, decision-maker knowledge thereof, adverse action specifics, intervening legitimate reasons.
- `harassment`: complaint channels, report dates, investigation steps, remedial action, Faragher-Ellerth affirmative defense (anti-harassment policy existed, reasonable complaint process, employee used it or unreasonably failed to).
- `equal_pay`: job duties / skill / effort / responsibility / working conditions comparison, affirmative defense factors (seniority, merit, production, other non-sex factor).

**Response envelope** (strict JSON):
```json
{"reply": str, "mode": "skill"|"general", "confidence": float,
 "updates": { /* zero or one of the directive keys below */ }}
```

**Directive keys**:
| Key | Shape | Behavior |
|---|---|---|
| `facts_update` | `{add:[{allegation_ref,fact,doc_id?}], update:[{id,fact?}], remove:[id]}` | Mutates `eeoc_statement_facts`. Source='ai' on add. |
| `questions_update` | `{add:[{question,claim_type}], resolve:[{id,answer_fact_id?}], remove:[id]}` | Mutates `eeoc_statement_questions`. |
| `section_draft` | `{"<section_id>": "<markdown>"}` | Empty/AI section → direct write; USER-EDITED → pending. |
| `section_revision` | `{section_id, content, change_summary}` | Always pending. |
| `sections_replace` | `[{section_key, title, content}]` | Replace full ordered list. Used by `/generate`. |
| `claim_update` | partial `claim_json` | Deep-merge. Used by extraction flow + AI-proposed corrections. |
| `status_update` | `{to: "gathering"\|"drafting"}` | Advance state machine; AI can only move forward along happy path. |

**Hallucination guardrails** (in prompt): never invent employee names, dates, email subject lines, or policy citations not present in `facts_gathered` or `supporting_docs`. When unsure, emit a `questions_update.add` instead of a section draft.

#### 5c. Final statement generation (`generate_position_statement(statement) -> sections`)

One-shot structured JSON. Schema: `{"sections":[{"section_key","title","content"}...]}` — 7 entries in this order:

1. **Introduction** — identifies respondent, charging party, charge #, agency; brief summary of respondent's position.
2. **Company Background** — industry, size, mission, relevant operational facts (pulled from company profile if available).
3. **Respondent / Complainant Profile** — employment history, role, dates, reporting relationships.
4. **Factual Background** — chronological narrative **drawn exclusively from `eeoc_statement_facts`**. Prompt forbids any fact not present there.
5. **Response to Allegations** — one markdown subsection per allegation (key = allegation id); rebuttal references exhibits by `supporting_docs.label`.
6. **Applicable Policies** — if `policies` feature enabled, pull relevant handbook sections via `handbook_service.get_policy_sections_for_categories(claim_types)`; else placeholder "Relevant policies attached as Exhibit N".
7. **Conclusion** — state the position, request no-cause finding, offer cooperation.

Each `content` ends with the AI-assistance disclaimer paragraph.

### 6. Web client — sidebar + router + pages

**Sidebar** — `client/src/components/ClientSidebar.tsx` lines 11–53: in the Safety group, add:
```tsx
{ to: '/app/eeoc-statements', icon: FileText, label: 'EEOC Statements' }
```
Gated via `hasFeature('eeoc_position')` (mirror how other Safety items are gated — check existing pattern in this file; if no client-side gate exists for ER Copilot, none needed here either since the server gates it).

**Router** — `client/src/App.tsx` lines 129–133, add:
```tsx
<Route path="eeoc-statements" element={<EEOCStatements />} />
<Route path="eeoc-statements/:statementId" element={<EEOCStatementDetail />} />
```

**New pages** under `client/src/pages/app/`:
- `EEOCStatements.tsx` — list view. Table columns: title, charge #, status, response-due countdown (red if <7 days), updated_at. Create button → modal.
- `EEOCStatementDetail.tsx` — detail view with tabs:
  1. **Intake** — upload charge, show extracted claim card, respondent/complainant, allegations list, response-due countdown, disclaimer checkbox (gates export).
  2. **Fact Gathering** — two-pane: (left) open questions list with inline answer → creates fact and resolves; (right) chat panel (SSE stream mirroring `ERSimilarCasesPanel.tsx`) + supporting-doc dropzone.
  3. **Draft** — 7-section editor. Each section: markdown editor, Accept/Reject banner for `pending_revision`, "Regenerate" button. Top: "Generate Full Draft" CTA (disabled until `claim_json` populated AND ≥1 fact per allegation).
  4. **Review & Export** — read-only render, disclaimer acknowledgment checkbox, export buttons (PDF / DOCX / MD). PDF / DOCX require acknowledgment.

**New components** under `client/src/components/eeoc/`:
- `EEOCClaimCard.tsx` — displays extracted claim structure.
- `EEOCDocumentList.tsx` — drag-drop upload (reuse `ERDocumentList.tsx` as reference).
- `EEOCFactsPanel.tsx` — open questions + facts list.
- `EEOCChatPanel.tsx` — SSE-driven chat (reuse pattern from `ERSimilarCasesPanel.tsx`).
- `EEOCSectionEditor.tsx` — markdown editor with pending-revision banner (port of desktop `SectionEditorView`).
- `EEOCNewStatementModal.tsx` — creation modal.

**New hooks** under `client/src/hooks/eeoc/`:
- `useEEOCStatement.ts` — fetch + mutations for a single statement (documents, facts, questions, sections).
- `useEEOCStatements.ts` — list.

**New API module** — `client/src/api/eeoc.ts` — wraps `/eeoc/*` endpoints.

### 7. Integration points

- **Handbook / policies** — `eeoc_ai.generate_position_statement` queries `handbook_service` (in `server/app/matcha/services/`) for policy sections matching `claim_types`. If the company doesn't have the `policies` feature enabled, fall back to placeholder text.
- **Company profile** — Section 2 pulls from `companies.name`, `companies.industry`, `companies.profile_json` where available.
- **Notifications (Phase 2)** — `response_due_date` hooks into existing notification/email services. Not in Phase 1.

## Critical files to modify / create

**Modify:**
- `server/app/core/feature_flags.py` (line 4)
- `server/app/core/routes/admin.py` (line 298)
- `server/app/matcha/routes/__init__.py` (mount new router)
- `client/src/components/ClientSidebar.tsx` (lines 11–53)
- `client/src/App.tsx` (lines 129–133)

**Create:**
- `server/alembic/versions/<ts>_eeoc_statements.py`
- `server/app/matcha/routes/eeoc_statements.py`
- `server/app/matcha/services/eeoc_service.py`
- `server/app/matcha/services/eeoc_ai.py`
- `server/app/matcha/services/eeoc_document_parser.py`
- `server/app/matcha/services/eeoc_export.py`
- `server/app/matcha/models/eeoc.py` (Pydantic models)
- `server/app/workers/tasks/eeoc_document_parse.py`
- `client/src/pages/app/EEOCStatements.tsx`
- `client/src/pages/app/EEOCStatementDetail.tsx`
- `client/src/components/eeoc/EEOCClaimCard.tsx`
- `client/src/components/eeoc/EEOCDocumentList.tsx`
- `client/src/components/eeoc/EEOCFactsPanel.tsx`
- `client/src/components/eeoc/EEOCChatPanel.tsx`
- `client/src/components/eeoc/EEOCSectionEditor.tsx`
- `client/src/components/eeoc/EEOCNewStatementModal.tsx`
- `client/src/hooks/eeoc/useEEOCStatement.ts`
- `client/src/hooks/eeoc/useEEOCStatements.ts`
- `client/src/api/eeoc.ts`

## Reused existing utilities (DO NOT reinvent)

- `server/app/matcha/services/er_document_parser.py:ERDocumentParser.extract_text_from_bytes()` — PDF / DOCX / RTF parsing.
- `server/app/core/services/storage.py:get_storage().upload_file()` — S3 upload with CDN URL return.
- `server/app/core/services/gemini_compliance.py:_clean_json_text()` — strips markdown fences from Gemini JSON output.
- `server/app/matcha/dependencies.py:require_feature()`, `require_admin_or_client` — auth/feature gating.
- `server/app/matcha/routes/er_copilot.py` — endpoint structure, SSE streaming shape.
- `client/src/components/er/ERSimilarCasesPanel.tsx` (lines 18–71) — SSE consumer pattern.
- WeasyPrint + `python-docx` pipeline used by `matcha_work.py` export endpoint.

## Verification plan (end-to-end, local)

Run against the local dev setup (`./scripts/dev.sh` — Matcha on :8001 / :5174).

1. **Flag:** admin hits `PATCH /api/company-features/{company_id}` with `{"feature":"eeoc_position","enabled":true}`. Confirm sidebar item appears under Safety.
2. **Create statement:** `POST /api/eeoc/statements` with `{"title":"Test 540-2025-01234"}` → 201; list view shows it.
3. **Upload charge:** drop a synthetic EEOC charge PDF (Title VII race allegation, comparator example) onto the Intake tab. Confirm `document_type='charge'` record created, Celery parses (or sync fallback), `extracted_text` populated.
4. **Extract claim:** server auto-fires `/extract-claim` after parse. Confirm `claim_json.claim_types=["title_vii_race"]`, allegations populated, ≥3 open questions seeded targeting comparator analysis / legitimate non-discriminatory reason / decision-maker knowledge.
5. **Chat turn — answer a question:** send "The complainant was terminated for poor performance after a 60-day PIP; the decision-maker was Jane Smith, the VP of Ops." Confirm server emits `facts_update.add` and `questions_update.resolve`. UI shows new fact + question crossed off.
6. **Adversarial: premature generate.** Before covering all allegations, hit "Generate Full Draft." Server must return 412 with `missing_preconditions: [...]` naming the unresolved questions. UI surfaces the list.
7. **Hallucination test:** in chat, ask "Write the factual background." Assert every name / date / policy / document referenced in the reply maps to an existing `eeoc_statement_facts` row or `eeoc_statement_documents.label`. If anything's invented, prompt needs tightening.
8. **Generate draft:** seed facts for all allegations, hit "Generate Full Draft". Confirm 7 sections with canonical keys (`intro, company_bg, profile, facts, response, policies, conclusion`), each ending in the disclaimer paragraph.
9. **Policy integration:** company has `policies` feature on with handbook loaded. Confirm Section 6 cites actual handbook policy text. Flip `policies` off → Section 6 uses the "attached as Exhibit N" placeholder.
10. **Pending revision:** in chat, "tighten Section 4." Confirm `pending_revision` populated on that section; Draft tab shows Accept/Reject banner; accept writes to content + clears pending.
11. **User-edit preservation:** hand-edit Section 5 in Draft tab. Save. In chat, ask "Any suggestions on Section 5?" — AI must respond in text only, not emit `section_draft` or `section_revision` for that id.
12. **Export gating:** hit PDF export on Review tab without checking disclaimer → 412. Check disclaimer → export succeeds. PDF includes cover page, all 7 sections, and final disclaimer. DOCX mirrors.
13. **Delete flow:** delete a document → referencing facts keep `doc_id=NULL` (not cascade-deleted). Delete the whole statement → all child rows removed.

## Out of scope (deferred)

- **Phase 2**: deadline notification emails / calendar sync, desktop app parity, per-allegation templates, legal-hazard audit (flag admissions, protected-activity-adjacent language).
- **Phase 3**: side-by-side claim vs response view, timeline builder, exhibit auto-numbering baked into export, state-FEPA flavors (CA DFEH, NY DHR) with state-specific prompt modules.

## Open questions still worth raising mid-implementation

1. **Document retention** — state FEPAs sometimes require 2-year retention of the submitted statement. Current schema has no `retained_until`; fine for Phase 1 but flag if user wants soft-delete or archive.
2. **Multi-company admin** — an admin spanning multiple companies can create statements for any; confirm list endpoint filters by `company_id` from context (it will by default via `require_admin_or_client`).
3. **Size cap** — 50 MB per document matches ER. If an EEOC exhibit bundle (e.g. a 200-page personnel file) exceeds this, the user needs to split. Raise only if it blocks real usage.
