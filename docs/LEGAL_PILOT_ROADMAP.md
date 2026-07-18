# Legal Pilot — Bolstering Roadmap

Status: proposed · Owner: finch · Drafted: 2026-07-05
Baseline: commit `7f4ebcd` (matter-scoped evidence, intake-seeded first turn, jurisdiction setter / case-law discoverability).

Feature flag: `legal_defense` · Routes: `/legal-pilot/*` · Frontend: `client/src/pages/app/LegalDefense/` · Service: `server/app/matcha/services/legal_defense.py` · Tables: `legal_matters`, `legal_matter_messages`, `legal_matter_packets`, `legal_matter_share_links`, `legal_matter_research`, `legal_matter_audit_log`.

Product stance (unchanged, load-bearing): the AI is an **organizer, not an advocate**. Everything below stays on the "what the records show" side of the line — no liability opinions, no advocacy drafting. Grounding invariants (citation gate `validate_citations`, deterministic PDF appendix from DB rows) apply to every new surface.

**Design decision — no chat modes.** The chat stays a single freeform surface; the model intuits intent (same call as IR Copilot: LLM drives intent, hard gates only where consequences are real — see the `ir_flow.py` precedent and the reverted deterministic-march commit). Rule of thumb: **toggles for consequences** ("Case law only" cost, "Include legal landscape" packet contents, hold on/off), **intuition for conversational intent**, **tabs/panels for deterministic views** (chronology, checklist, evidence, hold manifest — SQL surfaces, never model-routed). Matter type is the de-facto mode, set once at intake and already threaded through `_MATTER_TYPE_CATEGORIES`, the checklist registry, and the seeded recap. Soft-mode discoverability comes from starters, not state: see 1.6.

---

## Current architecture (for orientation)

- `gather_evidence(conn, company_id, start, end, features, matter=)` assembles 8 internal sources (each `_src_*` isolated, capped at 100) + 3 jurisdiction sources (`law`/`legislation`/`case_law`). Since `7f4ebcd`, internal sources scope to the matter's `location_id`/state via `_scope_direct` / `_scope_employee` predicates. Same corpus feeds sidebar preview, chat grounding, and packet.
- Chat: `POST /matters/{id}/chat` → SSE → strict-JSON Gemini turn → citation gate → persisted to `legal_matter_messages`.
- Packet: memo PDF (WeasyPrint) + ZIP of source docs (S3 via `_collect_source_files`) + chain-of-custody table from `legal_matter_audit_log`.
- Share: `legal_matter_share_links` (token, expiry, revoke, `download_count`, `last_downloaded_at`); public delivery at `@public_router GET /legal-pilot/share/{token}`; downloads audit-logged as `shared_download`.
- Research: `legal_matter_research` rows (CourtListener cases + grounded guidance), state-mismatch guard in `_gather_case_law`.

Known scoping gaps after `7f4ebcd`: `er_cases` (JSONB `involved_employees`, no scalar FK) and `policy_signatures` (policies are company-wide by design) remain unscoped.

---

## Phase 1 — quick wins

### 1.1 Upload-the-complaint intake (document → prefilled matter)

**Why.** Users get served papers; they shouldn't transcribe them. Extends the redundant-entry fix upstream: the complaint/subpoena PDF itself becomes the intake source.

**Pattern to copy:** `server/app/matcha/services/contract_parser.py` — cached `IRAnalyzer`, PDF sent to Gemini as inline part, strict-JSON prompt, `_coerce_*` clamp, best-effort/never-raises, parse-and-discard (document not stored unless user opts in).

**Backend.**
- New `services/legal_intake_parser.py`: prompt extracts `{matter_type (one of the 6), title_suggestion, allegation, parties: {plaintiff, defendant}, jurisdiction_state, key_dates: {filed, incident_window_start, incident_window_end, response_deadline}, doc_kind}`. Clamp `matter_type` to `_MATTER_TYPES`; clamp state to 2 chars; dates ISO-parsed or dropped.
- New route `POST /legal-pilot/intake/parse` (multipart, `require_admin_or_client`, size cap ~15 MB, PDF-only): returns the draft — **never auto-creates the matter**. Same review-before-submit rule as `ir_voice_intake`.
- Rate-limit via existing `check_rate_limit` (Gemini cost control).

