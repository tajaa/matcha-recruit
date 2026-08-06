# Tell-Us: sign-in redirect, upload fix, brand prompts, unclaimed places — mechanical plan

## Context (short)

1. **QR sign-in redirect bug** — `Intake.tsx` sign-in CTAs are bare `<Link to="/login">`; `Login.tsx:24` hardcodes `navigate('/')`; draft state lost. Fix: `returnTo` query param + sessionStorage draft.
2. **Photo "upload failed"** — presign OK; browser PUT to `S3_PRIVATE_BUCKET` dies at CORS preflight (bucket has no CORS config → XHR status 0 → bare "Upload failed" at `Intake.tsx:32`). Second bug: `Intake.tsx:70` stale `idx = media.length` in multi-file loop collides updates, silently drops files.
3. **Brand prompts** — structured Q&A: `tellus_brand_prompts` + `tellus_report_answers`, form renders per-prompt textareas, Q&A shown in brand Feedback / MyReviews / public page.
4. **Unclaimed places** — `owner_account_id` goes nullable; public `/places` search + add-place creates ownerless brand + store + link; review reuses existing `/i/{token}` flow. Claim flow deferred (schema supports: claim = set owner + claimed_at).

Decisions locked: bulk-replace `PUT /brand/prompts` (≤5); answers snapshot `prompt_text`; `description` stays required, answers optional, scoring concatenates; answers not editable in MyReviews v1; CORS `AllowedHeaders:["*"]`; dedup add-place by lower(name)+city; consumer points flow normally on unclaimed, brand notifications null-guarded.

Execution order: **Step 0 (migration) → Steps 3–4 backend → Steps 3–4 frontend; Steps 1–2 independent, any time.** All paths repo-relative to `/Users/finch/Documents/github/matcha`.

---

## Step 0 — Migration `server/alembic/versions/tellus_app_06_prompts_places.py` (new file)

```python
"""tellus_app_06 — brand prompts, report answers, unclaimed places.

Revision ID: tellus_app_06
Revises: tellus_app_05
"""
from alembic import op

revision = "tellus_app_06"
down_revision = "tellus_app_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Unclaimed places: brands may exist without an owning account.
    op.execute("ALTER TABLE tellus_brands ALTER COLUMN owner_account_id DROP NOT NULL")
    op.execute("ALTER TABLE tellus_brands ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ")
    op.execute("ALTER TABLE tellus_brands ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'signup'")
    op.execute(
        """DO $$ BEGIN
            ALTER TABLE tellus_brands ADD CONSTRAINT ck_tellus_brands_source
                CHECK (source IN ('signup', 'consumer_added'));
        EXCEPTION WHEN duplicate_object THEN NULL; END $$"""
    )

    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_brand_prompts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_id UUID NOT NULL REFERENCES tellus_brands(id) ON DELETE CASCADE,
            prompt TEXT NOT NULL,
            position INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_brand_prompts_brand ON tellus_brand_prompts (brand_id, position)")

    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_report_answers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            report_id UUID NOT NULL REFERENCES tellus_reports(id) ON DELETE CASCADE,
            prompt_id UUID REFERENCES tellus_brand_prompts(id) ON DELETE SET NULL,
            prompt_text TEXT NOT NULL,
            answer TEXT NOT NULL,
            position INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_report_answers_report ON tellus_report_answers (report_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tellus_report_answers")
    op.execute("DROP TABLE IF EXISTS tellus_brand_prompts")
    op.execute("ALTER TABLE tellus_brands DROP CONSTRAINT IF EXISTS ck_tellus_brands_source")
    op.execute("ALTER TABLE tellus_brands DROP COLUMN IF EXISTS source")
    op.execute("ALTER TABLE tellus_brands DROP COLUMN IF EXISTS claimed_at")
    # Irreversible once ownerless brands exist — fail loudly instead of deleting data.
    ownerless = op.get_bind().execute(
        sa_text("SELECT COUNT(*) FROM tellus_brands WHERE owner_account_id IS NULL")
    ).scalar()  # use sqlalchemy.text import
    if ownerless:
        raise RuntimeError(f"{ownerless} ownerless brands exist; cannot restore NOT NULL. Restore from RDS snapshot.")
    op.execute("ALTER TABLE tellus_brands ALTER COLUMN owner_account_id SET NOT NULL")
```

Process: **commit file first**, then `./scripts/migrate-dev.sh`. **Prod migration user-run** (`./scripts/migrate-prod.sh`) — never run it from the session.

---

