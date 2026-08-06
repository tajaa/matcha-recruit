# Auto-changelog from merged PRs — matcha `/admin/updates` + new Tell-Us admin surface

## Context

Matcha's `/admin/updates` changelog is hand-authored and ~2 weeks stale (last entry `broker-company-chat`, 2026-07-20; PRs #109–#149 shipped since with no entries). Tell-Us has no changelog and no admin surface at all. Goal: entries auto-generate from **merged PRs at deploy time** — the laptop deploy path already has git, `gh`, `server/.env` (`GEMINI_API_KEY`), dev DB, and the sanctioned dev→prod sync (`sync-test-tenants.sh --auto` at `update-ec2.sh:380`). Merge-time CI generation rejected: Actions has no DB access / no Gemini key, and would need a new prod write path (violates "seed-prod.sh is the only prod writer").

Known limitation (accepted): GitHub-Actions deploys skip tenant sync (`update-ec2.sh:356`) — generator skips there too; next laptop deploy catches up (state = PR number, nothing lost).

Architecture: **generator writes dev DB → existing sync pushes prod.** First real run backfills the stale 2 weeks.

---

## Part 1 — DB migration

**New file** `server/alembic/versions/tellus_app_07_admin_updates.py`

```python
revision = "tellus_app_07"
down_revision = "tellus_app_06"   # current tellus head (verified via alembic heads; repo is multi-head, scripts run `upgrade heads`)
```

Two tables:

```sql
CREATE TABLE tellus_admin_updates (          -- identical shape to admin_updates (adminupd01)
    id          TEXT PRIMARY KEY,
    position    INTEGER NOT NULL,
    date        DATE NOT NULL,
    category    TEXT NOT NULL,
    title       TEXT NOT NULL,
    summary     TEXT NOT NULL,
    whats_new   JSONB NOT NULL,
    how_to_use  JSONB NOT NULL,
    setup       JSONB,
    notes       JSONB,
    tag         TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_tellus_admin_updates_position ON tellus_admin_updates (position);

CREATE TABLE changelog_autogen_state (       -- generator watermark, single row
    id              INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    last_pr_number  INTEGER NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Write real `downgrade()` (drop both). Author with sa.Column like `adminupd01_admin_updates_table.py:27-42`. Apply: commit first, then `./scripts/migrate-dev.sh`; prod via `./scripts/migrate-prod.sh` (user-run).

---

## Part 2 — Generator: `server/scripts/generate_changelog.py`

New script, importable module name (underscores) so tests import it normally (`sys.path` insert, same as `seed_admin_updates.py:18`). Uses `load_settings()` + `init_pool/get_connection/close_pool` exactly like `server/scripts/seed_admin_updates.py:26-28` — gets `database_url` and `gemini_api_key` for free from `server/.env`.

### Data shapes + pure functions (unit-testable, no IO)

```python
@dataclass
class PrInfo:
    number: int
    title: str
    body: str
    merged_at: str        # ISO date "2026-08-06" (date part of mergedAt)
    files: list[str]      # changed paths

TABLE_FOR_PRODUCT = {"matcha": "admin_updates", "tellus": "tellus_admin_updates"}  # fixed whitelist — table name never interpolated from input

TELLUS_PREFIXES = ("server/app/tellus/", "client/tellus/")
NON_PRODUCT = lambda p: p.startswith(("docs/", ".github/")) or p.endswith(".md")

def classify_pr(files: list[str]) -> set[str]:
    """Which products this PR touches. Empty set ⇒ skip (docs/CI only)."""
    # tellus if any path under TELLUS_PREFIXES; matcha if any remaining
    # product path outside them; both possible.

def slugify(title: str, max_len: int = 40) -> str:
    """lowercase, non-alnum → '-', collapse+strip dashes, truncate at word boundary."""

def entry_id(pr_number: int, title: str) -> str:
    return f"pr-{pr_number}-{slugify(title)}"