**Frontend.** `modals.tsx` `NewMatterModal`: optional "Upload the complaint / subpoena" dropzone (existing `<FileUpload>`) → parse → prefill all fields, visibly editable. Badge fields as "extracted — review".

**Tests.** Coercion unit tests (bad matter_type, garbage dates, non-JSON reply → empty draft). No live-Gemini test.

### 1.2 Chronology (merged timeline) — UI tab + PDF section

**Why.** Attorneys build chronologies by hand; every evidence record is already normalized `{cid, ref, summary, when, source_label}`.

**Backend.** Nothing new for data. Add a `chronology` block to the memo PDF in `_memo_html`: flatten `corpus["index"]` (internal sources only — exclude `law`/`bill`/`case`), sort by parsed `when` (undated records last under "Undated"), render as a two-column table (date · source-tagged summary). Deterministic — no model text.

**Frontend.** `MatterWorkbench` gets a `Console | Chronology` toggle (or a tab strip above the console). New `Chronology.tsx`: client-side merge+sort of `evidence.sources`, grouped by month, source icon per row (reuse `SOURCE_META`), row click → existing `RecordViewer`.

**Edge.** `when` is a display string today (`_fmt_dt`). Add a raw ISO `when_iso` field to each `_src_*` record dict (cheap: same row value, `.isoformat()`), so sorting never parses display strings. Backend-only additive change; FE ignores unknown keys.

### 1.3 Counsel-opened notification

**Why.** "Send to counsel" is fire-and-forget today; the data to close the loop already exists.

**Backend.** In the public share-download route (where `download_count` increments + `shared_download` audit row is written): fire a `BackgroundTasks` email to the matter's creator (`created_by` → users.email) — "Counsel ({recipient_email or 'link holder'}) downloaded {filename} for {matter title}". New method on the email package: `app/core/services/email/compliance.py` (or a new `legal.py` mixin) — note email service is a **package** now (`app/core/services/email/`), root CLAUDE.md's `email.py` reference is stale. Reserved-domain guard applies automatically.
- Debounce: only notify on `download_count` transition 0→1 per share link (first open), not every re-download.

**Frontend.** None required (email). Optional: "Opened ✓" chip in `PacketsPanel` — data already in `packet.share.download_count` (wired in `get_matter`), likely a 5-line change.

### 1.4 Matter response deadlines + reminders

**Why.** EEOC position statements, subpoena returns have hard dates; missing one is catastrophic and entirely preventable.

**Backend.**
- Migration `legaldef03`: `ALTER TABLE legal_matters ADD COLUMN response_deadline DATE, ADD COLUMN deadline_note VARCHAR(300)`.
- `MatterCreate`/`MatterUpdate` + intake parser (1.1 extracts `response_deadline`) carry it.
- New worker `app/workers/tasks/legal_deadline_reminders.py` cloning the `compliance_action_reminders` shape: gated by `scheduler_settings` row `task_key='legal_deadline_reminders'` (default disabled, per repo convention), scans active matters with deadlines in {14, 7, 3, 1} days, emails matter creator, dedupes via a `legal_matter_audit_log` action `deadline_reminder` (details carry the day-bucket) instead of a new table.
- Register in the `@worker_ready` dispatch list in `app/workers/celery_app.py`.

**Frontend.** `NewMatterModal` + jurisdiction-setter-style inline edit: deadline date field. `Masthead`: countdown chip (`due in 12d`, amber ≤7d, red ≤3d).

### 1.5 Close the `er_cases` scoping gap

**Why.** Only remaining unintentionally-unscoped source (policy acks are unscoped *by design*).

**Backend.** `involved_employees` JSONB elements carry `employee_id` (see `er_copilot.py:_resolve_involved_parties`; containment queries already use `@>`). In `_src_er_cases`, when a scope is active:

