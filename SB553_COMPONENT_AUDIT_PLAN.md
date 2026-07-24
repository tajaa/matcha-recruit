# Per-clause statute audit — making the landing animation real

## Context

`client/src/pages/landing/AgentReasoningAnimation/` shows CA SB 553 decomposed into 5 obligations
(written WVP plan / annual training / violent incident log / hazard assessment / annual review), each
marked GAP with a suggested fix, plus an exposure figure. It is **entirely hardcoded** — `data.ts` is
static consts (`DECISIONS`, `SCENARIO`, `SYNTHESIS`) animated on a timer by `useReasoningLoop.ts`. No
API call in that tree.

No backend produces this. In the catalog SB 553 is a **single row**
(`regulation_key = 'workplace_violence_prevention'`, Cal. Lab. Code § 6401.9,
`compliance_registry.py` ~line 4899), and nothing anywhere decomposes a statute into sub-obligations.

Goal: a real, demoable version inside `/app/compliance`, generic enough that any statute decomposes
later without new code.

**Decision: extend `compliance`. No new feature flag.**

Rejected: **new feature** (forks catalog + gating + research + status engine, reuses nothing);
**`controls_evidence`** (8 hardcoded cross-domain controls, underwriter-facing, no citation or
jurisdiction link, status hand-written per `source` tag); **`workforce_compliance`** (bespoke
table-per-tracker, no catalog FK — a 5th table); **`handbook_audit`** (closest output shape, but grades
an uploaded **PDF**, not company records).

## What already exists (this is why `compliance` wins)

| Asset | Location | State |
|---|---|---|
| `requirement_compliance_status` + `requirement_status_audit_log` | migration `reqstatus01` | live |
| `Derivation` registry + pure `resolve_status` / `rollup` | `compliance_status.py:58-128` | live, the repo's only generic status registry |
| `reconcile_requirement_status` | `compliance_status.py:447` | live, called from `compliance_risk.py:495` (return value discarded) |
| `attest_requirement_status` | `compliance_status.py:566` | **orphan — zero callers anywhere in `app/`** |
| `RequirementStatusSummary` Pydantic model | `core/models/compliance.py:505` | **orphan — fields are an exact match for `rollup()`'s output, referenced nowhere** |
| `compliance_issue_state.source` CHECK incl. `'requirement'` | already widened by `reqstatus01` | **no CHECK change needed** |
| `implementation_steps` JSONB (3–6 AI "how to comply" strings) | `jurisdiction_requirements`, populated catalog-wide | rendered only in `admin/GapDashboard/CoveredRow.tsx` — the unstructured precursor of these components |

Missing: a **component axis** and any tenant UI.

## Correctness decision (settled — do not revisit)

`compliance_status.py:60-71` + `_derive_harassment_training:209-211` + `_derive_injury_recordkeeping:233-234`
establish the invariant: **blind ⇒ `None` ⇒ `unknown`; never `compliant`, never a manufactured
`non_compliant`.**

A fresh tenant is therefore 5× `unknown`, **not** the animation's `GAPS 5/5`. The card renders `unknown`
as **"NO EVIDENCE ON FILE"** + suggested fix + one-click attest. Do not add a mode that asserts breach
from absent evidence.

SB 553 splits 2 derivable / 3 attest-first:

| Component key | Source | Path |
|---|---|---|
| `written_plan` | policies / handbook sections | attest-first (a plan can live off-system) |
| `annual_training` | `training_records` | **derived**, `required_feature="training"` |
| `violent_incident_log` | `ir_incidents` | **derived**, `required_feature="incidents"` |
| `hazard_assessment` | no system record | attest-only |
| `annual_review` | no system record | attest-only |

---

## 1. Migration — `server/alembic/versions/reqcomp01_requirement_components.py`

`revision = "reqcomp01"`, `down_revision = "penaltyauth01"` (the compliance chain tip; repo has 8 heads
— chaining here keeps the count at 8, does not create a 9th).