## Step 1 — Sign-in returnTo + draft preservation (frontend only)

### 1a. New `client/tellus/src/utils/returnTo.ts`

```ts
// returnTo must be an app-relative path ('/i/abc'), never absolute — blocks open redirects.
const KEY = 'tellus_return_to'

export function sanitizeReturnTo(v: string | null): string | null {
  if (!v || !v.startsWith('/') || v.startsWith('//') || v.includes(':')) return null
  return v
}

export function stashReturnTo(v: string | null) {
  const s = sanitizeReturnTo(v)
  if (s) sessionStorage.setItem(KEY, s)
}

export function popReturnTo(): string | null {
  const v = sessionStorage.getItem(KEY)
  sessionStorage.removeItem(KEY)
  return sanitizeReturnTo(v)
}
```

### 1b. `client/tellus/src/pages/Login.tsx`

- Imports: add `useSearchParams` to react-router import; import `sanitizeReturnTo, stashReturnTo, popReturnTo` from `../utils/returnTo`; add `useEffect` to react import.
- Inside component:
  ```ts
  const [params] = useSearchParams()
  const returnTo = sanitizeReturnTo(params.get('returnTo'))
  useEffect(() => { stashReturnTo(returnTo) }, [returnTo])   // survives detour to /signup + email verify
  ```
- Line 24: `navigate('/')` → `navigate(returnTo ?? popReturnTo() ?? '/')`.
- Line 54 "Create an account" link: `to={returnTo ? '/signup?returnTo=' + encodeURIComponent(returnTo) : '/signup'}`.

### 1c. `client/tellus/src/pages/Signup.tsx`

- Same imports + `returnTo` + stash effect as Login.
- Line 51: `navigate(type === 'brand' ? '/brand/billing' : '/')` → `navigate(type === 'brand' ? '/brand/billing' : (returnTo ?? popReturnTo() ?? '/'))`.
- Verification-required path (`setSent(true)`) changes nothing — the stash waits for Verify.

### 1d. `client/tellus/src/pages/Verify.tsx`

- Line 22: `.then((res) => { setSession(res); navigate('/') })` → `.then((res) => { setSession(res); navigate(popReturnTo() ?? '/') })`. Import `popReturnTo`.

### 1e. `client/tellus/src/App.tsx` — `Protected`

- Add `useLocation` to react-router import. In `Protected` (line 33): `const location = useLocation()`; line 38 becomes:
  ```tsx
  if (!account) return <Navigate to={'/login?returnTo=' + encodeURIComponent(location.pathname + location.search)} replace />
  ```
  (location is basename-relative inside the router — no `/tellus` stripping needed.)
- `Home` (line 51) keeps bare `/login` — `/` is not a destination worth returning to.

### 1f. `client/tellus/src/api/tellusClient.ts` — `_logout()` (lines 45-50)

```ts
function _logout() {
  clearTellusTokens()
  if (window.location.pathname !== '/tellus/login') {
    const rel = window.location.pathname.replace(/^\/tellus/, '') + window.location.search
    window.location.href = '/tellus/login?returnTo=' + encodeURIComponent(rel)
  }
}
```

### 1g. `client/tellus/src/pages/Intake.tsx` — CTAs + draft

- CTAs at lines 147, 205, 263: `to="/login"` → `` to={'/login?returnTo=' + encodeURIComponent('/i/' + token)} ``.
- Draft persistence (sessionStorage key `` 'tellus_intake_draft:' + token ``):
  ```ts
  type IntakeDraft = {
    category: string; sentiment: string; title: string; description: string
    contact: string; rating: number; postPublic: boolean
    answers: Record<string, string>          // step 3 adds this state
    media: PendingMedia[]                    // done entries only
  }
  ```
  - Hydrate once on mount (after existing state declarations):
    ```ts
    useEffect(() => {
      try {
        const raw = sessionStorage.getItem('tellus_intake_draft:' + token)
        if (!raw) return
        const d: IntakeDraft = JSON.parse(raw)
        setCategory(d.category); setSentiment(d.sentiment); setTitle(d.title)
        setDescription(d.description); setContact(d.contact); setRating(d.rating)
        setPostPublic(d.postPublic); setAnswers(d.answers ?? {})
        setMedia((d.media ?? []).map((m) => ({ ...m, progress: 100, done: true, error: undefined })))
      } catch { /* corrupt draft — ignore */ }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [token])
    ```
  - Save on change (skip once submitted):
    ```ts
    useEffect(() => {
      if (result) return
      sessionStorage.setItem('tellus_intake_draft:' + token, JSON.stringify({
        category, sentiment, title, description, contact, rating, postPublic, answers,
        media: media.filter((m) => m.done && m.storage_path),
      }))
    }, [category, sentiment, title, description, contact, rating, postPublic, answers, media, result, token])
    ```
  - In `submit()` after `setResult(res)`: `sessionStorage.removeItem('tellus_intake_draft:' + token)`.