def build_prompt(pr: PrInfo, product: str) -> str:
    """Gemini prompt: PR title/body/file list + exact JSON schema + one sample
    entry (style-copied from admin_updates_seed.json) + category vocab
    (matcha: the 26 in-use values; tellus: Consumer/Brand/Places/Rewards/
    Messages/Billing/Platform) + tag rules ('action-needed' iff a migration or
    env var must be applied, 'new' for features, null for fixes) + product-
    scoping instruction (mixed PR ⇒ describe only this product's changes) +
    '{"skip": true}' escape for no-user-visible-change PRs."""

def parse_entry(raw: str, pr: PrInfo, product: str) -> dict | None:
    """Strict json.loads. Returns None for {'skip': true}.
    Validates: title/summary str non-empty, whatsNew non-empty list[str],
    howToUse list[str] (default []), setup/notes list[str]|None,
    tag coerced to {'new','action-needed'} else None,
    category str (default 'Platform'). Forces id=entry_id(...), date=pr.merged_at
    regardless of model output. Raises ValueError on structural garbage."""
```

### IO functions

```python
def fetch_merged_prs(since_pr: int, limit: int = 100) -> list[PrInfo]:
    """subprocess: gh pr list --state merged --base main --limit {limit}
       --json number,title,body,mergedAt,files
    Keep number > since_pr, sort ascending. files comes back as
    [{'path':…},…] (gh caps at 100 paths/PR — fine for classification;
    if the field errors on this gh version, fall back to per-PR
    `gh pr view N --json files`)."""

def generate_entry(client: genai.Client, pr: PrInfo, product: str) -> dict | None:
    """One call: model='gemini-3.1-flash-lite',
    config={'response_mime_type': 'application/json'}, then parse_entry()."""

async def upsert_entries(conn, product: str, entries: list[dict]) -> int:
    """INSERT … ON CONFLICT (id) DO NOTHING into TABLE_FOR_PRODUCT[product]
    (never clobbers hand edits). Column mapping identical to
    seed_admin_updates.py:35-63 (json.dumps for the JSONB cols).
    position inserted as 0 — renumber() fixes ordering after."""

async def renumber(conn, table: str) -> None:
    """Same SQL as export-dev-data.py:139-147 POST_HOOK:
    WITH ordered AS (SELECT id, row_number() OVER (ORDER BY date DESC, position ASC) - 1 AS rn FROM {table})
    UPDATE {table} t SET position = o.rn FROM ordered o WHERE t.id = o.id
    Runs EVERY invocation even with 0 new entries — self-heals position drift
    (e.g. after a seed_admin_updates.py rerun)."""

async def get_state(conn) -> int | None      # SELECT last_pr_number FROM changelog_autogen_state WHERE id=1
async def set_state(conn, pr_number: int)    # INSERT … ON CONFLICT (id) DO UPDATE
```

### main() / CLI

```
usage: generate_changelog.py [--dry-run] [--since-pr N] [--product both|matcha|tellus] [--limit N]
```

Flow: state = `--since-pr` or `get_state()`; **no state row and no `--since-pr` ⇒ exit 2 with instruction** (explicit first-run seeding, prevents accidentally generating 149 entries). Process PRs **oldest→newest, stop on first hard failure** and set state to last fully-processed PR — a mid-list failure never silently drops a PR. `--dry-run`: print entries as JSON, no DB writes, no state advance. Per-PR Gemini "skip" verdicts and docs-only PRs advance state normally. Exit 0 even when 0 entries (deploy hook must stay green on quiet deploys).

First-run seeding: `--since-pr 108` (highest PR merged ≤ 2026-07-21 — verify exact number with `gh pr list` during implementation; #109 merged 2026-07-31 is the first uncovered one).

---

## Part 3 — Deploy + sync wiring

**`scripts/update-ec2.sh`** — insert at :379, inside the existing non-CI branch, BEFORE the sync call (so fresh rows ride the same deploy's sync):

```bash
log_info "Generating changelog entries from merged PRs..."
CG_PY="server/venv/bin/python"; [ -x "$CG_PY" ] || CG_PY="python3"
"$CG_PY" server/scripts/generate_changelog.py \
    || log_warn "Changelog generation failed (deploy unaffected). Run server/scripts/generate_changelog.py manually."
