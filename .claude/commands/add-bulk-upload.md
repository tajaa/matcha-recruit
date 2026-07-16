Scaffold the bulk-CSV upload pattern (template endpoint + multipart upload endpoint + structured-errors response). Encodes the lessons from the 2026-05-15 medcenter.com bounce incident: invitation toggle defaults OFF, CSV templates use RFC 2606 reserved domains, server-side reserved-domain guard is presumed in place.

Parse the entity name from: $ARGUMENTS
Usage: `/add-bulk-upload <entity>` (e.g. `/add-bulk-upload candidates`).

The entity should be plural and match an existing router slug (e.g. `employees`, `candidates`, `incidents`). If you can't find an existing router for the entity, run `/new-router <entity>` first or stop and ask the user where it lives.

---

## Step 1: Identify the router file

Locate `server/app/matcha/routes/<entity>.py` (or `server/app/matcha/routes/<entity>/__init__.py` for a package). Read enough of it to identify:
- The Pydantic create model (e.g. `<Entity>Create`).
- The auth dep (`require_admin_or_client` is typical).
- Existing email-send pattern for this entity (look for any `send_*_email` call to mirror).

## Step 2: Add the template endpoint

Add (or update — if it exists already, audit it for reserved-domain compliance):

```python
@router.get("/bulk-upload/template")
async def download_bulk_upload_template(
    current_user=Depends(require_admin_or_client),
):
    """Download CSV template with one sample row using RFC 2606 reserved domains."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        'email', 'first_name', 'last_name',
        # ... add required + optional columns here
    ])
    writer.writeheader()
    writer.writerow({
        # CRITICAL: use RFC 2606 reserved domain — NEVER realistic fakes.
        # Allowed: @example.com, @example.org, @example.net, @<anything>.test,
        # @<anything>.invalid, @<anything>.localhost
        'email': 'jane.doe@example.com',
        'first_name': 'Jane',
        'last_name': 'Doe',
        # ...
    })
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=<entity>_template.csv"},
    )
```

**Do not** invent realistic-looking domains for the sample row. See root `CLAUDE.md` "Test Data — Email Domains" section.

## Step 3: Add the upload endpoint

```python
@router.post("/bulk-upload", response_model=Bulk<Entity>CSVUpload)
async def bulk_upload_<entity>_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="CSV with <entity> rows"),
    send_invitations: bool = Query(
        False,  # CRITICAL: default OFF. Bulk-invite blast incidents (e.g. 2026-05-15 medcenter.com)
                # were caused by this defaulting to True. Caller must opt in.
        description="Send invitation emails immediately after row creation",
    ),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload CSV to create <entity> rows and (optionally) send invitations."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")

    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    content = (await file.read()).decode('utf-8-sig')  # strip BOM if present
    reader = csv.DictReader(io.StringIO(content))

    created = 0
    failed = 0
    errors: list[dict] = []
    created_ids: list[str] = []

    async with get_connection() as conn:
        async with conn.transaction():
            for row_num, row in enumerate(reader, start=2):  # start=2: header is row 1
                try:
                    # 1. Validate required fields up front.
                    email = (row.get('email') or '').strip().lower()
                    if not email:
                        raise ValueError("email is required")

                    # 2. Create the row (replace with actual schema).
                    new_id = await conn.fetchval(
                        "INSERT INTO <table> (...) VALUES (...) RETURNING id",
                        # ...
                    )
                    created += 1
                    created_ids.append(str(new_id))

                    # 3. Optional invitation — only if explicitly opted in.
                    if send_invitations:
                        try:
                            await _send_<entity>_invitation_inline(conn, new_id, company_id, current_user.id)
                            await asyncio.sleep(0.15)  # rate-limit guard
                        except Exception as e:
                            logger.warning("Row %d: invitation failed for %s: %s", row_num, email, e)
                            errors.append({"row": row_num, "email": email,
                                           "error": f"Created but invitation failed: {e}"})

                except Exception as e:
                    failed += 1
                    errors.append({"row": row_num, "email": row.get('email', ''), "error": str(e)})

    if created == 0 and failed == 0:
        raise HTTPException(status_code=400, detail="No data rows found in CSV")

    return Bulk<Entity>CSVUpload(
        total_rows=created + failed,
        created=created,
        failed=failed,
        errors=errors,
        <entity>_ids=created_ids,
    )
```

Add the `Bulk<Entity>CSVUpload` response model to `server/app/matcha/models/<entity>.py`:

```python
class Bulk<Entity>CSVUpload(BaseModel):
    total_rows: int
    created: int
    failed: int
    errors: list[dict]
    <entity>_ids: list[str]
```

## Step 4: Frontend upload modal

Create `client/src/components/<entity>/BulkUploadModal.tsx`:

```tsx
import { useState } from 'react'
import { Button, FileUpload, Modal, Toggle } from '../ui'
import { api } from '../../api/client'
import type { BulkUploadResponse } from '../../types/<entity>'

type Props = {
  open: boolean
  onClose: () => void
  onSuccess: () => void
}

export function BulkUploadModal({ open, onClose, onSuccess }: Props) {
  // CRITICAL: default OFF. Mirrors backend Query default. The 2026-05-15
  // medcenter.com bounce-storm was caused by this defaulting to true.
  const [sendInvitations, setSendInvitations] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<BulkUploadResponse | null>(null)
  const [error, setError] = useState('')

  async function handleDownloadTemplate() {
    try {
      await api.download('/<entity>/bulk-upload/template', '<entity>_template.csv')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to download template')
    }
  }

  async function handleFiles(files: File[]) {
    const file = files[0]
    if (!file) return
    setUploading(true)
    setError('')
    setResult(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await api.upload<BulkUploadResponse>(
        `/<entity>/bulk-upload?send_invitations=${sendInvitations}`,
        fd,
      )
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Bulk Upload <Entity>">
      <Button variant="ghost" size="sm" onClick={handleDownloadTemplate}>Download CSV Template</Button>
      <FileUpload onFiles={handleFiles} accept=".csv" disabled={uploading} />
      <label className="flex items-center gap-2 text-sm text-zinc-400">
        <Toggle checked={sendInvitations} onChange={setSendInvitations} disabled={uploading} />
        Send invitations
      </label>
      {/* error + result rendering */}
    </Modal>
  )
}
```

## Step 5: Verify

```bash
cd /Users/finch/Documents/github/matcha/server && ./venv/bin/python -m py_compile app/matcha/routes/<entity>.py
cd /Users/finch/Documents/github/matcha/client && npx tsc -p tsconfig.app.json --noEmit
```

Then grep your new CSV template for accidentally-realistic domains:

```bash
grep -E "@[a-zA-Z0-9-]+\\.(com|org|net|io|co)" server/app/matcha/routes/<entity>.py | \
  grep -v "example\\.\\|\\.test\\|\\.invalid\\|\\.localhost"
```

Output should be empty. Any hit is a realistic fake — replace it.

Report back: the 3-4 files touched.

---

## Notes — non-negotiable defaults

These come from the 2026-05-15 incident review:

- `send_invitations` defaults to **False** in BOTH backend Query param AND frontend modal `useState`.
- CSV template sample rows use **RFC 2606 reserved domains only**.
- The server-level `_is_reserved_test_domain` guard in `server/app/core/services/email.py` is the second line of defense — verify it's still in place and active.
- If the frontend modal also sends to `MultiBatchModal` (multi-row in-form add), apply the same `useState(false)` default there. Audit any sibling modals before declaring done.