---

## Step 2 — Upload fix: S3 CORS + multi-file index bug

### 2a. New `deploy/s3-cors-tellus-uploads.json`

```json
{
  "CORSRules": [
    {
      "AllowedOrigins": [
        "https://hey-matcha.com",
        "https://www.hey-matcha.com",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5191",
        "http://127.0.0.1:5191"
      ],
      "AllowedMethods": ["PUT", "GET"],
      "AllowedHeaders": ["*"],
      "ExposeHeaders": ["ETag"],
      "MaxAgeSeconds": 3000
    }
  ]
}
```
(Dev origins included — dev browsers PUT to the real bucket. Presigned auth lives in the query string, so `AllowedHeaders:*` costs nothing.)

### 2b. New `deploy/apply-s3-cors.sh` (chmod +x)

```bash
#!/bin/bash
# Apply the tellus direct-upload CORS rules to the private S3 bucket.
# Usage: ./apply-s3-cors.sh [bucket]   (defaults to $S3_PRIVATE_BUCKET)
set -euo pipefail
BUCKET="${1:-${S3_PRIVATE_BUCKET:-}}"
if [ -z "$BUCKET" ]; then
  echo "usage: $0 <bucket>  (or set S3_PRIVATE_BUCKET)" >&2
  exit 1
fi
DIR="$(cd "$(dirname "$0")" && pwd)"
aws s3api put-bucket-cors --bucket "$BUCKET" --cors-configuration "file://$DIR/s3-cors-tellus-uploads.json"
echo "Applied. Current config:"
aws s3api get-bucket-cors --bucket "$BUCKET"
```

### 2c. Ops (user-approved): run once against prod

Bucket = prod `S3_PRIVATE_BUCKET` value (presign path `storage.py:379` uses `private_bucket or bucket`; if unset in prod env, target `S3_BUCKET`). Read the value from `server/.env` / ask; run `deploy/apply-s3-cors.sh <bucket>`. Verify with the preflight curl in §Verification.

### 2d. `client/tellus/src/pages/Intake.tsx` — index-collision fix

- `interface PendingMedia` (line 18): add `id: string`.
- `onFiles()` rewrite of the loop body (lines 68-89):
  ```ts
  for (const file of Array.from(files)) {
    const mediaType: 'photo' | 'video' = file.type.startsWith('video') ? 'video' : 'photo'
    const id = crypto.randomUUID()
    const entry: PendingMedia = {
      id, name: file.name, media_type: mediaType, mime_type: file.type,
      file_size: file.size, original_filename: file.name, storage_path: '', progress: 0, done: false,
    }
    setMedia((m) => [...m, entry])
    try {
      const presign = await tellusPublicPost<MediaPresignResponse>(`/i/${token}/media/presign`, { ... }) // unchanged
      await uploadToS3(presign.upload_url, file, (pct) =>
        setMedia((m) => m.map((x) => (x.id === id ? { ...x, progress: pct } : x))))
      setMedia((m) => m.map((x) => (x.id === id ? { ...x, storage_path: presign.storage_path, done: true, progress: 100 } : x)))
    } catch (e) {
      setMedia((m) => m.map((x) => (x.id === id ? { ...x, error: e instanceof Error ? e.message : 'Upload failed' } : x)))
    }
  }
  ```
- `removeMedia` (line 93): `function removeMedia(id: string) { setMedia((m) => m.filter((x) => x.id !== id)) }`; list render (lines 234-241): `key={m.id}`, `onClick={() => removeMedia(m.id)}`.
- `uploadToS3` line 32: `xhr.onerror = () => reject(new Error('Upload failed — network or permissions error'))`.

---

## Step 3 — Brand prompts (structured Q&A)

### 3a. `server/app/tellus/models/tellus.py`

After `TellusBrandUpdate` (~line 127):
```python
class TellusBrandPrompt(BaseModel):
    id: UUID
    prompt: str
    position: int = 0


class TellusPromptItem(BaseModel):
    prompt: str = Field(min_length=1, max_length=500)


class TellusBrandPromptsUpdate(BaseModel):
    prompts: list[TellusPromptItem] = Field(default_factory=list, max_length=5)
```