```sql
CREATE TABLE IF NOT EXISTS requirement_components (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    jurisdiction_requirement_id UUID NOT NULL
                     REFERENCES jurisdiction_requirements(id) ON DELETE CASCADE,
    component_key  VARCHAR(48) NOT NULL,
    label          TEXT NOT NULL,
    question       TEXT NOT NULL,
    statute_citation TEXT,
    suggested_fix  TEXT,
    severity       VARCHAR(12) NOT NULL DEFAULT 'important'
                     CHECK (severity IN ('critical','important','recommended')),
    derivation_key VARCHAR(48),          -- NULL => attest-only
    sort_order     INTEGER NOT NULL DEFAULT 0,
    verified_at    TIMESTAMPTZ,          -- hand-verification stamp (curation gate)
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (jurisdiction_requirement_id, component_key)
);
CREATE INDEX IF NOT EXISTS ix_req_components_parent
    ON requirement_components (jurisdiction_requirement_id, sort_order);
```

Widen the status table (additive, no backfill):

```sql
ALTER TABLE requirement_compliance_status ADD COLUMN IF NOT EXISTS component_key VARCHAR(48);
ALTER TABLE requirement_status_audit_log  ADD COLUMN IF NOT EXISTS component_key VARCHAR(48);

ALTER TABLE requirement_compliance_status
    DROP CONSTRAINT IF EXISTS requirement_compliance_status_location_id_jurisdiction_re_key;
CREATE UNIQUE INDEX IF NOT EXISTS ux_req_status_loc_cat_component
    ON requirement_compliance_status
       (location_id, jurisdiction_requirement_id, COALESCE(component_key, ''));
```

**`COALESCE(component_key,'')` is load-bearing.** Postgres treats NULLs as distinct in a plain unique
index, so `UNIQUE (location_id, catalog_id, component_key)` would let the whole-requirement row
(`component_key IS NULL`) be inserted repeatedly and silently break the existing `ON CONFLICT` in
`reconcile_requirement_status:533`.

**The existing `ON CONFLICT (location_id, jurisdiction_requirement_id)` targets in
`compliance_status.py:533` and `:601` must be updated to the new index columns** or both upserts start
raising `there is no unique or exclusion constraint matching the ON CONFLICT specification`.

`downgrade()`: drop the index, restore the 2-col UNIQUE (after deleting rows where
`component_key IS NOT NULL`), drop the columns and the table.

No CHECK change on `compliance_issue_state` — `reqstatus01` already added `'requirement'`.

## 2. Backend — `server/app/core/services/compliance_status.py`

New context keys (the existing ones are the wrong shape and must not be reused: `ctx["training"]` is
filtered to `training_type = 'harassment_prevention' OR LOWER(title) ~ '(harass|discriminat|eeo)'`, and
`ctx["incidents"]` aggregates `osha_recordable IS NULL`, which says nothing about violence logging):

```python
# added inside _build_context, each behind its own feature check
ctx["wvp_training"]  = ...   # if features["training"]:
    # SELECT COUNT(*) AS assigned,
    #        COUNT(*) FILTER (WHERE status = 'completed') AS completed,
    #        MAX(completed_at) AS last_completed
    # FROM training_records
    # WHERE company_id = $1
    #   AND (training_type = 'workplace_violence'
    #        OR LOWER(title) ~ '(workplace violence|wvp|sb ?553)')
ctx["violence_incidents"] = ...  # if features["incidents"]: dict keyed by location_id
    # SELECT location_id, COUNT(*) AS total,
    #        COUNT(*) FILTER (WHERE description IS NULL OR description = '') AS undocumented,
    #        MIN(incident_date) AS earliest
    # FROM ir_incidents
    # WHERE company_id = $1 AND location_id IS NOT NULL
    #   AND (incident_type ILIKE '%violence%' OR incident_type ILIKE '%threat%')
    # GROUP BY location_id
```

New derivations, signature-identical to the existing ones so they slot into `Derivation.fn`:

```python
async def _derive_wvp_training(
    conn, *, company_id: UUID, location_id: UUID, row: Dict[str, Any], ctx: Dict[str, Any]
) -> DerivationResult: ...

async def _derive_wvp_incident_log(
    conn, *, company_id: UUID, location_id: UUID, row: Dict[str, Any], ctx: Dict[str, Any]
) -> DerivationResult: ...
```

Rules, mirroring the existing precedents exactly:
- `_derive_wvp_training`: `ctx.get("wvp_training")` falsy or `assigned == 0` → `None` (cannot tell
  trained-and-unrecorded from untrained). `completed < assigned` → `("in_progress", {...})`. Else
  `("compliant", {...})`. Add `last_completed` to evidence; older than 12 months →
  `("non_compliant", {"rule": "annual training lapsed", ...})`.
