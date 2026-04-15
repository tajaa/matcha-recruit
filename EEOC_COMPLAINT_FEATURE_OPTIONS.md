# EEOC Complaint Feature — Architecture Decision Document

## Context

A company receiving an EEOC charge is facing a time-sensitive, high-stakes legal event: a strict 30-day position statement deadline, mandatory document production, and a permanent impact on the company record. This feature adds structured case handling — intake, deadlines, document organization, evidence gathering, AI-assisted position statement drafting, and determination tracking — to the business platform.

**Decisions already made:**
- **Full AI drafting** — AI drafts the position statement from intake facts, attached documents, and employee data
- **All four workflow capabilities** — charge intake + deadlines, position statement drafting workspace, evidence + document production, mediation + determination tracking

**Open question**: how the feature integrates with existing code. Two options below.

---

## What the Feature Does (common to both options)

Regardless of which architecture wins, the end-user experience is identical:

1. **Intake the charge** — user uploads the EEOC charge letter (PDF), enters charge number, filing date, agency (EEOC or state FEP like CA DFEH, NY SDHR), respondent entity, and complainant info. AI extracts allegations from the charge letter.
2. **Auto-compute deadlines** — position statement due date (typically charge receipt + 30 days), mediation election window (10 days), RFI response windows, right-to-sue 90-day clock. Shown prominently with countdown timers.
3. **Evidence workspace** — upload and tag documents by category: policies, comparator data, discipline history, pay records, performance reviews, email/chat logs, witness statements. Mark what's been produced to EEOC vs. internal-only.
4. **Position statement drafting** — structured editor with sections (company background, employment history of complainant, allegation-by-allegation response, conclusion). AI drafts each section from attached evidence, intake facts, and employee records pulled from the Employees module. User edits. Export as PDF.
5. **Determination + post-case tracking** — mediation election, conciliation offers, determination outcome (cause / no cause), right-to-sue letter receipt, post-determination decisions (settle / litigate / close).

The question is where this code lives.

---

## Option A: Extend ER Copilot

### What it means

ER Copilot (`server/app/matcha/routes/er_copilot.py`) already manages employee relations cases — harassment, discrimination, retaliation, wage-hour investigations. An EEOC charge is, by definition, one of these categories escalated to a formal external complaint. Under this option, EEOC handling becomes a **specialized mode** of an existing ER case.

**Model**: an ER case can exist internally (someone files an internal complaint), and if it escalates to an EEOC charge later, you **promote** the case to EEOC mode. Alternatively, if an EEOC charge arrives without a prior internal complaint, you **create an ER case in EEOC mode from the start**.

### Data model changes

Add columns to `er_cases`:

```
is_eeoc                        BOOLEAN DEFAULT false
eeoc_charge_number             TEXT
eeoc_agency                    TEXT ('EEOC' | 'CA_DFEH' | 'NY_SDHR' | ...)
eeoc_filing_date               DATE
eeoc_respondent                TEXT (legal entity name)
eeoc_received_at               TIMESTAMPTZ (when company received the charge)
eeoc_status                    TEXT ('intake' | 'responding' | 'investigating' | 'mediation' | 'determination' | 'right_to_sue' | 'resolved')
eeoc_allegations               JSONB (extracted from charge letter, each with text + category + response_status)
eeoc_position_statement_draft  TEXT (the working draft)
eeoc_determination             TEXT ('cause' | 'no_cause' | 'dismissed' | 'settled' | null)
```

New table for deadlines (generic, reused for non-EEOC deadlines in future):

```
er_case_deadlines
  id, case_id FK, deadline_type, due_date, status ('pending' | 'met' | 'missed'), notes
```

Extend `er_case_documents` with new `document_category` values for EEOC-specific types: `charge_letter`, `position_statement_draft`, `position_statement_final`, `comparator_data`, `discipline_record`, `rfi_response`, `determination_letter`, `right_to_sue_letter`, `mediation_agreement`.

No new analysis tables — reuse `er_case_analysis` with new `analysis_type` values: `eeoc_position_draft`, `eeoc_allegation_analysis`.

### Backend changes