In the public-intake section (~line 184):
```python
class TellusIntakePrompt(BaseModel):
    id: UUID
    prompt: str


class TellusSubmittedAnswer(BaseModel):
    prompt_id: UUID
    answer: str = Field(min_length=1, max_length=2000)


class TellusReportAnswer(BaseModel):
    id: UUID
    prompt_text: str
    answer: str
    position: int = 0
```
- `TellusIntakeConfig`: add `prompts: list[TellusIntakePrompt] = Field(default_factory=list)`.
- `TellusFeedbackSubmit`: add `answers: list[TellusSubmittedAnswer] = Field(default_factory=list)`.
- `TellusReport` (report model used by `_build_report`), `TellusMyReview` (line 451), `TellusPublicReview` (line 478): add `answers: list[TellusReportAnswer] = Field(default_factory=list)`.
- (Step 4 also in this file — do both in one pass: `TellusBrand.owner_account_id: Optional[UUID] = None`.)

### 3b. New `server/app/tellus/routes/prompts.py`

```python
"""Tell-Us brand feedback prompts — up to 5 custom questions on the intake form."""
from fastapi import APIRouter, Depends

from ...database import get_connection
from ..dependencies import require_paid_brand
from ..models.tellus import TellusAccount, TellusBrandPrompt, TellusBrandPromptsUpdate

router = APIRouter()


@router.get("/brand/prompts", response_model=list[TellusBrandPrompt])
async def get_prompts(account: TellusAccount = Depends(require_paid_brand)):
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT id, prompt, position FROM tellus_brand_prompts WHERE brand_id = $1 ORDER BY position",
            account.brand_id,
        )
    return [TellusBrandPrompt(**dict(r)) for r in rows]


@router.put("/brand/prompts", response_model=list[TellusBrandPrompt])
async def replace_prompts(body: TellusBrandPromptsUpdate, account: TellusAccount = Depends(require_paid_brand)):
    """Bulk replace — prompts are tiny config; answers snapshot prompt_text, so id churn is harmless."""
    async with get_connection() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM tellus_brand_prompts WHERE brand_id = $1", account.brand_id)
            rows = []
            for i, item in enumerate(body.prompts):
                rows.append(await conn.fetchrow(
                    "INSERT INTO tellus_brand_prompts (brand_id, prompt, position) "
                    "VALUES ($1, $2, $3) RETURNING id, prompt, position",
                    account.brand_id, item.prompt.strip(), i,
                ))
    return [TellusBrandPrompt(**dict(r)) for r in rows]
```

Register in `server/app/tellus/routes/__init__.py`: `from .prompts import router as prompts_router` + `tellus_router.include_router(prompts_router)` in the brand-authenticated block (after `links_router`).

### 3c. `server/app/tellus/routes/public_intake.py`

- `intake_config` (line 86-97): inside the `async with get_connection()` block after `_resolve_link`:
  ```python
  prows = await conn.fetch(
      "SELECT id, prompt FROM tellus_brand_prompts WHERE brand_id = $1 ORDER BY position LIMIT 5",
      link["brand_id"],
  )
  ```
  and add `prompts=[TellusIntakePrompt(id=p["id"], prompt=p["prompt"]) for p in prows]` to the response. Import `TellusIntakePrompt`.
- `submit_feedback`: after the atomic link UPDATE (line 197) and before `create_report`:
  ```python
  answers_in: list[tuple] = []
  if body.answers:
      prows = await conn.fetch(
          "SELECT id, prompt FROM tellus_brand_prompts WHERE brand_id = $1", link["brand_id"]
      )
      text_by_id = {p["id"]: p["prompt"] for p in prows}
      seen: set = set()
      for a in body.answers:
          text = text_by_id.get(a.prompt_id)
          if text is None or a.prompt_id in seen or not a.answer.strip():
              continue  # bogus/duplicate prompt ids are dropped, not errors
          seen.add(a.prompt_id)
          answers_in.append((a.prompt_id, text, a.answer.strip(), len(answers_in)))
          if len(answers_in) >= 5:
              break
  ```
  Pass `answers=answers_in` to `create_report`.

### 3d. `server/app/tellus/services/feedback_service.py`

- `create_report` signature (after `post_as_review`): `answers: list = (),`.
- Scoring (lines 128-130): description arg becomes
  ```python
  scoring_text = " ".join([description, *[a[2] for a in answers]])
  usefulness = score_usefulness(scoring_text, has_media, bool(title), occurred_at is not None, identified)
  ```
  (score-time only; stored `description` unchanged).
