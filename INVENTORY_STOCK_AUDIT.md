# Inventory stock audit + voice counts (Gemini dictation, `inventory_voice`-gated)

## Context

Managers physically count stock in the store, then amend the app. Before this change, the only count-write path was: item row → `ItemDetail.tsx` → single "Set count" input → `patchItem(itemId, {set_quantity})` — one item per full page navigation. No audit/bulk-count concept existed anywhere in the inventory code (no endpoint, table, or UI).

Decisions:
- **Dedicated Audit mode** — a count sheet with a store filter and a per-row count input, mobile-friendly for a manager walking the store with a phone. Untouched rows are skipped; one Save commits everything.
- **One-shot voice dictation** (not Gemini Live) — record → Gemini parses spoken counts → prefills the sheet → manager reviews → same Save.
- **Voice gated on a new flag `inventory_voice`** (default off, admin-toggle, NOT bundled). The audit sheet itself ships free with `inventory` — only the voice button is gated.

Provenance invariant preserved: the audit writes `kind='adjust'` through `movements.adjust_item_count` (`movements.py:209`) — the one sanctioned set-count path. It already accepted a `note: Optional[str]` that no route had ever passed; the audit passes `note="Stock audit"` (or a caller-supplied override) so audit-originated rows are distinguishable in the ledger. Never `kind='in'`.

No migration, no new tables.

---

## Backend

### 1. Feature flag — `server/app/core/feature_flags.py`

```python
"inventory_voice": False,
```

Comment: voice dictation on the Inventory Audit sheet — one Gemini multimodal parse of a spoken count list into a review sheet the manager confirms before saving; parse-only, never writes (same invariant as `ir_voice_intake`). Default off; admin-toggle; NOT bundled.

`FEATURE_REQUIRES`:
```python
"inventory_voice": ("inventory",),
```

### 2. Audit commit service — `server/app/matcha/services/inventory/audits.py`

```python
MAX_LINES = 200

async def commit_audit_lines(
    conn, *, company_id: UUID, user_id: UUID, location_id: Optional[UUID],
    note: Optional[str], lines: list[dict],
) -> dict:
    # lines: [{item_id: UUID|None, new_item_name: str|None, counted_quantity: number}]
    # Returns {"total": int, "applied": int, "failed": int, "errors": [{row, item, error}]}
```