- Extend `ERCaseCreate` Pydantic model with optional `eeoc_metadata` object
- Add routes under existing `/er/cases/*` namespace:
  - `POST /er/cases/{id}/eeoc/promote` — promote existing case to EEOC mode
  - `POST /er/cases/{id}/eeoc/intake` — upload charge letter, AI extract allegations
  - `POST /er/cases/{id}/eeoc/deadlines/compute` — compute deadlines from filing date + agency rules
  - `POST /er/cases/{id}/eeoc/draft-position-statement` — AI-draft the full position statement
  - `POST /er/cases/{id}/eeoc/draft-allegation-response` — AI-draft response to a specific allegation
  - `PATCH /er/cases/{id}/eeoc/position-statement` — save manual edits
  - `POST /er/cases/{id}/eeoc/export` — PDF export of position statement
  - `PATCH /er/cases/{id}/eeoc/determination` — record determination outcome
- Extend `er_analyzer.py` with EEOC-specific prompts:
  - `extract_eeoc_allegations(charge_letter_text)` — parses charge letter, returns structured allegations
  - `draft_position_statement(case, allegations, evidence, employee_data)` — generates full draft
  - `draft_allegation_response(allegation, evidence)` — generates response to one allegation
- New service: `server/app/matcha/services/eeoc_deadline_service.py` — computes deadlines based on agency rules (EEOC is 30 days; some state FEPs differ)

### Frontend changes

- `ERCopilot.tsx` page gets a new tab/filter: **EEOC Mode**
- New component: `client/src/components/er/EEOCIntakePanel.tsx` — charge upload, allegation extraction, deadline computation
- New component: `client/src/components/er/EEOCPositionStatementEditor.tsx` — structured editor with section-by-section AI drafting
- New component: `client/src/components/er/EEOCDeadlineTracker.tsx` — countdown timers for active deadlines
- New component: `client/src/components/er/EEOCDeterminationPanel.tsx` — determination + post-case tracking
- Extend `ERCaseCard.tsx` with an EEOC badge when `is_eeoc = true`
- Extend `ERDocumentList.tsx` with EEOC-specific document categories and a "produced to EEOC" toggle
- Feature flag: gated by existing `er_copilot` flag (no new flag needed)

### Pros

1. **Fastest to ship** — reuses ~80% of existing infrastructure (document storage, timeline, analysis tables, PDF export, audit log, company scoping, feature flag)
2. **Conceptually correct** — an EEOC charge IS an ER case that escalated. The data model already captures complainant/respondent/witnesses, category (discrimination, retaliation, etc.), and outcome — adding EEOC metadata extends this naturally
3. **Unified case history** — if a company has an internal complaint that escalates to an EEOC charge, it stays as ONE case record with a continuous timeline. Two separate modules would create a disjointed history
4. **Shared AI infrastructure** — `ERAnalyzer` already does timeline analysis, policy checks, discrepancy detection. EEOC prompts plug into the same streaming Gemini infrastructure
5. **Single feature flag** — users who have `er_copilot` enabled get EEOC capabilities automatically, no separate enablement step
6. **Unified search and filtering** — one place to search across all ER-related records. Counsel handling a case can see everything (internal + EEOC) in one view
7. **Lower maintenance burden** — one set of routes, one data model to evolve, one UI page to keep polished
8. **Inherits future improvements for free** — every time ER Copilot gets a bug fix or UX polish, EEOC cases benefit automatically

### Cons

1. **ER Copilot becomes heavier** — the UI has to accommodate two modes (internal investigation vs. EEOC mode). Requires careful UX to not overwhelm users who only use it for internal cases
2. **Schema overloads existing table** — `er_cases` gains 10+ EEOC-specific columns that are null for internal-only cases. This is cosmetically ugly but functionally fine with partial indexes
3. **Tight coupling to ER Copilot's future** — if you ever want to deprecate ER Copilot or split it apart, EEOC comes along with it
4. **Harder to price/package separately** — if you want to sell EEOC handling as a standalone premium add-on distinct from ER Copilot, gating it requires more granular flag logic
5. **Mixed terminology** — "case" (ER language) vs. "charge" (EEOC language). UI will need careful labeling

### Migration path if you change your mind

If this becomes too heavy over time, you can extract EEOC into its own module later:
- Create `eeoc_cases` table, copy EEOC-mode rows over
- Add a FK back to the original `er_cases` row for historical continuity
- Route the UI tab to the new module
- Achievable but non-trivial (~2 days of refactoring)

### Effort estimate

- **Backend**: ~600 lines added to existing files
- **Frontend**: 4 new components + 2 extended
- **Time to ship v1**: ~1 week

---

## Option B: New Sibling Module (`eeoc_cases`)

### What it means

Build a net-new module that sits alongside ER Copilot as a peer. Own table (`eeoc_cases`), own routes (`/eeoc/cases/*`), own service layer, own analyzer, own client page (`EEOCComplaints.tsx`), own feature flag (`eeoc_complaints`). Cases can optionally link to an ER case via FK but are independent entities.

