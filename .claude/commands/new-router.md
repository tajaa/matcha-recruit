Scaffold a new FastAPI router under `server/app/matcha/routes/` following repo conventions (asyncpg pool, tenant-isolation pattern, audit-log pattern, mounting in `routes/__init__.py`).

Parse the router slug from: $ARGUMENTS
Usage: `/new-router <slug>` (e.g. `/new-router compensation_reviews`).

Use snake_case for the slug. The slug becomes the file name AND the URL prefix (kebab-case'd).

---

## Step 1: Decide flat-file vs package

- **Single concern, < ~1000 lines projected** → flat file at `server/app/matcha/routes/<slug>.py`. Default.
- **Multiple concerns or growth expected** → package directory following the `ir_incidents/` template (see `server/app/matcha/routes/ir_incidents/CLAUDE.md`).

For the default flat-file path, continue with steps 2-5 below.

## Step 2: Create the router file

Create `server/app/matcha/routes/<slug>.py`:

```python
"""<Short one-line description of what this router owns>."""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id

logger = logging.getLogger(__name__)

router = APIRouter()


async def _get_<entity>_with_company_check(conn, entity_id: UUID, current_user):
    """Verify ownership before reading/writing. Raises 404 on cross-company access."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="<Entity> not found")
    row = await conn.fetchrow(
        "SELECT * FROM <entity_table> WHERE id = $1 AND company_id = $2",
        str(entity_id), company_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="<Entity> not found")
    return row


@router.get("/{entity_id}")
async def get_<entity>(
    entity_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    async with get_connection() as conn:
        row = await _get_<entity>_with_company_check(conn, entity_id, current_user)
        return dict(row)
```

Replace `<entity>` and `<entity_table>` with the actual names. Add Pydantic request/response models in `server/app/matcha/models/<slug>.py` if endpoints take/return structured bodies.

## Step 3: Mount in `routes/__init__.py`

Edit `server/app/matcha/routes/__init__.py`:

1. Add to the import block near the top:
   ```python
   from .<slug> import router as <slug>_router
   ```
2. Add to the `include_router` block (alphabetical by domain):
   ```python
   matcha_router.include_router(<slug>_router, prefix="/<kebab-slug>", tags=["<slug>"])
   ```
3. If the router should be feature-gated, add `dependencies=[Depends(require_feature("<flag>"))]`. The flag must already exist — use `/add-feature-flag <flag>` first if not.
4. Add to the `__all__` list at the bottom of the file.

## Step 4: Models (if applicable)

If the router needs request/response shapes, create `server/app/matcha/models/<slug>.py`:

```python
"""Pydantic models for <slug> endpoints."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class <Entity>Create(BaseModel):
    name: str
    # ...


class <Entity>Response(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    # ...

    class Config:
        from_attributes = True
```

## Step 5: Schema (if applicable)

If you need a new table, add an Alembic migration:

```bash
cd /Users/finch/Documents/github/matcha/server && ./venv/bin/python -m alembic revision -m "add_<entity>_table"
```

**Do NOT** run `alembic upgrade head` automatically — per root CLAUDE.md, schema changes need explicit user approval before touching the production DB.

## Step 6: Verify

```bash
cd /Users/finch/Documents/github/matcha/server && ./venv/bin/python -c "
from app.main import app
paths = [r.path for r in app.routes if '/<kebab-slug>' in (r.path or '')]
print('paths:', paths)
"
```

If running locally, hit `http://localhost:8001/api/<kebab-slug>/...` to confirm the route resolves (auth-fail is the expected response without a token).

Report back: the 2-3 files created and the mount line.

---

## Notes

- Tenant isolation is non-negotiable. Every per-company endpoint must call `_get_<entity>_with_company_check` (or equivalent) — never trust the path parameter alone.
- Use asyncpg pool (`async with get_connection() as conn:`); do not introduce SQLAlchemy.
- For write-side actions, call the relevant `log_audit` helper inside the transaction.
- If the router will exceed ~2000 lines, plan for a package split following `ir_incidents/CLAUDE.md`.