- `_derive_wvp_incident_log`: no violence incidents at the location → `None` (**absence of incidents is
  not proof of a log**). `undocumented > 0` → `non_compliant`. Else `compliant`.

Component registry — same dataclass, separate dict so the parent-key registry is untouched:

```python
COMPONENT_DERIVATIONS: Dict[str, Derivation] = {
    "wvp_training": Derivation(
        "wvp_training", _derive_wvp_training, "SB 553 annual training",
        required_feature="training"),
    "wvp_incident_log": Derivation(
        "wvp_incident_log", _derive_wvp_incident_log, "SB 553 violent incident log",
        required_feature="incidents"),
}

def component_derivation(derivation_key: Optional[str]) -> Optional[Derivation]: ...
def derivable_component_keys() -> List[str]: ...
```

New public functions (all in the same module; `resolve_status` and `rollup` are reused **unchanged**):

```python
async def fetch_requirement_components(
    conn, catalog_ids: Sequence[UUID]
) -> Dict[UUID, List[Dict[str, Any]]]:
    """Catalog-side decomposition, batched by parent id. Never N+1 per requirement."""

async def reconcile_component_status(
    conn, company_id: UUID, *, features: Optional[Dict[str, Any]] = None,
    location_id: Optional[UUID] = None, catalog_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    """Re-derive status for every component of every codified requirement projected to
    this company. Same contract as reconcile_requirement_status: idempotent, read-path
    safe, audit-logs only real transitions. Returns {"evaluated": int, "changed": int}."""

async def get_component_checklist(
    conn, *, company_id: UUID, location_id: UUID, catalog_id: UUID,
) -> Dict[str, Any]:
    """One requirement's components + per-component status + rollup + exposure.
    Calls reconcile_component_status(scoped) first, then reads back."""

async def attest_component_status(
    conn, *, company_id: UUID, location_id: UUID, catalog_id: UUID,
    component_key: str, status: str, note: Optional[str], actor_user_id: UUID,
) -> Dict[str, Any]:
    """Human declaration for ONE component. Refused only when THAT component carries a
    derivation_key."""
```

**The per-component guard is the whole point.** `attest_requirement_status:583` refuses when
`regulation_key in DERIVATIONS` — a whole-key check. Reusing it would mean that the moment
`annual_training` becomes derivable, attestation is refused for `written_plan`, `hazard_assessment` and
`annual_review` on the same statute. `attest_component_status` must key the refusal on the component's
own `derivation_key`. Leave `attest_requirement_status` untouched.

`reconcile_component_status` mirrors `reconcile_requirement_status:447-563` with three changes: the
`existing` map key becomes the 3-tuple `(location_id, catalog_id, component_key)`; the row fetch joins
`requirement_components` instead of filtering on `derivable_keys()` (so attest-only components
participate — they have no `DERIVATIONS` entry and would otherwise never get a row); the
`codified_gate_sql("cat", conn=conn)` join stays verbatim, so components inherit the codified gate for
free.

### Guard the existing risk math — required, not optional

Component rows land in the same table as whole-requirement rows. Two live readers select from it
without a component filter, and both would silently change every tenant's numbers:

- `server/app/core/services/compliance_risk.py:495` — `WHERE rcs.company_id = $1 AND rcs.status =
  'non_compliant'`, builds `RiskIssue(id=f"requirement:{location_id}:{jurisdiction_requirement_id}")`.
  Five component rows on one requirement collide on that id.
- `server/app/matcha/services/risk_index.py:_compliance_component` (line 206, queries at 258/263) —
  coverage denominators feeding `compliance_posture_score`.

**Add `AND rcs.component_key IS NULL` to both.** v1 non-goal: components do not feed the risk index or
the remediation queue. Promoting a component rollup into the parent row is a deliberate follow-up that
moves scores and needs its own review.

## 3. Routes — `server/app/core/routes/compliance/`

Routers are `router` / `lite_router` / `shared_router`, defined bare at `_shared.py:85-87` and mounted
in `core/routes/__init__.py:78-89` under `prefix="/compliance"` (full path `/api/compliance/...`):
`shared_router` → `require_any_feature(*COMPLIANCE_SHARED_FEATURES)` = `("compliance","compliance_lite")`;
`router` → `require_feature("compliance")`.