- After the media insert loop (line 167):
  ```python
  for prompt_id, prompt_text, answer, position in answers:
      await conn.execute(
          """INSERT INTO tellus_report_answers (report_id, prompt_id, prompt_text, answer, position)
             VALUES ($1, $2, $3, $4, $5)""",
          report_id, prompt_id, prompt_text, answer, position,
      )
  ```
- **Step 4 null guard in same file**: line 178 `if brand:` → `if brand and brand["owner_account_id"]:` (notification INSERT would violate `tellus_notifications.account_id` NOT NULL for ownerless brands).

### 3e. `server/app/tellus/routes/_shared.py` — serializers

- New helper:
  ```python
  def _answer_rows_to_models(arows) -> list[TellusReportAnswer]:
      return [TellusReportAnswer(id=a["id"], prompt_text=a["prompt_text"], answer=a["answer"], position=a["position"]) for a in arows]
  ```
- `_build_report(row, *, store_name, media, has_dm_thread, answers=())`: pass `answers=list(answers)` into `TellusReport`.
- `serialize_report` (line 111): add
  ```python
  arows = await conn.fetch(
      "SELECT id, prompt_text, answer, position FROM tellus_report_answers WHERE report_id = $1 ORDER BY position",
      row["id"],
  )
  ```
  → `answers=_answer_rows_to_models(arows)`.
- `serialize_reports` (line 135): add one batched query
  ```python
  arows = await conn.fetch(
      "SELECT id, report_id, prompt_text, answer, position FROM tellus_report_answers "
      "WHERE report_id = ANY($1::uuid[]) ORDER BY report_id, position", report_ids,
  )
  answers_by_report: dict = {}
  for a in arows:
      answers_by_report.setdefault(a["report_id"], []).append(a)
  ```
  → `answers=_answer_rows_to_models(answers_by_report.get(r["id"], []))` per row. Brand `feedback.py` needs zero changes (it uses these serializers).

### 3f. `server/app/tellus/routes/my_reviews.py`

- `_serialize_my_review` (line 18): same per-row answers fetch as 3e → `answers=` kwarg.
- `_serialize_my_reviews` (line 54): same batched fetch + `answers_by_report` map → per-row `answers=`.
- `PATCH /me/reviews/{id}` untouched (answers not editable v1).

### 3g. `server/app/tellus/routes/community.py`

- Alongside the media batch fetch (lines 55-69), add the same batched answers fetch → `TellusPublicReview(..., answers=...)`.

### 3h. `client/tellus/src/api/types.ts`

```ts
export interface IntakePrompt { id: string; prompt: string }
export interface ReportAnswer { id: string; prompt_text: string; answer: string; position: number }
export interface BrandPrompt { id: string; prompt: string; position: number }
```
- `IntakeConfig`: add `prompts: IntakePrompt[]`.
- `Report`, `MyReview`, `PublicReview`: add `answers: ReportAnswer[]`.
- (Step 4 in same pass: `Brand.owner_account_id: string | null`.)

### 3i. `client/tellus/src/pages/Intake.tsx` — render prompts

- State: `const [answers, setAnswers] = useState<Record<string, string>>({})` (also in the Step-1 draft).
- Below the "Your feedback" `<Textarea>` (line 222):
  ```tsx
  {(config?.prompts ?? []).map((p) => (
    <Textarea key={p.id} label={p.prompt} rows={2} value={answers[p.id] ?? ''}
      onChange={(e) => setAnswers((a) => ({ ...a, [p.id]: e.target.value }))} />
  ))}
  ```
- Submit body (line 108-112): add
  ```ts
  answers: Object.entries(answers)
    .filter(([, v]) => v.trim())
    .map(([prompt_id, answer]) => ({ prompt_id, answer: answer.trim() })),
  ```

### 3j. `client/tellus/src/pages/brand/Settings.tsx` — "Feedback questions" card

- Load: `tellusApi.get<BrandPrompt[]>('/brand/prompts')` on mount → `useState<string[]>` of prompt texts.
- UI (new `<Card>` below the existing one, same Input/Button components): one `<Input>` per question with an X remove button; "Add question" button (`disabled={questions.length >= 5}`); ↑/↓ reorder buttons (swap array entries); Save button →
  ```ts
  await tellusApi.put<BrandPrompt[]>('/brand/prompts', { prompts: questions.filter(q => q.trim()).map(q => ({ prompt: q.trim() })) })
  ```

