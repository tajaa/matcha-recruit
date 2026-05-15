# Matcha Work — Discipline Project (Document-First)

Companion to `DISCIPLINE_ENGINE_PLAN.md`. That plan is the
HRIS-backed engine for full-platform tenants (escalation logic,
look-back math, employee DB lookups). This plan is the
**lightweight, document-first** version that runs as a new project
type inside Matcha Work — no synced employee DB, no escalation
engine. The user describes a situation, the AI drafts a formal
warning, the user signs it (digitally or physically), done.

## Context

Matcha Work already has 6 project types: `general`, `presentation`,
`recruiting`, `blog`, `collab`, `consultation`
(`server/app/matcha/services/project_service.py:16`). Each one is a
`mw_projects` row with a `project_type` discriminator + a
type-specific `project_data` JSONB shape and an AI system prompt
keyed on the type. Adding `discipline` follows that exact shape.

The user need: an HR rep or manager wants to issue a single
disciplinary action without setting up the full HR product. They
shouldn't have to import an employee CSV, configure look-back rules,
or wire integrations. They want: open project → answer a few
prompts → review the AI-drafted document → sign it (digital or
physical) → done. The output is a polished PDF (and an audit trail
inside the project), regardless of which signing path they take.

The intended outcome: a discipline workflow that's
indistinguishable in feel from the existing blog/consultation flows
for matcha-work users — a focused project with chat on one side and
the live document preview on the other — but with the e-sig step
plus the "Mark as Refused" fallback baked in.

## Where this lives vs. the platform engine

| | Platform Discipline Engine | Matcha Work Discipline Project |
|---|---|---|
| Synced employee DB | Required (`employees` table) | Not required (free-text employee name) |
| Escalation engine | Yes (verbal → written → final) | No (user picks the level) |
| Look-back math | Yes (auto expiry sweep) | No (each project is self-contained) |
| Pre-term integration | Yes (feeds `scan_consistency`) | No (lives only in `mw_projects`) |
| Surface | Full platform sidebar entry | One-of-many Matcha Work project type |
| Tier | Bespoke / full-platform feature | Available to any matcha-work user (free or paid) |

A customer can use both: matcha-work for one-off documents, the
platform engine when they're operating at scale with the full
HRIS. They don't share data unless we explicitly bridge them later
(out of scope for v1).

## Data model

### New project type

`server/app/matcha/services/project_service.py`:

- Extend `_ALLOWED_PROJECT_TYPES` with `"discipline"`.
- New `_seed_discipline_data(extra)` returning the per-project state
  blob (see schema below).

### `project_data` shape (JSONB on `mw_projects`)

```json
{
  "employee": {
    "name": "Jane Doe",
    "title": null,
    "department": null,
    "manager_name": null,
    "manager_email": null,
    "employee_email": null
  },
  "infraction": {
    "category": "attendance",
    "category_label": "Attendance",
    "occurred_on": "2026-04-26",
    "summary": "Three unexcused absences in the past 30 days.",
    "severity": "moderate",
    "evidence_urls": []
  },
  "level": "written_warning",
  "draft_status": "drafting",
  "meeting_held_at": null,
  "signature": {
    "method": null,
    "envelope_id": null,
    "requested_at": null,
    "signed_at": null,
    "refused_at": null,
    "refusal_notes": null,
    "signed_pdf_storage_path": null
  },
  "delivered_status": "draft"
}
```

`level` values: `verbal_warning | written_warning | final_warning | termination_notice`. Free-text user choice; no escalation engine
runs.

`draft_status` values: `drafting | review | meeting_scheduled |
pending_signature | signed | refused | physically_signed`.

`delivered_status` is the user-visible bucket for the project list:
`draft | active | closed`.

The document content itself lives in the existing `mw_projects.sections`
JSONB (the same column used for blog/recruiting/general project
content). The AI emits sections like:
- `header` (employer letterhead, employee name, date, level)
- `incident_description`
- `expected_changes`
- `consequences`
- `signature_block`

Sections are editable in the project detail view exactly the way
blog sections are today — same `MWProjectSection` Codable on the
desktop side, same edit endpoints.