```

(`set -e` is on — the `|| log_warn` guard is mandatory, same pattern as :380-381.)

**`scripts/sync-test-tenants.sh:250`** — add the twin table to the same export (flag is append-action; one SQL file, one prod transaction):

```bash
"$PY" scripts/export-dev-data.py --dsn "$DEV_URL" --table admin_updates --table tellus_admin_updates --mode update --scrub-emails --out "$ADMIN_OUT" >&2
```

**`scripts/export-dev-data.py:138`** — add key:

```python
POST_HOOKS = {
    "admin_updates": """…unchanged…""",
    "tellus_admin_updates": <same SQL, table name swapped>,
}
```

Verify during implementation that the POST_HOOK emission at :461-468 fires per-table when two `--table` flags are passed (its `text_rows` gate).

---

## Part 4 — Tell-Us backend admin

**`server/app/config.py`** — two edits:
- Settings class, next to `master_admin_email` (:197): `tellus_admin_emails: str = ""` (comma-separated; empty ⇒ fail-closed, nobody passes — same semantics as `_is_master_admin`).
- `load_settings()` (:361 area): `tellus_admin_emails=os.getenv("TELLUS_ADMIN_EMAILS", ""),`

**`server/app/tellus/dependencies.py`** — add:

```python
from app.config import get_settings

def _is_tellus_admin(email: str) -> bool:
    """Case-insensitive allowlist from TELLUS_ADMIN_EMAILS. Empty ⇒ nobody."""
    allowed = {e.strip().lower() for e in get_settings().tellus_admin_emails.split(",") if e.strip()}
    return email.lower() in allowed

async def require_tellus_admin(
    account: TellusAccount = Depends(require_tellus_account),
) -> TellusAccount:
    if not account.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access restricted")
    return account
```

And in `require_tellus_account`'s return (:69-82) add `is_admin=_is_tellus_admin(row["email"])`. Computed per-request from settings — **no JWT claim, no schema change** (token mint is the shared `scoped_auth.py` helper cappe also uses; `tellus_accounts` CHECK constraint untouched).

**`server/app/tellus/models/tellus.py`** — `TellusAccount` (:63-79) add:

```python
    # True when the account email is in TELLUS_ADMIN_EMAILS — internal changelog access.
    is_admin: bool = False
```

`/auth/me` returns `TellusAccount`, so the frontend gets `is_admin` with zero route changes.

**New file** `server/app/tellus/routes/admin.py`:

```python
"""Tell-Us internal admin — changelog only for now. Gated by TELLUS_ADMIN_EMAILS."""
import json
from fastapi import APIRouter, Depends
from ...database import get_connection
from ..dependencies import require_tellus_admin

router = APIRouter()

@router.get("/admin/updates", dependencies=[Depends(require_tellus_admin)])
async def list_tellus_admin_updates():
    """Product changelog shown at /tellus/admin/updates, newest first."""
    # identical body to core/routes/admin/platform_settings.py:83-108,
    # table tellus_admin_updates: ORDER BY position ASC, json.loads the four
    # JSONB cols if str, remap whats_new→whatsNew / how_to_use→howToUse.