New file `server/app/core/routes/compliance/components.py`, imported for decorator side-effects in
`compliance/__init__.py` alongside the other submodules:

```python
@shared_router.get(
    "/locations/{location_id}/requirements/{catalog_id}/components",
    response_model=RequirementComponentChecklist,
)
async def get_requirement_components_endpoint(
    location_id: str,
    catalog_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
): ...

@router.post(
    "/locations/{location_id}/requirements/{catalog_id}/components/{component_key}/attest",
    response_model=RequirementComponent,
)
async def attest_requirement_component_endpoint(
    location_id: str,
    catalog_id: str,
    component_key: str,
    payload: AttestComponentRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
): ...
```

Read on `shared_router` (Lite sees it read-only), write on `router` (full `compliance` only) — the split
documented in the root CLAUDE.md `compliance_lite` row. Derive `company_id` from `current_user` and
verify the location belongs to it; never trust a client-supplied id. `attest_component_status` raising
`PermissionError` → 409 with the message; `ValueError` → 422.

Extend `get_location_requirements_endpoint` (`locations.py:396`) with a `has_components` boolean via an
`EXISTS (SELECT 1 FROM requirement_components rc WHERE rc.jurisdiction_requirement_id = cat.id)`
subquery — one join, no extra round trip, and the FE knows which rows are expandable without N calls.

**Optional same-PR win:** the identical route shape gives orphaned `attest_requirement_status` its first
caller (`POST /locations/{location_id}/requirements/{catalog_id}/attest`). Cheap; flag separately in review.

## 4. Pydantic — `server/app/core/models/compliance.py`

```python
class RequirementComponent(BaseModel):
    component_key: str
    label: str
    question: str
    statute_citation: Optional[str] = None
    suggested_fix: Optional[str] = None
    severity: str = "important"
    sort_order: int = 0
    derivable: bool = False          # derivation_key is not None
    status: str = "unknown"
    basis: Optional[str] = None      # 'derived' | 'attested' | None
    evidence: Dict[str, Any] = Field(default_factory=dict)
    attested_note: Optional[str] = None
    attested_at: Optional[str] = None
    derived_at: Optional[str] = None

class RequirementComponentChecklist(BaseModel):
    jurisdiction_requirement_id: str
    location_id: str
    title: str
    statute_citation: Optional[str] = None
    components: List[RequirementComponent]
    summary: RequirementStatusSummary        # the orphan at line 505 — exact field match with rollup()
    exposure: Optional[Dict[str, Any]] = None

class AttestComponentRequest(BaseModel):
    status: Literal["compliant", "non_compliant", "in_progress", "unknown"]
    note: Optional[str] = None
```

Add `has_components: bool = False` to `RequirementResponse` (line 232).

**Exposure is reuse, not a new model.** Read `cat.metadata -> 'penalties'` + `cat.penalty_item_id` →
`authority_index_items` (the exact join already at `compliance_risk.py:495`) × active
`business_locations` count. Label it directional in the response and the UI. Do not invent a dollar model.

## 5. Seed pack — `scripts/seed/sb553_components.sql` + `.undo.sql`

Per `scripts/seed/README.md`: data only (no DDL — runner-enforced), additive only, `ON CONFLICT DO
NOTHING`, and **tag everything**: pin every `requirement_components.id` under a shared UUID prefix
(e.g. `5b553c00-0001-…`) so undo is `DELETE FROM requirement_components WHERE id::text LIKE '5b553c00-%'`.
Copy the structure of the only existing pair, `scripts/seed/benefits_sunset_dental.sql[.undo.sql]`.

Content: the 5 components, hand-curated per the `compliance_evals/fixtures/golden` rule — each cites the
real **subdivision** of Cal. Lab. Code § 6401.9 (plan / training / log / hazard identification / review),
`verified_at` stamped. The animation repeats a bare "CA Lab §6401.9" five times; that uniform citation is
a fidelity downgrade, not the target. `derivation_key` set only on `annual_training` and
`violent_incident_log`.

Run `./scripts/seed-prod.sh sb553_components --dry-run --dev` first, always.