### 3k. Q&A render (3 surfaces, same ~7-line block)

`brand/Feedback.tsx` below the description `<p>` (line 118), `consumer/MyReviews.tsx` below its description (line 87, read-only — NOT inside the edit form), `PublicBrand.tsx` in the review card:
```tsx
{r.answers.length > 0 && (
  <div className="mt-2 space-y-1.5">
    {r.answers.map((a) => (
      <div key={a.id}>
        <p className="text-xs font-medium text-tu-dim">{a.prompt_text}</p>
        <p className="whitespace-pre-wrap text-sm">{a.answer}</p>
      </div>
    ))}
  </div>
)}
```

---

## Step 4 — Unclaimed places

### 4a. `server/app/tellus/models/tellus.py` (same pass as 3a)

- `TellusBrand.owner_account_id: Optional[UUID] = None`.
- New models:
  ```python
  class TellusPlaceSearchResult(BaseModel):
      slug: str
      name: str
      logo_url: Optional[str] = None
      city: Optional[str] = None
      state: Optional[str] = None
      claimed: bool
      intake_token: Optional[str] = None   # only ever set for unclaimed places
      review_count: int = 0


  class TellusPlaceCreate(BaseModel):
      name: str = Field(min_length=1, max_length=255)
      city: str = Field(min_length=1, max_length=120)
      state: Optional[str] = Field(default=None, max_length=60)
      website: Optional[str] = None  # honeypot


  class TellusPlaceCreateResponse(BaseModel):
      slug: str
      name: str
      claimed: bool = False
      intake_token: Optional[str] = None
      existing: bool = False
  ```
- `TellusPublicBrandPage`: add `claimed: bool = True` and `intake_token: Optional[str] = None`.

### 4b. New `server/app/tellus/routes/places.py`