```

**`server/app/tellus/routes/__init__.py`** — import + new block after :54:

```python
from .admin import router as admin_router
…
# Internal admin (require_tellus_admin per-route — TELLUS_ADMIN_EMAILS allowlist).
tellus_router.include_router(admin_router)
```

Full path: `GET /api/tellus/admin/updates`.

---

## Part 5 — Tell-Us frontend admin page

**`client/tellus/src/api/types.ts`** — `TellusAccount` (:12-27) add `is_admin: boolean`; new type:

```ts
export interface TellusAdminUpdate {
  id: string
  date: string          // ISO yyyy-mm-dd
  category: string
  title: string
  summary: string
  whatsNew: string[]
  howToUse: string[]
  setup: string[] | null
  notes: string[] | null
  tag: 'new' | 'action-needed' | null
}
```

**`client/tellus/src/App.tsx`** — new wrapper next to `Protected` (:34-48):

```tsx
function AdminOnly({ children }: { children: React.ReactNode }) {
  const { account, loading } = useAccount()
  const location = useLocation()
  if (loading) return <div className="min-h-screen bg-tu-bg"><Spinner /></div>
  if (!account) return <Navigate to={'/login?returnTo=' + encodeURIComponent(location.pathname + location.search)} replace />
  if (!account.is_admin) return <Navigate to="/" replace />
  return <Layout>{children}</Layout>
}
```

Route registered before the `*` catch-all (:87):

```tsx
{/* Internal admin */}
<Route path="/admin/updates" element={<AdminOnly><AdminUpdates /></AdminOnly>} />
```

(`import AdminUpdates from './pages/admin/Updates'`). URL: `/tellus/admin/updates`.

**New file** `client/tellus/src/pages/admin/Updates.tsx` — port of `client/src/pages/admin/Updates.tsx` (month-grouped accordion + category tabs + expand-all + "Setup needed" count; keep `fmtDate`/`monthLabel`/`groups` logic verbatim), with tellus substitutions:
- `api.get` → `tellusApi.get<TellusAdminUpdate[]>('/admin/updates')` (`api/tellusClient.ts`)
- zinc/emerald classes → tellus tokens (`bg-tu-bg`, `bg-tu-panel`, `text-tu-text`, `text-tu-dim`, `text-tu-accent` — match `Layout.tsx:39-45`); `LABEL` const from main app doesn't exist here — inline the label classes.

**`client/tellus/src/components/Layout.tsx`** — one line at :52 (both desktop :124-129 and mobile :158-163 render from `nav`, so one change covers both):

```tsx
const baseNav = isPendingBrand ? BRAND_PENDING_NAV : isBrand ? BRAND_NAV : CONSUMER_NAV
const nav = account?.is_admin ? [...baseNav, { to: '/admin/updates', label: 'Updates', icon: Sparkles }] : baseNav
```

(`Sparkles` added to the lucide import at :4.)

---

## Part 6 — Tests

**New** `server/tests/changelog/test_generate_changelog.py` — imports the script normally (`sys.path.insert` of `server/scripts/`; NOT `spec_from_file_location` — see server/CLAUDE.md test rules). Pure functions only, no DB/network/Gemini:

| # | Case | Assert |
|---|---|---|
| 1 | `classify_pr(["server/app/tellus/routes/dms.py", "client/tellus/src/App.tsx"])` | `== {"tellus"}` |
| 2 | `classify_pr(["server/app/matcha/routes/inventory.py"])` | `== {"matcha"}` |
| 3 | mixed tellus+matcha paths | `== {"matcha", "tellus"}` |
| 4 | `classify_pr(["docs/ops/DEPLOY.md", "CLAUDE.md"])` | `== set()` (docs-only skip) |
| 5 | `classify_pr([".github/workflows/ci.yml"])` | `== set()` |
| 6 | `slugify("Inventory stock audit sheet + voice count dictation")` | `"inventory-stock-audit-sheet-voice-count"` (≤40, word-boundary trunc, no leading/trailing `-`) |
| 7 | `entry_id(149, "Fix: thing → other")` | `"pr-149-fix-thing-other"` |
| 8 | `parse_entry('{"skip": true}', pr, "matcha")` | `None` |
| 9 | valid JSON entry | id forced to `entry_id(...)`, date forced to `pr.merged_at`, tag kept |
| 10 | `tag: "banana"` | coerced to `None` |
| 11 | `whatsNew: []` or missing title | raises `ValueError` |
| 12 | non-JSON garbage | raises `ValueError` |
| 13 | `build_prompt` for product="tellus" on a mixed PR | contains product-scoping instruction + `"skip"` escape |

**New** `server/tests/tellus/test_admin_gate.py`:

| # | Case | Assert |
|---|---|---|
| 1 | `_is_tellus_admin` with empty setting | `False` (fail-closed) |
| 2 | `"Admin@X.test"` vs setting `"admin@x.test"` | `True` (case-insensitive) |
| 3 | comma list with spaces `"a@x.test, b@y.test"` | both pass, others fail |

Patch `app.tellus.dependencies.get_settings` (the module that DEFINES the caller — per server/CLAUDE.md monkeypatch rule).

No auto-run DB tests (CLAUDE.md prod-safety rule) — DB paths verified manually below.

---

## Part 7 — Rollout order

1. Author migration → commit → `./scripts/migrate-dev.sh`.
2. Land generator + wiring + tellus backend/frontend; run pytest suites above; `cd client/tellus && npx tsc --noEmit` (verify its tsconfig actually checks files — root-app `tsc` gotcha) and `cd client && npx tsc -p tsconfig.app.json --noEmit` (untouched but cheap).
3. Add `TELLUS_ADMIN_EMAILS=<user's email>` to `server/.env` (dev).
4. `server/venv/bin/python server/scripts/generate_changelog.py --dry-run --since-pr 108` — **review output quality together**; tune prompt if entries are weak.
5. Real run (backfill) → verify dev: matcha `/admin/updates` shows PRs #109–#149 entries above the hand-authored ones; `/tellus/admin/updates` shows the tellus subset (#137, #140, #143, #148…); non-admin tellus account → redirect + API 403.
6. `./scripts/sync-test-tenants.sh` (dry-run default) — inspect `scripts/sql/sync_admin_updates.sql`: inserts for BOTH tables + both position POST_HOOKs.
7. User-run prod steps: `./scripts/migrate-prod.sh`; add `TELLUS_ADMIN_EMAILS` to `~/matcha/.env.backend` on the app EC2 (persists across deploys — no script overwrites it); normal deploy `./scripts/build-and-push.sh && ./scripts/update-ec2.sh --matcha` — generator + sync fire automatically at the end.