### No new tables

No new SQL tables. Everything fits into `mw_projects.project_data`
+ `mw_projects.sections` + the existing `mw_project_files` table
(for evidence uploads + the final signed PDF).

### Schema migration

Pure additive — no DB DDL needed. The only "migration" is updating
`_ALLOWED_PROJECT_TYPES` and adding the seed function. Skips the
manual-prod-approval step.

## Backend changes

### `project_service.py`

- Add `_seed_discipline_data` matching the JSONB shape above.
- Branch in `create_project` on `project_type == "discipline"` to
  use the seed.

### Discipline AI system prompt (`matcha_work.py`)

Mirrors the existing blog system-prompt branch. New helper that
returns the prompt:

> "You are an HR drafting assistant inside a Discipline Project.
>  Your job is to interview the user (one question at a time, never
>  drown them) to capture: the employee's name + email, what
>  happened (time, place, witnesses if any), severity (minor /
>  moderate / severe), and which discipline level they want to
>  issue (verbal / written / final / termination). When you have
>  enough signal, emit `discipline_outline` to seed the document
>  sections, then iterate on `discipline_section_draft` /
>  `discipline_sections_replace` directives the same way blog drafts
>  work. Use a neutral, factual tone — never speculate about
>  motive, never add allegations the user didn't supply, and never
>  promise a specific corrective outcome."

`project_type_hint == "discipline"` routing already has the
infrastructure — `matcha_work.py:1394` shows the
`_skip_project_sections_sync` set; add `"discipline"` to it so the
AI's directives go through the same blog-style sync that already
works.

### New endpoints (small companion router or fold into matcha_work)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/matcha-work/projects/{id}/discipline/meeting-held` | Stamp `meeting_held_at`. Required gate before `/signature/request`. |
| `POST` | `/matcha-work/projects/{id}/discipline/signature/request` | Body `{employee_email}` → calls `SignatureProvider.send` (one-off, no template), records `envelope_id`, sets `draft_status='pending_signature'`. |
| `POST` | `/matcha-work/projects/{id}/discipline/signature/refuse` | Body `{notes}` → sets `draft_status='refused'`, stamps `refused_at`, `delivered_status='closed'`. |
| `POST` | `/matcha-work/projects/{id}/discipline/signature/upload-physical` | Multipart upload of the scanned signed PDF → stores via existing `mw_project_files` flow, sets `draft_status='physically_signed'`, `delivered_status='closed'`. |
| `POST` | `/matcha-work/signature/webhook` | Provider webhook — flips `draft_status='signed'`, downloads provider PDF to `mw_project_files`. |

PDF export is **already wired**: `GET /matcha-work/projects/{id}/export/pdf` (matcha_work.py:5342). Same WeasyPrint
helper renders this project type's sections into a clean branded PDF.
The fix shipped in commit `65252a7` already surfaces the export menu
on blog projects in the desktop app — we'll mirror the same menu on
discipline projects.

### Where the signed document lives

After signing (any method), the signed PDF lands in
`mw_project_files` with kind `signed_discipline_doc`, scoped to the
project. The user finds it in the project detail right pane (Files
tab) — same place files always live for matcha-work projects.

The list endpoint already returns `mw_project_files` entries; the
desktop app already renders them. No new UI needed for "where can
the rep find the signed document" — answer: it's in the project's
Files panel.

### Signature provider

Same `SignatureProvider` interface laid out in
`DISCIPLINE_ENGINE_PLAN.md`. Implemented once, used by both the
platform engine and this matcha-work flow:

```
class SignatureProvider(Protocol):
    async def send(self, *, recipient_email: str, recipient_name: str,
                   document_pdf: bytes, subject: str) -> SendResult:
        ...
    async def fetch_signed_pdf(self, envelope_id: str) -> bytes:
        ...
```

DocuSign / Dropbox Sign concrete impl shared. Webhook URL is
single — both flows route into it via `envelope_id` lookup against
either `mw_projects.project_data->signature->envelope_id` (this flow)
or `progressive_discipline.signature_envelope_id` (engine flow).

