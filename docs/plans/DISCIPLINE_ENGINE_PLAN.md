# Discipline Engine — Plan

Companion build to the existing pre-termination work
(`server/app/matcha/routes/pre_termination.py`,
`server/app/matcha/services/pre_termination_service.py`,
`progressive_discipline` table). Closes out the partially-shipped
pre-termination feature set with a real escalation engine, configurable
look-back rules, manual override, e-signature workflow with refusal
handling, and notification triggers.

## Context

Today's `progressive_discipline` table records a fact (the warning was
issued) but doesn't enforce policy: there is no escalation logic, no
look-back / expiry math, no policy → look-back mapping, no override
audit trail, no signature workflow, and no notification fanout. HR
admins can list/create/update raw discipline rows but the system
doesn't tell them *which level* the next infraction should be, doesn't
flip stale rows to `expired` automatically, and doesn't drive the
in-room signing flow.

Goal: a single API call ("employee X just had infraction Y of severity
S") returns the recommended discipline level (with full reasoning),
opens a draft record, runs the workflow (meeting → signature or
refusal → notifications), and keeps `pre-termination` analyses honest
because the active-vs-expired state is now real.

## Core data model

### New columns on `progressive_discipline`

Bundle into one migration `add_discipline_engine_fields.py`:

| Column | Type | Purpose |
|--------|------|---------|
| `infraction_type` | `VARCHAR(64)` | Free-form key (e.g. `attendance`, `safety`, `harassment`). Drives which look-back-period config applies. |
| `severity` | `VARCHAR(20) CHECK (severity IN ('minor','moderate','severe','immediate_written'))` | Drives Escalation Engine entry point. |
| `lookback_months` | `INTEGER` | Snapshot of the active period at issue time (3, 6, 12 or whatever the policy was set to). Snapshotting protects against config drift. |
| `expires_at` | `TIMESTAMPTZ` | Computed at insert time as `issued_date + lookback_months months`. Indexed for the daily expiry sweep. |
| `escalated_from_id` | `UUID NULL REFERENCES progressive_discipline(id)` | Chain to the prior active record this one escalated from (null when starting fresh). |
| `override_level` | `BOOLEAN DEFAULT false` | True when HR jumped the engine. |
| `override_reason` | `TEXT` | Required when `override_level=true`. |
| `signature_status` | `VARCHAR(20) DEFAULT 'pending' CHECK (signature_status IN ('pending','requested','signed','refused','physical_uploaded'))` | Drives signature workflow. |
| `signature_requested_at` | `TIMESTAMPTZ` | When HR clicked "send signature request" after the meeting. |
| `signature_completed_at` | `TIMESTAMPTZ` | When employee signed (digital), refused (HR mark), or HR uploaded the physical signed PDF. |
| `signature_envelope_id` | `VARCHAR(255)` | E-signature provider envelope ID. |
| `signed_pdf_storage_path` | `VARCHAR(500)` | S3 key for the signed PDF (digital or physical scan). |
| `meeting_held_at` | `TIMESTAMPTZ` | Set when HR confirms the meeting happened. Required gate before signature can be requested. |

Extend the existing `status` CHECK to add `'pending_signature'` and
`'pending_meeting'`. The lifecycle becomes:

```
draft → pending_meeting → pending_signature → active → expired
                                            ↘ active (refused-to-sign)
                                            ↘ active (physical uploaded)
escalated and superseded → escalated
manually closed early → completed
```

### New table: `discipline_policy_mapping`

Per-company config that powers the engine. One row per
`infraction_type`.

```sql
CREATE TABLE discipline_policy_mapping (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    infraction_type VARCHAR(64) NOT NULL,
    label VARCHAR(255) NOT NULL,
    default_severity VARCHAR(20) NOT NULL,
    lookback_months_minor INTEGER NOT NULL DEFAULT 6,
    lookback_months_moderate INTEGER NOT NULL DEFAULT 9,
    lookback_months_severe INTEGER NOT NULL DEFAULT 12,
    auto_to_written BOOLEAN NOT NULL DEFAULT false,  -- "Severe / Immediate Written"
    notify_grandparent_manager BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (company_id, infraction_type)
);
```

Seed each new IR-only / bespoke company with a default set
(attendance / performance / safety / harassment / policy_violation /
gross_misconduct) on first access.

### New table: `discipline_audit_log`

Every state change writes a row here. Critical for the override
justification trail and for ER copilot / pre-termination analyses to
read consistency history.

```sql
CREATE TABLE discipline_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    discipline_id UUID NOT NULL REFERENCES progressive_discipline(id) ON DELETE CASCADE,
    actor_user_id UUID NOT NULL REFERENCES users(id),
    action VARCHAR(40) NOT NULL,  -- created / overridden / meeting_held / signature_requested / signed / refused / physical_uploaded / expired / closed
    details JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Escalation engine

### `recommend_next_discipline(employee_id, infraction_type, severity)`

Pure function in `server/app/matcha/services/discipline_engine.py`:

1. Fetch active records for the employee:
   `SELECT … FROM progressive_discipline WHERE employee_id=$1 AND status='active' AND expires_at > NOW() ORDER BY issued_date DESC`.
2. If `severity = 'immediate_written'` OR the policy mapping has
   `auto_to_written = true` for this infraction type → recommend
   `final_warning` (or `written_warning` per per-policy decision).
   Skip the climb-from-verbal logic.
3. Otherwise climb the ladder by counting **distinct levels currently
   active**:
   - 0 active → `verbal_warning`
   - active `verbal_warning` → `written_warning`
   - active `written_warning` → `final_warning`
   - active `final_warning` → `termination_review` (returned as a
     recommendation flag, NOT auto-issued; routes the user into the
     existing pre-term check flow).
4. Return:
   ```json
   {
     "recommended_level": "written_warning",
     "reasoning": [{"text": "Verbal warning issued 2026-02-10 still active until 2026-08-10", "discipline_id": "..."}],
     "supersedes": ["<verbal_warning id>"],
     "lookback_months": 9,
     "expires_at": "2027-01-29T00:00:00Z",
     "override_available": true
   }
   ```

`supersedes` is the list of prior records that flip from `active` to
`escalated` when this one is issued. The engine returns the list; the
issue endpoint applies the flip in the same transaction so we never
end up with two active rows on the same employee.

### Look-back reset rule

Decision (matches the spec's "does the first one stay active longer"
question): **first-in-first-out, no refresh**. A new infraction does
NOT reset the original timer. A verbal issued 2026-02-10 with a
6-month look-back expires 2026-08-10 regardless of any new
infractions in between. New infractions get their own `expires_at`
based on their own issue date and the configured look-back for that
infraction type / severity.

Why: HR auditors expect deterministic look-back math and a non-refresh
rule is what most progressive-discipline policies actually say in
writing. Refresh logic is configurable later if a customer needs it
(add `refresh_on_new_infraction BOOLEAN` to
`discipline_policy_mapping`).

### Daily expiry sweep

Celery beat task `expire_stale_discipline_records` runs once a day,
flips `status` from `active` to `expired` for any row where
`expires_at <= NOW()` and `status = 'active'`. Writes an `expired`
audit-log entry. `pre_termination_service.scan_consistency` (which
already weighs prior discipline) reads `status` correctly without
changes.

## Workflow

### State machine (per record)

```
draft         (created via API, before meeting confirmation)
   └─► pending_meeting   (HR clicked "begin workflow")
         └─► pending_signature   (HR confirmed "Have you conducted the disciplinary meeting? Yes")
               ├─► active           (employee signed digitally)
               ├─► active           (HR marked "Employee Refused to Sign")
               └─► active           (HR uploaded physical signed PDF)
   └─► escalated   (a higher-level record now supersedes this one)
   └─► expired     (expires_at passed)
   └─► completed   (HR manually closed early — improvement plan met)
```

`active` is the only "counts toward escalation" state. `escalated`,
`expired`, and `completed` all stop driving the engine.

### Signature workflow detail

1. HR creates the record (manual trigger; auto-trigger is out of scope
   for v1). System runs the engine and pre-fills the recommended
   level.
2. HR optionally overrides level (must supply `override_reason`, free
   text, min 20 chars). Override flips `override_level = true` and is
   logged.
3. HR attaches evidence — uploads land in S3 and rows go in the
   existing `documents JSONB`.
4. HR moves to "Begin disciplinary meeting." Status →
   `pending_meeting`. Server stamps `meeting_held_at = NULL` (set
   after step 5).
5. After the meeting, HR clicks "Have you conducted the disciplinary
   meeting?" → `Yes` stamps `meeting_held_at = NOW()` and moves to
   `pending_signature`. (No retreat to draft from this point.)
6. HR picks the signature path:
   - **Digital, in-room or remote** → server calls e-signature provider
     (DocuSign envelope or similar — abstract behind
     `SignatureProvider` interface), records `signature_envelope_id`,
     status moves from `pending` to `requested`. Webhook on completion
     sets `signed`, stamps `signature_completed_at`, stores signed PDF
     to `signed_pdf_storage_path`, and flips record status → `active`.
   - **Refused to Sign** → HR clicks "Employee refused to sign" with a
     required note. Status → `refused`, record status → `active`,
     warning still counts.
   - **Physical signature** → HR clicks "Export PDF for in-person
     signing." System renders the discipline doc to PDF (reuse the
     WeasyPrint helper from matcha-work). After the meeting HR uploads
     the scanned signed PDF — status → `physical_uploaded`, record
     status → `active`.
7. Notifications fire (see below).

### Out of scope for v1

- Auto-initiation from policy violations or attendance import. Manual
  trigger only.
- Multi-signer flows (witness, employee + manager). Single signer
  (employee) plus internal HR/manager metadata only.
- Multiple e-signature providers. Pick one (DocuSign or Dropbox Sign)
  for v1 behind `SignatureProvider`; abstract interface lets us swap.

## API surface

All under `/api/discipline` (new router; gate behind a new
`enabled_features.discipline` flag, on by default for `bespoke`
companies, off for `ir_only` until the customer upgrades).

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/recommend` | Body `{employee_id, infraction_type, severity}` → engine output (no row created). |
| `POST` | `/records` | Issue. Body adds `description, evidence_uploads[], override_level?, override_reason?`. Wraps the supersede flip atomically. |
| `GET` | `/records/employee/{id}` | List for one employee, with computed effective state. (Replaces or augments the existing `pre_termination/discipline/employee/{id}`.) |
| `PATCH` | `/records/{id}/meeting-held` | Idempotent stamp `meeting_held_at`. |
| `POST` | `/records/{id}/signature/request` | Send digital request. |
| `POST` | `/records/{id}/signature/refuse` | Body `{notes}` — HR marks refusal. |
| `POST` | `/records/{id}/signature/upload-physical` | Multipart upload of signed PDF. |
| `POST` | `/signature/webhook` | Provider webhook (signature/decline). |
| `GET` | `/policies` | List `discipline_policy_mapping` for current company. |
| `PUT` | `/policies/{infraction_type}` | Upsert mapping config. |
| `GET` | `/records/{id}/audit-log` | Reads `discipline_audit_log`. |

Existing `pre_termination` discipline endpoints stay for backward
compat but become thin shims that forward to the new router.

## Notifications

Hook into the existing notification system (`mw_notifications_router`
+ email service). Triggered events:

| Event | Recipients |
|-------|-----------|
| Record issued (status → `pending_meeting`) | Issuing HR + employee's direct manager |
| Signature requested | Employee (digital request itself) + direct manager + HR |
| Signed / Refused / Physical uploaded | Direct manager, manager's manager (if `notify_grandparent_manager=true` per policy mapping), HR (issuing user + any HR group) |
| Stale active → expired (sweep) | None by default — runs in background |

`employees.manager_id` already exists; chase the chain with one `JOIN`
to find the grandparent. If either is null, skip silently and log a
warning (don't block the workflow on missing org structure).

Email + in-app notification both. In-app uses
`mw_notifications.kind = 'discipline_*'`.

## Frontend

### New pages / components

- `client/src/pages/app/Discipline.tsx` — list + filters (active /
  expired / by employee).
- `client/src/pages/app/DisciplineDetail.tsx` — one record, evidence,
  audit log, signature workflow.
- `client/src/features/discipline/`:
  - `IssueDisciplineModal.tsx` — pick employee, infraction type,
    severity → engine preview → confirm.
  - `MeetingConfirmStep.tsx` — "Have you conducted the disciplinary
    meeting?" gate.
  - `SignatureChoiceStep.tsx` — Digital / Refused / Physical.
  - `EvidenceUpload.tsx` — drag-drop, attaches to `documents` JSONB.
  - `OverrideForm.tsx` — level override with required justification.
- `client/src/pages/app/DisciplineSettings.tsx` — admin-only edit of
  `discipline_policy_mapping`.

### Sidebar wiring

- Full-platform `ClientSidebar` — new entry under existing "HR Ops" or
  "Safety" group: "Discipline" → `/app/discipline`. Gated by
  `enabled_features.discipline`.
- IR-only `IrSidebar` — NOT shown until upgrade.

## Backward compat

- Existing `progressive_discipline` rows remain valid. Backfill on the
  same migration: `lookback_months = 6` (default), compute
  `expires_at = issued_date + INTERVAL '6 months'`, `severity =
  'moderate'`, `infraction_type = 'unspecified'`,
  `signature_status = 'signed'` for legacy rows (assume they were
  closed out the old way).
- `pre_termination_service.scan_consistency` already counts
  `status='active'` rows; once the daily sweep runs, stale rows flip
  to `expired` and the consistency calculation tightens up
  automatically.
- ER Copilot / IR Copilot bridges that read discipline history keep
  working (same table, additive columns).

## Critical files

| File | Change |
|------|--------|
| `server/alembic/versions/<new>_add_discipline_engine_fields.py` | New columns on `progressive_discipline`; new tables `discipline_policy_mapping`, `discipline_audit_log`; backfill of `expires_at` on existing rows. |
| `server/app/database.py:1633` | `progressive_discipline` schema definition synced for fresh installs. |
| `server/app/matcha/services/discipline_engine.py` (new) | `recommend_next_discipline`, `issue_discipline_with_supersede`, `expire_stale_records` (Celery target). |
| `server/app/matcha/services/signature_provider.py` (new) | `SignatureProvider` interface; one concrete impl. |
| `server/app/matcha/routes/discipline.py` (new) | The new router listed above. |
| `server/app/matcha/routes/__init__.py` | Mount new router; gate by `require_feature("discipline")`. |
| `server/app/matcha/routes/pre_termination.py` | Existing discipline endpoints become thin forwarders; tests updated. |
| `server/app/matcha/services/pre_termination_service.py` | `scan_consistency` reads new `status='active' AND expires_at > NOW()` (no behavior change once expiry sweep runs). |
| `server/app/core/feature_flags.py` | `DEFAULT_COMPANY_FEATURES["discipline"] = False`. Bespoke signup turns it on. |
| `client/src/pages/app/Discipline*.tsx` (new) | List + detail pages. |
| `client/src/features/discipline/*` (new) | Issue modal + signature workflow components. |
| `client/src/components/ClientSidebar.tsx` | Add Discipline nav, gated by feature flag. |

## Build order

1. **Schema** — migration with new columns + 2 new tables + backfill. Manual run on prod after explicit approval.
2. **Engine service** — `recommend_next_discipline` + `issue_discipline_with_supersede` + tests.
3. **API** — `/recommend`, `/records`, override flow.
4. **Workflow** — meeting confirm + signature provider abstraction + DocuSign (or chosen provider) impl + webhook.
5. **Refusal + physical upload** — both close the loop without provider.
6. **Notifications** — direct manager + grandparent + HR fanout.
7. **Daily expiry Celery beat** — flip `active → expired` past
   `expires_at`.
8. **Frontend** — list, detail, issue modal, signature step UI, policy
   mapping admin page.
9. **Migration of existing endpoints** — make legacy `pre_termination`
   discipline routes thin shims; remove duplicate logic.
10. **End-to-end test on a sandbox company** before flipping the
    feature flag for any real customer.

## Verification

- **Unit**: engine returns the right level for each (history,
  severity) combination; `auto_to_written` jumps correctly; override
  audit row written.
- **Integration**: issue verbal → wait → issue another infraction →
  engine recommends written and supersedes verbal in one transaction.
- **Workflow**: simulate digital sign → record `active`,
  `signature_completed_at` stamped, signed PDF in S3.
- **Refusal**: mark refused → record `active`, audit row, no provider
  call.
- **Physical**: export PDF, upload signed scan → record `active`,
  `signed_pdf_storage_path` set.
- **Expiry**: insert a row with `expires_at` in the past → run sweep
  task → row `expired`, audit logged.
- **Notifications**: end-to-end fire on each state change; manager
  chain resolved correctly; missing manager logs warning instead of
  500ing.
- **pre-termination consistency**: confirm a previously-active record
  that has expired no longer shows up in
  `pre_termination/checks/analytics`.

## Decisions captured (from spec)

- **Look-back reset**: first-in-first-out. New infractions don't
  refresh the original timer.
- **E-signature timing**: only fires after HR confirms the meeting was
  held. Drives signature path post-`pending_signature`.
- **Refusal-to-sign**: explicit status, closes workflow, warning
  remains active.
- **Physical signing**: PDF export option + signed-scan upload, both
  produce `active` records.
- **Notifications**: direct manager, manager's manager, and HR
  receive an automated copy once the signature (or refusal) is
  logged. Configurable per policy mapping (the
  `notify_grandparent_manager` flag).