## 6. Frontend

Real paths (the tab is under `components/`, not `pages/`; the api dir is doubly nested behind a barrel):

| File | Change |
|---|---|
| `client/src/types/compliance.ts` | add `RequirementComponent`, `RequirementComponentChecklist`; add `has_components?: boolean` to `ComplianceRequirement` (lines 195-238) |
| `client/src/api/compliance/compliance/requirements.ts` | add `fetchRequirementComponents(locationId, catalogId)` + `attestRequirementComponent(locationId, catalogId, componentKey, body)`, matching the file's existing `api.get<T>(...)` style |
| `client/src/api/compliance/compliance.ts` | re-export the two new functions from the barrel |
| `client/src/components/compliance/ComplianceRequirementsTab/ComponentChecklist.tsx` | **new** — the card |
| `client/src/components/compliance/ComplianceRequirementsTab/RequirementRow.tsx` | add local `const [open, setOpen] = useState(false)`; render a disclosure only when `req.has_components`; lazy-fetch the checklist on first open |

`RequirementRow` currently has **no internal expand state** — the category-level `expanded: Set<string>`
+ `toggle` live in `ComplianceRequirementsTab.tsx` and arrive via `CategoryRowShared`. Per-row state is
local and does not disturb that contract. The row already receives `readOnly?: boolean` — the attest
control must respect it.

Lite: `Compliance.tsx:57` dispatches `hasFeature('compliance_lite') && !hasFeature('compliance')` to
`ComplianceLiteView` before the tab bar exists, so Lite reaches the checklist through
`LitePreview.tsx`/`readOnly`, not through a tab filter.

Borrow the animation's **visual language only** — do not import from
`pages/landing/AgentReasoningAnimation/` (landing↔app boundary; different data shapes). Match the
existing zinc/emerald Tailwind tokens in neighbouring compliance components; no new colors.

Copy rule: `status === 'unknown'` renders **"No evidence on file"** + the suggested fix, never "GAP".

## 7. Pilot grounding (repo convention, same PR)