```python
"""Tell-Us public places — search any place, add an unclaimed one, review it.

Unclaimed place = tellus_brands row with owner_account_id NULL (source
'consumer_added') + one store + one always-on link whose token feeds the
existing /i/{token} intake flow. Unauthenticated; mirrors public_intake.py
hygiene (rate limits + honeypot accept-and-drop).
"""
import secrets
from typing import Optional

import asyncpg
from fastapi import APIRouter, Query, Request, status

from ...core.services.redis_cache import check_rate_limit, client_ip
from ...database import get_connection
from ..models.tellus import TellusPlaceCreate, TellusPlaceCreateResponse, TellusPlaceSearchResult
from ..services.geo import geocode_location
from ._shared import slugify

router = APIRouter()


@router.get("/places/search", response_model=list[TellusPlaceSearchResult])
async def search_places(
    request: Request,
    q: str = Query(min_length=1, max_length=120),
    city: Optional[str] = Query(default=None, max_length=120),
):
    await check_rate_limit(client_ip(request), "tellus_place_search", 60, 3600)
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT b.slug, b.name, b.logo_url, b.owner_account_id,
                      s.city, s.state,
                      (SELECT COUNT(*) FROM tellus_reports r
                        WHERE r.brand_id = b.id AND r.review_state = 'held'
                          AND r.publish_at <= NOW() AND r.moderation_status = 'visible') AS review_count,
                      CASE WHEN b.owner_account_id IS NULL THEN lk.token END AS intake_token
               FROM tellus_brands b
               LEFT JOIN LATERAL (SELECT city, state FROM tellus_stores
                                   WHERE brand_id = b.id ORDER BY created_at LIMIT 1) s ON TRUE
               LEFT JOIN LATERAL (SELECT token FROM tellus_links
                                   WHERE brand_id = b.id AND is_active
                                   ORDER BY created_at LIMIT 1) lk ON TRUE
               WHERE b.name ILIKE '%' || $1 || '%'
                 AND ($2::text IS NULL OR EXISTS
                      (SELECT 1 FROM tellus_stores st
                        WHERE st.brand_id = b.id AND st.city ILIKE '%' || $2 || '%'))
               ORDER BY review_count DESC, b.name
               LIMIT 20""",
            q.strip(), (city or "").strip() or None,
        )
    return [
        TellusPlaceSearchResult(
            slug=r["slug"], name=r["name"], logo_url=r["logo_url"],
            city=r["city"], state=r["state"],
            claimed=r["owner_account_id"] is not None,
            intake_token=r["intake_token"], review_count=r["review_count"],
        )
        for r in rows
    ]


@router.post("/places", response_model=TellusPlaceCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_place(body: TellusPlaceCreate, request: Request):
    ip = client_ip(request)
    await check_rate_limit(ip, "tellus_place_create_burst", 3, 60)
    await check_rate_limit(ip, "tellus_place_create", 5, 3600)

    if body.website:  # honeypot — synthetic success, no write
        return TellusPlaceCreateResponse(slug="place", name=body.name.strip(), intake_token=None)

    name = body.name.strip()
    city = body.city.strip()

    async with get_connection() as conn:
        async with conn.transaction():
            # Dedup: same name + same city (or a store-less brand with the name).
            existing = await conn.fetchrow(
                """SELECT b.id, b.slug, b.name, b.owner_account_id
                   FROM tellus_brands b
                   WHERE lower(b.name) = lower($1)
                     AND (EXISTS (SELECT 1 FROM tellus_stores s
                                   WHERE s.brand_id = b.id AND lower(s.city) = lower($2))
                          OR NOT EXISTS (SELECT 1 FROM tellus_stores s WHERE s.brand_id = b.id))
                   ORDER BY b.created_at LIMIT 1""",
                name, city,
            )
            if existing is not None:
                claimed = existing["owner_account_id"] is not None
                token = None
                if not claimed:
                    token = await conn.fetchval(
                        "SELECT token FROM tellus_links WHERE brand_id = $1 AND is_active "
                        "ORDER BY created_at LIMIT 1", existing["id"],
                    )
                return TellusPlaceCreateResponse(
                    slug=existing["slug"], name=existing["name"],
                    claimed=claimed, intake_token=token, existing=True,
                )

            slug = slugify(name)
            try:
                # SAVEPOINT so a slug collision only rolls back this insert (auth.py pattern).
                async with conn.transaction():
                    brand_id = await conn.fetchval(
                        "INSERT INTO tellus_brands (owner_account_id, name, slug, location_count, source) "
                        "VALUES (NULL, $1, $2, 1, 'consumer_added') RETURNING id",
                        name, slug,
                    )
            except asyncpg.UniqueViolationError as e:
                if e.constraint_name != "ux_tellus_brands_slug":
                    raise
                slug = f"{slug}-{secrets.token_hex(3)}"
                brand_id = await conn.fetchval(
                    "INSERT INTO tellus_brands (owner_account_id, name, slug, location_count, source) "
                    "VALUES (NULL, $1, $2, 1, 'consumer_added') RETURNING id",
                    name, slug,
                )

            geo = await geocode_location(city, body.state, None, None)
            store_id = await conn.fetchval(
                "INSERT INTO tellus_stores (brand_id, name, city, state, lat, lng) "
                "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
                brand_id, name, city, body.state,
                geo["lat"] if geo else None, geo["lng"] if geo else None,
            )
            token = secrets.token_urlsafe(12)
            link_id = await conn.fetchval(
                "INSERT INTO tellus_links (brand_id, store_id, token, label) "
                "VALUES ($1, $2, $3, 'Community feedback') RETURNING id",
                brand_id, store_id, token,
            )
            await conn.execute(
                "INSERT INTO tellus_link_history (link_id, action, actor_account_id, actor_ip, detail) "
                "VALUES ($1, 'created', NULL, $2, 'consumer_added place')",
                link_id, ip,
            )

    return TellusPlaceCreateResponse(slug=slug, name=name, intake_token=token)
```

Register in `routes/__init__.py` unauthenticated block: `from .places import router as places_router` + `tellus_router.include_router(places_router)`.

### 4c. `server/app/tellus/routes/community.py` — claimed flag + intake token

- Line 26 SELECT: add `owner_account_id` → `"SELECT id, name, slug, logo_url, owner_account_id FROM tellus_brands WHERE slug = $1"`.
- Before building the response:
  ```python
  claimed = brand["owner_account_id"] is not None
  intake_token = None
  if not claimed:
      intake_token = await conn.fetchval(
          "SELECT token FROM tellus_links WHERE brand_id = $1 AND is_active ORDER BY created_at LIMIT 1",
          brand["id"],
      )
  ```
- Response: `claimed=claimed, intake_token=intake_token`.

### 4d. Null-owner guards