```sql
AND (
  ($4::uuid IS NULL AND $5::varchar IS NULL)
  OR EXISTS (
    SELECT 1 FROM jsonb_array_elements(er_cases.involved_employees) ie
    JOIN employees e ON e.id = (ie->>'employee_id')::uuid
    WHERE ($4::uuid IS NOT NULL AND (e.work_location_id = $4
           OR (e.work_location_id IS NULL AND UPPER(e.work_state) = UPPER($5))))
       OR ($4::uuid IS NULL AND UPPER(e.work_state) = UPPER($5))
  )
  OR jsonb_array_length(COALESCE(er_cases.involved_employees, '[]'::jsonb)) = 0
)
```

Last branch is deliberate: an ER case naming **no** employees can't be attributed to any location — keep it in scope rather than silently dropping it (opposite default from the employee-linked tables, where every row names an employee; comment this). Guard `(ie->>'employee_id')` NULL/garbage with a `WHERE ie ? 'employee_id'` filter. Unit-test the fragment placeholders like the existing `_scope_*` tests.

### 1.6 Matter-type-aware starters

**Why.** The three `STARTERS` in `shared.ts` are static and wage-biased ("class action alleging employees worked off the clock…"); on an EEOC or subpoena matter they read as noise. Starters are the soft-mode surface (see design decision above) — make them fit the matter.

**Frontend only.** `shared.ts`: `STARTERS` becomes `startersFor(matterType: MatterType): string[]` — 3 per type (e.g. `eeoc_charge`: "What documentation exists around the complainant's complaints and our responses?", "Show training and policy acknowledgments relevant to this charge", "What do the records NOT establish that counsel will ask about?"; `subpoena`: scope-inventory + custodian-shaped prompts; `audit`: posture/monitoring-shaped). `Console.tsx` takes the matter type (or the computed list) as a prop. Keep one universal closer ("What's missing?") in every set.

---

## Phase 2 — structural upgrades

### 2.1 Named claimants (person-scoped matters)

**Why.** Single-plaintiff and EEOC matters are person-shaped, not location-shaped; today scope is location-only.

**Schema.** Migration `legaldef04`:

```sql
CREATE TABLE legal_matter_employees (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  matter_id UUID NOT NULL REFERENCES legal_matters(id) ON DELETE CASCADE,
  employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  role VARCHAR(30) NOT NULL DEFAULT 'claimant',  -- claimant|complainant|witness|other
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (matter_id, employee_id)
);
```

**Backend.**
- CRUD on the matter routes (`POST/DELETE /matters/{id}/employees`), tenant-checked via employees.org_id = company.
- `gather_evidence`: when the matter has claimants, employee-linked sources (`discipline`, `training`, `accommodations`, and `er_cases` via containment) gain an additional `AND e.id = ANY($6::uuid[])`-style narrowing **on top of** location scope; incidents narrow via existing IR people links if present (check `ir_incidents` involved-person columns before promising). Person scope and location scope compose (AND).
- Per-claimant PDF appendix: reuse `build_er_packet`/`build_incident_packet` (`services/claims_readiness.py:44,206`) plus a per-employee digest (discipline rows, training status, policy acks for that signer).
- Prompt: claimant names/roles added to the MATTER block of `_build_prompt` so the model can organize per person — still citing only corpus cids.

**Frontend.** Masthead or side panel: claimants strip (roster picker — reuse whatever employee-picker `er_copilot` / IR use); EvidencePanel shows "scoped to N claimants".

**Privacy note.** Claimant-scoped packets concentrate one person's records — packet stays admin-gated + audit-logged (already true); no new exposure surface.

### 2.2 Deterministic evidence checklist per matter type

**Why.** AI `open_questions` are non-exhaustive and vary; attorneys want a fixed "do we have X" list. Zero hallucination surface.

**Backend.** New module-level registry in `legal_defense.py` (or `legal_checklist.py`):

```python
_MATTER_TYPE_CHECKLIST = {
  "eeoc_charge": [
    ("anti_harassment_policy_ack", "Anti-harassment policy + signatures", _chk_policy_ack_exists),
    ("harassment_training", "Harassment-prevention training completions", _chk_training_type),
    ("prior_complaints", "Prior ER complaints (same category)", _chk_er_category),
    ...
  ],
  "class_action": [...wage-hour: timekeeping discipline, meal-break policy, pay-period records...],
}
```