Mirrors `receipts.commit_receipt_lines`'s shape:
1. Location ownership check (same SQL as `receipts.py:296-303`) — raises `ValueError("location not found")` before touching any line.
2. `note = note or "Stock audit"`.
3. Catalog prefetched **once** via `movements_service.list_item_names(...)` and reused across every `new_item_name` line — avoids an N+1 catalog SELECT.
4. Per line, inside its own `async with conn.transaction():` (one wrapping transaction can't survive a bad row — Postgres aborts the whole thing on the first error, same reason `receipts.py` runs one transaction per line):
   - validate `counted_quantity` is a non-negative number, not a bool;
   - `item_id` path → `movements_service.adjust_item_count(conn, item_id=..., company_id=..., quantity=..., user_id=..., note=note)`;
   - `new_item_name` path (manager accepted an unmatched voice line as new) → `movements_service.find_or_create_item(...)` then `adjust_item_count` on its id;
   - neither field → `ValueError("line needs item_id or new_item_name")`.
5. A bad row is caught, logged, and appended to `errors[]` — the rest of the batch still commits.

A delta-0 line (counted the same as system) still writes — a confirmed count is audit information in its own right. Untouched items are simply absent from `lines`; the frontend only submits rows the manager actually typed into.

### 3. Voice parse service — `server/app/matcha/services/inventory/voice_audit.py`

Combines `ir_voice_parser.py`'s audio wrapper with `extraction.py`'s known-item-names grounding trick (the same closed-set idea as IR voice's `location_options`, so the model reuses an exact catalog name instead of inventing a near-duplicate).

```python
VOICE_PARSE_TIMEOUT = 90
MAX_VOICE_LINES = 100

def _coerce_voice_counts(raw: dict) -> dict:
    # PURE, unit-tested. Returns {"transcript": str|None,
    # "lines": [{"item_name": str, "quantity": float, "unit": str|None}]}.
    # Drops non-numeric/negative/bool quantities and empty/non-str names;
    # clamps name length to 200 chars; caps at MAX_VOICE_LINES. Never raises.

async def parse_voice_counts(audio_bytes: bytes, mime_type: str, *, item_names: list[str]) -> dict:
    # Never raises. One retry on asyncio.TimeoutError / json.JSONDecodeError only
    # (ir_voice_parser.py's loop, verbatim shape). Returns the coerced dict plus
    # {"available": bool(lines), "model": GEMINI_FLASH}.

async def resolve_count_lines(conn, *, company_id, location_id, lines: list[dict]) -> list[dict]:
    # Read-only. Attaches {"item_id": str|None, "matched_name": str|None,
    # "exact": bool} per line via list_item_names + matching.best_match —
    # receipts.resolve_lines minus the order-claiming block (an audit line
    # isn't tied to an order).
```

Gemini call: `types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)`, `GenerateContentConfig(response_mime_type="application/json", temperature=0.2)`, wrapped in `asyncio.wait_for(..., timeout=VOICE_PARSE_TIMEOUT)`. Uses `genai_env_client()` (the same client-factory precedent `extraction.py` uses) and `GEMINI_FLASH` from `model_catalog` — the audio-understanding tier IR voice uses, so no pricing-table edits were needed. No `BLOCK_NONE` safety overrides (that's IR-specific; not needed for stock counts).

Prompt:
```
You are transcribing a store manager dictating physical stock counts while walking the store.

Known inventory items (reuse an EXACT name below when the speech clearly refers to it; otherwise use the spoken name as heard, title-case):
{item_names or "(none yet)"}

Return ONLY valid JSON matching this shape:
{"transcript": "<full verbatim transcription of the audio>",
 "lines": [{"item_name": "...", "quantity": <number>, "unit": "<spoken unit like boxes/bags, or null>"}]}

Rules:
- One line per distinct item counted. "twelve boxes of gloves" -> {"item_name": "Gloves", "quantity": 12, "unit": "boxes"}.
- quantity is the TOTAL count stated for that item; convert number words to digits.
- Skip anything that is not a count of a stock item (asides, questions). Never invent an item or a number that was not spoken.
- If the same item is counted twice, keep only the LAST count (a correction).
```

### 4. Shared WAV reader — `server/app/matcha/services/_shared/uploads.py`

```python
_ALLOWED_AUDIO_MIME = {"audio/wav", "audio/x-wav", "audio/wave"}
_MAX_AUDIO_BYTES = 25 * 1024 * 1024

async def read_wav_or_400(file: UploadFile) -> bytes:
    # content-type allow-list (400), read_upload_capped(file, _MAX_AUDIO_BYTES),
    # RIFF/WAVE magic-byte check on the bytes themselves.
```

Lifted from `ir_incidents/_shared.py`'s `_read_audio_or_400` into the shared leaf module so any route package can bound a voice upload without importing another router package (routes must not import routes). IR's own copy is untouched.

### 5. Routes — `server/app/matcha/routes/inventory.py`

Mount-level `require_feature("inventory")` already applies to the whole router.

```python
@router.post("/audit/commit", response_model=AuditCommitResult)
async def commit_audit(body: AuditCommit, company_id=Depends(get_client_company_id),
                        user=Depends(require_admin_or_client)):
    # 400 empty lines, 413 over MAX_LINES, 404 on ValueError("location not found"),
    # else audits.commit_audit_lines(...) -> AuditCommitResult

@router.post("/audit/voice-parse", response_model=VoiceCountDraft)
async def parse_audit_voice(file: UploadFile = File(...), location_id: Optional[UUID] = Query(None),
                             current_user=Depends(require_admin_or_client),
                             _gate=Depends(require_feature("inventory_voice"))):
    # rate limits (below) -> read_wav_or_400 -> voice_audit.parse_voice_counts
    # -> voice_audit.resolve_count_lines -> VoiceCountDraft
```

Rate limits (own action keys, own budget — not shared with IR voice's), checked before reading the upload, same trio IR voice uses:
- `inv_voice_parse_burst`: 5 / 60s per user
- `inv_voice_parse`: 40 / hr per user
- `inv_voice_parse_co`: 120 / hr per company

### 6. Models — `server/app/matcha/models/inventory.py`

```python
class AuditLine(BaseModel):
    item_id: Optional[UUID] = None
    new_item_name: Optional[str] = None
    counted_quantity: float = Field(ge=0)   # 0 is legal — counted none on hand

class AuditCommit(BaseModel):
    location_id: Optional[UUID] = None
    note: Optional[str] = None              # defaults server-side to "Stock audit"
    lines: list[AuditLine]

class AuditCommitResult(BaseModel):
    total: int
    applied: int
    failed: int
    errors: list[dict]                      # [{row, item, error}]

class VoiceCountLine(BaseModel):
    item_name: str
    quantity: float
    unit: Optional[str] = None
    item_id: Optional[str] = None
    matched_name: Optional[str] = None
    exact: bool = False

class VoiceCountDraft(BaseModel):
    available: bool
    transcript: Optional[str] = None
    model: Optional[str] = None
    lines: list[VoiceCountLine]
```

---

## Frontend

### 1. Hoisted the dictation hook to the shared layer

`client/src/hooks/ir/useVoiceDictation.ts` → `client/src/hooks/useVoiceDictation.ts`. The hook had zero IR coupling (only imported React + `pcmToWav`), so this was a pure move + import-path fix. Updated its two importers: `components/ir/IRCreateIncidentModal.tsx`, `components/ir/IRPublicDictate.tsx`. The worklet (`/worklets/pcm-capture-processor.js`) and `utils/pcmToWav.ts` were already shared and needed no change.

### 2. API client — `client/src/work/api/inventory.ts`

```ts
export interface AuditCommitLine { item_id?: string; new_item_name?: string; counted_quantity: number }
export interface AuditCommitResult {
  total: number; applied: number; failed: number
  errors: { row: number; item: string; error: string }[]
}
export function commitAudit(body: { location_id?: string | null; note?: string; lines: AuditCommitLine[] }) {
  return api.post<AuditCommitResult>('/inventory/audit/commit', body)
}

export interface VoiceCountLine {
  item_name: string; quantity: number; unit: string | null
  item_id: string | null; matched_name: string | null; exact: boolean
}
export interface VoiceCountDraft { available: boolean; transcript: string | null; model: string | null; lines: VoiceCountLine[] }

export function parseAuditVoice(wav: Blob, locationId?: string) {
  const form = new FormData()
  form.append('file', wav, 'counts.wav')
  const qs = locationId ? `?location_id=${locationId}` : ''
  return api.upload<VoiceCountDraft>(`/inventory/audit/voice-parse${qs}`, form)
}
```

### 3. Audit sheet — `client/src/work/pages/InventoryAudit.tsx` (new)

Routes registered as `inventory/audit` in both `WorkRouteTree.tsx` and `WerkLiteRoutes.tsx`, inside the existing `<FeatureGate feature="inventory">` wrapper, alongside `inventory` and `inventory/:itemId`.

Structure:
- Loads `listItems()` + `listChannelLocations()` on mount, same pattern as `InventoryHub.tsx`. Store filter + free-text name search, both client-side.
- `edits: Record<itemId, string>` — raw input text per row; `""` means untouched. Touched rows get a highlighted ring; a small mic badge marks rows a voice dictation filled in (`fromVoice: Set<itemId>`).
- Sticky footer showing "Save N counts" + Cancel, only rendered once something is touched.
- `handleSave` builds `AuditCommitLine[]` from non-empty `edits` plus any accepted new-item lines, calls `commitAudit`, toasts applied/failed counts, clears local edit state, reloads.
- Voice section (only rendered when `hasFeature('inventory_voice')`): idle "Dictate counts" button → recording card with elapsed timer + Stop → "Transcribing…" spinner. Chrome copied (not imported — it was never extracted as a reusable component) from `IRCreateIncidentModal.tsx`'s recording UI. On stop, uploads the WAV via `parseAuditVoice`; matched lines merge into `edits`, unmatched lines render with per-line "Add as new item" / "Dismiss". A 429 gets its own message. Auto-stop at 120s.

### 4. Entry point — `InventoryHub.tsx`

An "Audit" button (`ClipboardCheck` icon, `secondary` variant) next to "Receive delivery" in the page header, navigating to `${base}/inventory/audit`.

---

## Tests

### `server/tests/inventory/test_audits.py` (new, 10 tests)

Fake-conn pattern from the existing `test_receipts.py`, patching `movements.adjust_item_count` / `find_or_create_item` / `list_item_names` on the live module object. Covers: default note applied, custom note passthrough, zero-count legality, one bad row failing alone without sinking the batch, new-item-name create-then-adjust, missing item_id/new_item_name, negative and boolean quantities rejected, location-not-found raised before any line runs, and the catalog fetched exactly once regardless of line count.

### `server/tests/inventory/test_voice_audit.py` (new, ~20 tests)

Pure `_coerce_voice_counts` tests (valid payload, negative/bool/non-numeric quantity dropped, empty/non-str name dropped, long name clamped, line-count cap, missing keys, non-list `lines`, non-dict entries). `resolve_count_lines` against a fake conn (exact match, fuzzy match, no match). `parse_voice_counts` against a fake Gemini client (never-raises on failure, successful parse, timeout-then-retry-succeeds).

### Result

`cd server && ./venv/bin/python -m pytest tests/inventory/ -q` → **120 passed**. `cd client && npx tsc -p tsconfig.app.json --noEmit` → clean. Full `tests/inventory/ tests/infrastructure/` run shows 29 pre-existing failures unrelated to this change (confirmed identical on a clean `main` via `git stash`) — none introduced by this work.

---

## Verification checklist

1. `cd server && ./venv/bin/python -m pytest tests/inventory/ -q`
2. `cd client && npx tsc -p tsconfig.app.json --noEmit` (not bare `tsc --noEmit` — see `client/CLAUDE.md`)
3. Live on dev-remote:
   - Toggle `inventory_voice` on for the test company.
   - `/work` → Ops → Inventory → **Audit** → type counts for a few items (one unchanged, one changed, one starting from an unknown `?` count) → Save → confirm toast + refreshed counts.
   - Ledger check: `docker exec matcha-postgres psql -U matcha -d matcha -c "SELECT kind, quantity, quantity_delta, note FROM inventory_movements ORDER BY created_at DESC LIMIT 5"` → `adjust` rows with `note='Stock audit'`.
   - Dictate: "six bags of espresso beans, twelve boxes of gloves, three cases of oat milk" → matched rows prefill with a mic badge, unmatched lines offer Add-as-new → Save.
   - Toggle `inventory_voice` off → Dictate button disappears; `POST /inventory/audit/voice-parse` 403s.
4. No migration, no schema change, no deploy required for this change alone.