- `feedback_service.py:178` — done in 3d (`if brand and brand["owner_account_id"]:`).
- `dms.py` (~line 233): the `_notify(conn, counterparty_id, ...)` after computing `counterparty_id` — guard `if counterparty_id: await _notify(...)` (defensive; unclaimed brands can't open threads).
- `public_intake.py:222` already guards (`if owner_id:`). No other owner deref sites.

### 4e. New `client/tellus/src/pages/Places.tsx`

Public page (route below), no auth. Structure:
```tsx
// state: q, city, results: PlaceSearchResult[] | null, searching, addName, addCity, addState, adding, err, website (honeypot)
// search: tellusPublicGet<PlaceSearchResult[]>(`/places/search?q=${encodeURIComponent(q)}${city ? '&city=' + encodeURIComponent(city) : ''}`)
// result card: name, city/state, review_count; Link to={`/b/${r.slug}`} "See reviews";
//   if (!r.claimed && r.intake_token) Link to={`/i/${r.intake_token}`} "Leave feedback"
// "Can't find it?" inline form → tellusPublicPost<PlaceCreateResponse>('/places', {name, city, state, website})
//   → res.intake_token ? navigate('/i/' + res.intake_token) : navigate('/b/' + res.slug)
```
Components: `Card, Input, Button, ErrorText, Spinner` from `../components/ui`; hidden honeypot input identical to `Intake.tsx:252`.

### 4f. `client/tellus/src/App.tsx`

`import Places from './pages/Places'` + public route: `<Route path="/places" element={<Places />} />`.

### 4g. `client/tellus/src/pages/PublicBrand.tsx`

Using new `PublicBrandPage.claimed`/`intake_token`: in the header, if `!page.claimed` render an "Unclaimed" chip (`text-xs` bordered span, tu-dim palette), a "Write a review" `<Link to={'/i/' + page.intake_token}>` button (only when `intake_token`), and the line "Are you the owner? Claiming is coming soon."

### 4h. `client/tellus/src/pages/Landing.tsx`

One CTA/link near the existing hero CTAs: "Review any place →" → `<Link to="/places">`.

### 4i. `client/tellus/src/api/types.ts` (same pass as 3h)

```ts
export interface PlaceSearchResult {
  slug: string; name: string; logo_url: string | null
  city: string | null; state: string | null
  claimed: boolean; intake_token: string | null; review_count: number
}
export interface PlaceCreateResponse {
  slug: string; name: string; claimed: boolean; intake_token: string | null; existing: boolean
}
```
`PublicBrandPage`: add `claimed: boolean; intake_token: string | null`.

---

## Verification

Checks:
- `cd client/tellus && npx tsc -p tsconfig.app.json --noEmit` (bare `tsc --noEmit` checks nothing) + one `npm run build`.
- `cd server && ./venv/bin/python -c "from app.tellus.routes import tellus_router"`; run tellus tests if present: `./venv/bin/python -m pytest tests/tellus/ -q`.
- Migration: commit → `./scripts/migrate-dev.sh` → psql `\d tellus_brand_prompts`, `\d tellus_report_answers`, `\d tellus_brands`. **Prod migration + CORS-on-prod are the two ops steps; CORS approved to run, prod migration stays user-run.**

Manual (dev servers via `./scripts/dev-remote.sh` + `cd client/tellus && npm run dev`; test accounts on RFC 2606 domains, e.g. `brand-test@example.com`):
- **Step 1**: logged-out `/tellus/i/<token>` → fill + upload → "sign in" → login → back on form, fields + photo intact → submit. Signup→Verify path returns too (stash). Negative: `?returnTo=https%3A%2F%2Fevil.com` → lands `/`.
- **Step 2**: two files selected at once → independent progress, both storage_paths submitted. After CORS apply: upload succeeds from dev origin; `curl -si -X OPTIONS -H 'Origin: https://hey-matcha.com' -H 'Access-Control-Request-Method: PUT' -H 'Access-Control-Request-Headers: content-type' '<presigned-url>'` → `access-control-allow-origin` present.
- **Step 3**: `PUT /brand/prompts` with 2 → 200; 6 → 422. `GET /i/<token>` includes prompts; submit with 1 valid + 1 bogus prompt_id → bogus dropped, answer row inserted. Q&A renders in brand Feedback, MyReviews (not editable), public page (dev-force `UPDATE tellus_reports SET publish_at = NOW() - interval '1 minute'`).
- **Step 4**: search curl → `claimed` flags correct, claimed brands never expose `intake_token`. POST place → `{slug, intake_token, existing:false}`; repeat → `existing:true`; honeypot POST → synthetic success, no row. Review via `/i/<intake_token>` as consumer → 201, points awarded, **no** `tellus_notifications` row, clean logs. `/tellus/b/<slug>` shows Unclaimed chip + review CTA. Regression: owned-brand QR submit still notifies owner.