## Frontend (matcha-work, both web and desktop macOS)

### Project type creation UX

In the existing matcha-work project picker (the `+ New Project`
menu), add **"Disciplinary Action"** alongside Blog, Recruiting,
etc.

- Web: `client/src/pages/work/MatchaWorkList.tsx` — add to the
  type list.
- Desktop: `desktop/Matcha/Matcha/Views/MatchaWork/ProjectListView.swift:34`
  — already has `["general", "presentation", "recruiting", "collab"]`.
  Add `"discipline"`. New icon (e.g. `exclamationmark.shield`).

### Intake step (chat or form, both supported)

Same pattern as the new-blog intake. On project create the AI greets:

> "Let's get started. Who is the employee receiving this action,
>  and what's their email if you'd like to send the document
>  digitally?"

Subsequent turns gather the situation, severity, and level. The
AI emits `discipline_outline` once it has enough signal; the
sections appear in the document panel.

For users who want to type into a form instead of chatting, the
project header's right pane has a "Quick Setup" tab with the same
fields (employee, infraction summary, level). Saving that tab pokes
`mw_projects.project_data` directly — no AI roundtrip — and
auto-emits the seed sections.

### Document review

Same blog-style three-pane layout users already know:
- Left: sections list + chat.
- Center: section editor.
- Right: live PDF preview (existing `PreviewPanelView` rendering),
  Files tab, History tab.

### Execution step

Once the user is ready to send:

1. **Meeting confirm gate** — modal: *"Have you conducted the
   disciplinary meeting?"* `Yes` → moves to signature choice.
   `Not yet` → returns to draft. Pre-fills `meeting_held_at` on
   `Yes`.
2. **Signature choice** — three buttons:
   - **Send Digitally** — email field (pre-filled from
     `project_data.employee.employee_email`). Click sends via
     `SignatureProvider`. UI moves to `Awaiting Signature` state
     showing the envelope ID and a "Resend" link.
   - **Mark as Refused** — modal asks for notes (min 20 chars),
     stamps `refused_at`, closes the project. Project list shows it
     under Closed with a "Refused" chip.
   - **Download PDF for In-Person Signing** — exports the current
     state (reuses existing PDF export). After the meeting, an
     **Upload signed scan** button accepts the PDF; saves it as
     `signed_discipline_doc` under the project's Files.

### Signed PDF discoverability

After signing, the project shows a banner: *"Signed by Jane Doe on
Apr 28, 2026 — Download Signed PDF"*. The button hits a download
helper that points at the latest `signed_discipline_doc` in
`mw_project_files`. Project state moves to `Closed`.

### Status chips in the project list

- `Draft` — gray
- `Awaiting Signature` — amber
- `Signed` — emerald
- `Refused` — red
- `Physically Signed` — emerald (with a small "physical" icon)

Appears next to the project type chip in MatchaWorkList /
ProjectListView.

## Critical files

| File | Change |
|------|--------|
| `server/app/matcha/services/project_service.py:16` | Add `"discipline"` to `_ALLOWED_PROJECT_TYPES`; new `_seed_discipline_data`. |
| `server/app/matcha/routes/matcha_work.py` | New discipline system prompt branch; new `/discipline/*` endpoints; webhook handler shared with platform engine. |
| `server/app/matcha/services/signature_provider.py` (new, shared) | `SignatureProvider` interface + one concrete impl (DocuSign or Dropbox Sign). Imported by both this flow and the platform engine. |
| `client/src/pages/work/MatchaWorkList.tsx` | New-project menu adds Discipline. |
| `client/src/pages/work/ProjectView.tsx` | Type-switch picks discipline-specific right pane (Quick Setup tab + Execution buttons). |
| `client/src/features/discipline-project/` (new) | `QuickSetupTab.tsx`, `MeetingConfirmModal.tsx`, `SignatureChoice.tsx`, `RefusalModal.tsx`, `SignedBanner.tsx`. |
| `desktop/Matcha/Matcha/Views/MatchaWork/ProjectListView.swift:34` | Add `"discipline"` to the types array; new icon. |
| `desktop/Matcha/Matcha/Views/MatchaWork/DisciplineEditorView.swift` (new) | Mirrors `BlogEditorView` for discipline projects — chat + sections + PDF preview + execution buttons. Reuses the same export menu pattern committed in `65252a7`. |
| `desktop/Matcha/Matcha/ViewModels/ProjectDetailViewModel.swift` | New methods: `confirmMeetingHeld()`, `requestSignature(email:)`, `markRefused(notes:)`, `uploadPhysicalSignedPDF(_:)`. |
| `desktop/Matcha/Matcha/Models/MatchaWorkModels.swift` | `MWProjectData` extension to type the discipline shape (or stay loose with `[String: AnyCodable]?` and gate behind a small typed accessor). |