## Files touched

| File | Change |
|---|---|
| `server/alembic/versions/tellus_app_07_admin_updates.py` | new — 2 tables |
| `server/scripts/generate_changelog.py` | new — generator |
| `scripts/update-ec2.sh` | +4 lines at :379 |
| `scripts/sync-test-tenants.sh` | +1 `--table` flag at :250 |
| `scripts/export-dev-data.py` | +POST_HOOKS key |
| `server/app/config.py` | +`tellus_admin_emails` (class + load_settings) |
| `server/app/tellus/dependencies.py` | +`_is_tellus_admin`, `require_tellus_admin`, `is_admin=` in account build |
| `server/app/tellus/models/tellus.py` | +`is_admin: bool = False` |
| `server/app/tellus/routes/admin.py` | new — GET /admin/updates |
| `server/app/tellus/routes/__init__.py` | +import/include block |
| `client/tellus/src/api/types.ts` | +`is_admin`, +`TellusAdminUpdate` |
| `client/tellus/src/App.tsx` | +`AdminOnly`, +route |
| `client/tellus/src/pages/admin/Updates.tsx` | new — page |
| `client/tellus/src/components/Layout.tsx` | +conditional nav item |
| `server/tests/changelog/test_generate_changelog.py` | new — 13 cases |
| `server/tests/tellus/test_admin_gate.py` | new — 3 cases |

Out of scope: merge-time CI generation, entry editing UI, tellus consumer-facing "what's new", removing the seed-JSON path (stays for hand-authored entries; generator's always-renumber keeps positions coherent).