Root CLAUDE.md: *"When a new analytics/risk engine lands under `services/`, the same PR wires its records
into whichever grounded pilots ground on that domain."* Keep it minimal — extend
`matcha_work_node.build_compliance_context` (already the source of HR Pilot's `floor:` records) with
component-level status rather than adding a new corpus group. Then re-check
`hr_pilot_corpus.redact_for_employee` still behaves for the added text.

---

## Test cases

### `server/tests/compliance/test_component_status.py` (new)

Match the style of `server/tests/compliance/test_compliance_status.py`: **no DB**, direct imports of the
pure functions, `asyncio.run` rather than an async-test plugin. Stub `conn` is unused by these paths.

| # | Test | Assertion |
|---|---|---|
| 1 | `test_rollup_excludes_unknown` | 5 components, 2 compliant / 3 unknown → `total=5, known=2, coverage_pct=40` |
| 2 | `test_training_blind_returns_none` | `ctx["wvp_training"] is None` → derivation returns `None`; `resolve_status(None, None) == ("unknown", None, {})` |
| 3 | `test_training_nothing_assigned_returns_none` | `assigned=0` → `None` (not `compliant`, not `non_compliant`) |
| 4 | `test_training_incomplete_is_in_progress` | `assigned=87, completed=40` → `("in_progress", …)`, evidence carries both counts |
| 5 | `test_training_complete_is_compliant` | `assigned=87, completed=87` → `compliant` |
| 6 | `test_training_lapsed_is_non_compliant` | complete but `last_completed` 13 months ago → `non_compliant` |
| 7 | `test_incident_log_no_incidents_returns_none` | zero violence incidents → `None` — **absence of incidents is not proof of a log** |
| 8 | `test_incident_log_undocumented_is_non_compliant` | `total=4, undocumented=2` → `non_compliant`, counts in evidence |
| 9 | `test_attest_refused_on_derivable_component` | component with `derivation_key='wvp_training'` → `PermissionError` |
| 10 | **`test_attest_allowed_on_sibling_component`** | `hazard_assessment` (no `derivation_key`) on the **same** requirement → allowed. **Regression test for the whole-key guard bug** |
| 11 | `test_derived_outranks_attestation_and_preserves_it` | `resolve_status(derived, attested)` → `basis='derived'` and `evidence["superseded_attestation"]` present |
| 12 | `test_every_component_derivation_key_resolves` | every `derivation_key` used by the seed pack exists in `COMPONENT_DERIVATIONS` |
| 13 | `test_component_required_feature_gates_are_declared` | both entries carry a non-null `required_feature` (an ungated derivation would read an unsold module as a clean record) |

### `server/tests/seed_packs/test_sb553_components_pack.py` (new)

Mirror `server/tests/seed_packs/test_benefits_sunset_dental_pack.py`:
- no DDL keywords (`CREATE|ALTER|DROP`) in the pack
- no transaction-control statements (`BEGIN|COMMIT|ROLLBACK|SAVEPOINT`) — the runner owns the envelope
- every pinned `id` starts with the pack's UUID prefix; `.undo.sql` deletes by that prefix
- exactly 5 components, keys match the documented set, each has a non-empty `statute_citation`
- `derivation_key` non-null on exactly `annual_training` + `violent_incident_log`

### `client/src/components/compliance/ComplianceRequirementsTab/ComponentChecklist.test.tsx` (new)

Vitest is configured (`client/package.json`: `test`, `test:run`, `test:coverage`). Only one compliance
test exists today (`hooks/compliance/useComplianceRequirements.test.ts`) and **no component test at all**
for this tab, so this is the first.

- `unknown` status renders "No evidence on file" and **not** the string "GAP"
- attest control hidden when `readOnly` is true
- a `derivable: true` component renders no attest control (matches the server-side 409)
- `summary.coverage_pct` renders; `null` coverage renders a dash, not `0%`

### Regression coverage for the guards

- `server/tests/compliance/test_compliance_status.py` — add a case asserting
  `reconcile_requirement_status` still writes and upserts after the `ON CONFLICT` target change.
- Add a case asserting the `compliance_risk` / `risk_index` queries carry `component_key IS NULL`
  (grep-style source assertion is acceptable here and matches how the repo pins
  `INACTIVE_EMPLOYMENT_STATUSES` drift in the schedule tests).

## Verification

```bash
# unit
cd server && ./venv/bin/python -m pytest tests/compliance/ tests/seed_packs/ -q

# migration: commit FIRST, then rehearse against dev, watch elapsed time
cd server && MIGRATE_REHEARSAL=1 DATABASE_URL=<dev> ./venv/bin/python -m alembic upgrade heads
./scripts/migrate-dev.sh            # prod needs explicit approval — do not run migrate-prod.sh

# seed
./scripts/seed-prod.sh sb553_components --dry-run --dev

# frontend
cd client && npx tsc -p tsconfig.app.json --noEmit   # NOT bare `npx tsc --noEmit` — checks nothing
cd client && npm run test:run
```

End-to-end on dev — `./scripts/dev-remote.sh` is **already running on :5174**; do not start a second
Vite and **never** `pkill -f vite` (the pattern matches the user's real dev server):

1. `/app/compliance` → Requirements → expand the workplace-violence category.
2. The WVP row shows a disclosure (`has_components`); the other rows do not.
3. Open it → 5 components, correct subdivision citations, rollup line.
4. `training` + `incidents` on → those two show a derived verdict with evidence; toggle either feature
   off and reload → that component returns to `unknown`, never to a gap.
5. Attest `hazard_assessment` → persists, `basis='attested'`, survives a reload (which re-reconciles).
6. Attempt to attest `annual_training` → 409 with the "derived from your own records" message.
7. Confirm `/app/risk-profile` and the compliance risk summary are **numerically unchanged** — the
   `component_key IS NULL` guards are working.

## Gotchas

- `COALESCE(component_key,'')` in the unique index, and update both existing `ON CONFLICT` targets
  (`compliance_status.py:533`, `:601`) — otherwise the existing upserts break at runtime, not at import.
- Do **not** reuse `ctx["training"]` (harassment-filtered) or `ctx["incidents"]` (OSHA-recordability
  shaped) for WVP. New keys.
- `compliance_issue_state.source` already permits `'requirement'`; adding it again is a no-op that will
  read as a real change in review.
- Alembic is multi-head (8). Chain off `penaltyauth01`; `alembic upgrade heads` (plural) is what runs.
- Commit the migration before applying it to any DB, dev included.