Each checker is a small SQL count against the already-scoped corpus window; result `{key, label, status: present|missing|n/a, count}`. Endpoint `GET /matters/{id}/checklist` (or folded into the evidence response). Mirrors how `_MATTER_TYPE_CATEGORIES` already maps matter types → compliance categories — reuse those category lists where they fit.

**Frontend.** EvidencePanel section "Expected for this matter type" — green check / amber missing rows; missing rows deep-link to the owning feature page (e.g. handbooks, training).

### 2.3 Litigation hold (warn-first)

**Why.** Spoliation is the worst real-world failure mode. Start warn-only; blocking is a follow-up decision.

**Backend.**
- Migration `legaldef05`: `ALTER TABLE legal_matters ADD COLUMN hold_active BOOLEAN NOT NULL DEFAULT FALSE, ADD COLUMN hold_started_at TIMESTAMPTZ` + toggle endpoint (audit-logged `hold_on`/`hold_off`).
- Shared helper `services/legal_hold.py:active_holds_for(conn, company_id, *, record_kind, record_id) -> list[matter]`: cheap check = any active-hold matter whose scope (window + location/claimants) covers the record.
- Wire into existing delete endpoints as **warn data, not a block**: `ir_incidents/crud.py:1116 DELETE /{incident_id}`, `er_copilot.py:775 DELETE /{case_id}`, `er_copilot.py:1821` (documents). Discipline has no delete route today (expiry task closes, doesn't delete) — nothing to wire there. Response gains `{"hold_warning": "In scope of active matter '<title>'"}`; FE confirms with explicit language.
- Hold manifest export: `GET /matters/{id}/hold-manifest` — CSV/PDF of every in-scope record id+source+date at hold time (defensible-process artifact; reuses `gather_evidence` without the AI).

**Frontend.** Masthead hold toggle + banner; delete-confirm dialogs surface the warning.

**Deferred decision:** hard-block deletes (`403` unless hold released) — product call, revisit after warn-mode ships.

---

## Phase 3 — bigger bets (sketch only)

### 3.1 Counsel evidence room
Extend the share token from packet-download to a read-only browse surface: evidence index, per-document S3 fetch (reuse `_collect_source_files` machinery per-record), counsel notes ("need X") that land as `legal_matter_messages` with a `counsel` role or a request table. Public-token surface → same hardening as `/report/:token` (rate-limit, no enumeration, expiry/revoke already exist). Biggest new attack surface of the roadmap — security review before build (webapp-security-pass conventions).

### 3.2 Supplemental-production diff
Persist a per-packet evidence snapshot (cid list + content hash) in `legal_matter_packets.metadata` at generation; `GET /matters/{id}/packets/{a}/diff/{b}` → added/removed/changed cids. Renders "since last production" list; feeds a supplemental ZIP containing only new documents.

---

## Cross-cutting

**Migrations:** `legaldef03` (deadline), `legaldef04` (claimants), `legaldef05` (hold) — chain off current head; apply via `./scripts/migrate-dev.sh` then `./scripts/migrate-prod.sh` per DB workflow. No destructive DDL anywhere.

**No new feature flags.** Everything rides `legal_defense`. Scheduler row `legal_deadline_reminders` defaults disabled (repo convention).

**Gemini cost:** 1.1 adds one flash call per intake parse (rate-limited); nothing else calls the model. Checklist/chronology/hold/notifications are all deterministic SQL.

**Suggested build order:** 1.5 → 1.6 → 1.2 → 1.3 → 1.4 → 1.1 (parser last in phase 1; it's the only model-dependent piece) → 2.1 → 2.2 → 2.3 → phase 3 re-scoped after usage feedback.

**Verification per phase:** unit tests follow `tests/legal_defense/test_legal_defense.py` fake-conn style (arg-count + fragment-placeholder assertions for any new SQL); `pytest tests/legal_defense/ -q`; `npx tsc --noEmit --incremental false`; manual pass on dev-remote (`:5174`) — create matter per type, verify checklist/chronology/deadline chip/hold banner; packet regen for PDF sections. DB-mutating integration tests stay manual-run per root CLAUDE.md.

**Explicit non-goals:** advocacy drafting (position statements, argument memos) — violates the organizer stance; policy-ack location scoping (no schema path); auto-creating matters from parsed documents (legal records require human confirmation, same rule as `ir_voice_intake`).