### Data model

Four new tables:

```
eeoc_cases
  id UUID PK
  company_id UUID FK
  case_number TEXT (e.g. EEOC-2026-04-ABCD)
  linked_er_case_id UUID FK er_cases NULL  -- optional link if promoted from internal
  charge_number TEXT
  agency TEXT ('EEOC' | state FEP codes)
  filing_date DATE
  received_at TIMESTAMPTZ
  respondent_entity TEXT
  complainant_name TEXT
  complainant_email TEXT
  allegations JSONB  -- extracted from charge letter
  status TEXT  -- intake / responding / investigating / mediation / determination / right_to_sue / resolved
  position_statement_draft TEXT
  determination TEXT  -- cause / no_cause / dismissed / settled
  assigned_to UUID FK users
  created_at, updated_at TIMESTAMPTZ
  closed_at TIMESTAMPTZ

eeoc_case_documents
  id UUID PK
  case_id FK eeoc_cases
  document_type TEXT  -- charge_letter / position_statement / comparator_data / etc.
  filename TEXT
  file_path TEXT
  uploaded_by UUID
  produced_to_eeoc BOOLEAN  -- whether this has been shared with the agency
  uploaded_at TIMESTAMPTZ

eeoc_case_deadlines
  id UUID PK
  case_id FK eeoc_cases
  deadline_type TEXT  -- position_statement / mediation_election / rfi_response / etc.
  due_date TIMESTAMPTZ
  status TEXT  -- pending / met / missed
  notes TEXT

eeoc_case_analysis
  id UUID PK
  case_id FK eeoc_cases
  analysis_type TEXT  -- allegation_extraction / position_draft / evidence_summary
  result JSONB
  generated_at TIMESTAMPTZ
```

### Backend changes

- New route file: `server/app/matcha/routes/eeoc_complaints.py` (~1500–2000 lines)
- New service: `server/app/matcha/services/eeoc_case_service.py`
- New analyzer: `server/app/matcha/services/eeoc_analyzer.py` — Gemini prompts for allegation extraction, position statement drafting, evidence summary
- New deadline service: `eeoc_deadline_service.py`
- Register new router in the matcha module init
- Add feature flag `eeoc_complaints` to `server/app/core/feature_flags.py`
- Migration file creating four new tables with all indexes and foreign keys

### Frontend changes

- New page: `client/src/pages/app/EEOCComplaints.tsx`
- New component directory: `client/src/components/eeoc/`
  - `EEOCCaseCard.tsx`
  - `EEOCIntakeModal.tsx`
  - `EEOCDocumentList.tsx` (reimplementation of ERDocumentList pattern)
  - `EEOCTimelinePanel.tsx` (reimplementation of ERTimelinePanel pattern)
  - `EEOCPositionStatementEditor.tsx`
  - `EEOCDeadlineTracker.tsx`
  - `EEOCAllegationList.tsx`
  - `EEOCDeterminationPanel.tsx`
- New route in `App.tsx`: `/app/eeoc-complaints`
- New item in the Layout sidebar nav
- New API client: `client/src/api/eeoc.ts`

### Pros

1. **Clean separation of concerns** — EEOC workflow is distinct and specialized; keeping it separate means neither module accumulates two sets of mental models for maintainers
2. **Independent pricing and packaging** — can sell EEOC complaint handling as a standalone add-on or premium tier without touching ER Copilot
3. **Clean schema** — no nullable EEOC columns on ER cases. Each table stays focused
4. **Independent feature flag** — companies can enable EEOC without enabling ER Copilot, or vice versa
5. **Clearer terminology** — UI uses "charge" and "complaint" throughout, no overloading "case"
6. **Easier to evolve independently** — EEOC-specific workflow changes don't risk breaking ER Copilot and vice versa
7. **Easier to delete or pivot** — if EEOC doesn't pan out as a feature, removing it is cleaner

### Cons