## Backward compat

Pure additive. No migration. No schema break. Existing project types
keep working; the new discipline type is invisible until a user
picks it. Web client and desktop client both gracefully ignore
unknown project types today — verified by reviewing the project
selector switch.

## Build order

1. **Backend**: `_ALLOWED_PROJECT_TYPES` + seed + system prompt + 4
   new endpoints + webhook. Tests for create / meeting-held / refuse
   / physical upload.
2. **`SignatureProvider` abstraction**: implement once (shared with
   platform engine plan). Wire to webhook URL. Test in provider
   sandbox.
3. **Web**: project picker entry + type-aware right pane + execution
   modals. Reuse existing PDF preview pane.
4. **Desktop**: `DisciplineEditorView.swift`, type registration in
   `ProjectListView`, viewmodel methods. Reuse the export-menu fix
   from `65252a7`.
5. **End-to-end test on a sandbox tenant**: create a discipline
   project as a personal/free user → walk through chat draft →
   confirm meeting → digital sign with a fake recipient → confirm
   signed PDF lands in Files. Repeat for Refused and Physical paths.

## Verification

- **Project creation**: from MatchaWorkList "+ New Project" pick
  Discipline → empty draft created with seed `project_data`,
  AI greets with the intake prompt.
- **Drafting**: chat through the situation → AI emits
  `discipline_outline` → sections appear in the doc panel,
  editable.
- **PDF export**: hit Export → PDF — downloads a clean branded PDF
  with header, body, signature block.
- **Meeting gate**: clicking Send Digitally before
  `meeting_held_at` is set → button is disabled with helper text
  "Confirm the meeting was held first."
- **Digital sign**: confirm meeting → enter employee email → send →
  webhook fires (test envelope) → project shows `Signed`,
  signed PDF appears under Files, downloadable.
- **Refusal**: choose Refuse → notes required → state flips to
  `Refused`, project closed, refused_at + notes stored.
- **Physical**: download PDF, upload signed scan → state flips to
  `Physically Signed`, scan in Files.
- **Cross-tenant isolation**: a user from company A cannot read
  another company's discipline project (existing
  `mw_project_collaborators` + company_id scoping covers this; just
  verify).
- **List filtering**: project list correctly filters by
  `delivered_status` (Draft / Active / Closed), separate from the
  existing project status filter.

## Out of scope (v1)

- Pre-built infraction templates per industry (one generic template;
  AI fills the specifics).
- Multi-signer (employee + witness + manager). Single signer
  (employee) only.
- Auto-import from existing `progressive_discipline` rows so a
  matcha-work discipline project picks up where a platform engine
  record left off. (Future bridge if customers ask.)
- Reminders / nudges if the employee hasn't signed in N days. Add
  later.
- Localization. English only for v1; templates assume US labor law
  framing — AI can re-tone but no per-jurisdiction variants yet.

## Open question for the spec

> "If they want to do a physical signature then there should be an
>  option to export a PDF and then an option to upload the signed
>  document"

Confirmed in plan — Physical path = Export PDF + Upload signed
scan. Both options are visible in the Signature Choice pane.

> "Once signed, where can the rep find the signed document?"

Answer: the project's Files panel (right pane) AND a banner at the
top of the project view with a Download button. Audit log entries
in the project's audit pane (existing
`discipline_audit_log` style — but stored inside
`mw_projects.project_data.signature` events for the doc-first flow,
no new table).