1. **More code to write** — need to reimplement document lists, timelines, file upload, PDF exports, audit logging, company scoping. Probably 1500–2500 lines of backend + 6–8 React components vs. extending existing ones. Roughly 2× the work of Option A for v1
2. **Duplicated infrastructure** — two places to fix bugs in document handling, two places to enhance file uploaders, two places to add audit logging
3. **Disjointed case history** — an internal complaint that escalates to EEOC exists in two separate records with an FK link. Counsel has to switch between views to see the full history
4. **Separate AI analyzer** — new prompts, new Gemini integration, new streaming endpoints. Can't reuse `ERAnalyzer`'s existing timeline/discrepancy/policy-check logic without extracting it into a shared helper (extra refactoring)
5. **Another feature flag for admins to manage** — plus it requires the admin UI to understand the relationship between `er_copilot` and `eeoc_complaints`
6. **Sidebar crowding** — another top-level nav item. Users may not see the connection between ER Copilot and EEOC Complaints
7. **More surface area for bugs** — each duplicated piece of infrastructure is a place where ER and EEOC can drift out of sync (e.g., ER Copilot gains a new file type but EEOC doesn't)

### Migration path if you change your mind

Converting back to Option A later is painful:
- Merge `eeoc_cases` into `er_cases` with new columns, preserve IDs
- Migrate all documents, deadlines, analysis rows
- Deprecate the old routes with redirects
- Roughly 3–5 days of data migration work plus user communication

### Effort estimate

- **Backend**: ~1500–2500 lines net-new
- **Frontend**: 8 new components + new page + new API client
- **Time to ship v1**: ~2–3 weeks

---

## Comparison Matrix

| Dimension | Option A (Extend ER) | Option B (Sibling module) |
|-----------|---------------------|---------------------------|
| **Time to ship v1** | ~1 week | ~2–3 weeks |
| **Backend code** | ~600 lines added to existing files | ~1500–2500 lines net-new |
| **Frontend code** | 4 new components, 2 extended | 8 new components + page + API client |
| **Schema complexity** | 10 new columns on `er_cases` + 1 new table | 4 new tables |
| **Conceptual fit** | Strong (EEOC is a case category) | Neutral (EEOC is its own thing) |
| **Unified case history** | Yes (single record) | No (two records + FK) |
| **Independent pricing** | Harder (requires sub-flag logic) | Easy (own feature flag) |
| **Code reuse** | ~80% | ~30% |
| **Maintenance burden** | Lower (one module) | Higher (two parallel modules) |
| **Risk of drift between modules** | None | Real (two file systems to keep aligned) |
| **Inherits future ER Copilot improvements** | Automatically | No |
| **Migration path if wrong** | Easier (extract later, ~2 days) | Harder (merge later, ~3–5 days) |
| **Sidebar clutter** | None | +1 nav item |
| **Terminology clarity** | Mixed (case vs charge) | Clean |

---

## Recommendation: Option A (Extend ER Copilot)

The decisive factor is that **an EEOC charge is not a new entity — it's a specialized mode of an existing employee relations case**. Companies don't receive EEOC charges in a vacuum; they almost always correspond to a situation that was already or should have been an ER case internally. Keeping one unified record per situation reflects the operational reality and gives counsel/HR a single source of truth.

The speed-to-ship difference is significant — ~1 week vs. ~2–3 weeks for v1 — and the reuse of `ERAnalyzer`, document infrastructure, PDF export, and audit logging isn't just an engineering win. It means EEOC handling inherits every future improvement to ER Copilot automatically.

The main reason you might want Option B — **independent pricing** — can be mostly solved in Option A by adding a sub-flag (`er_copilot.eeoc_enabled`) if you want to gate it separately later.

The UI concern (ER Copilot getting heavier) is real but solvable with a clean tab/mode pattern: one tab for internal investigations, one tab for EEOC cases, with shared document and timeline views. The schema cosmetic concern (nullable columns) is not a functional issue — partial indexes make queries efficient regardless.

**When Option B would make sense instead:**
- If you're planning to sell EEOC complaint handling as a standalone SaaS product to companies that don't need general ER case management
- If your team is large enough that parallel ownership of two modules is cheaper than coordinating on a shared module
- If EEOC compliance regulations diverge so sharply from internal ER workflow that shared data structures become awkward (not the case today)

None of these apply right now, so Option A is the right call.

---

## Next Step

Tell me which option to implement and I'll produce a detailed implementation plan with:

**If Option A:**
- Specific column additions to `er_cases` migration
- New `er_case_deadlines` table migration
- EEOC-mode UI tab structure in `ERCopilot.tsx`
- Position statement editor component spec
- AI prompt additions to `er_analyzer.py`
- Deadline service with EEOC + state FEP rules
- PDF export template for the position statement

**If Option B:**
- Full new module scaffolding (routes, service, analyzer, migration)
- All 8 new React components with props and state
- Sidebar nav integration
- New feature flag plumbing
- AI prompts and streaming endpoints
- New API client
