"""Cappe forms — form definitions + submissions (owner side).

Public submission lives in public.py.
"""
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeForm,
    CappeFormCreate,
    CappeFormSubmission,
    CappeFormUpdate,
)
from ._shared import get_owned_site, loads, loads_list, slugify, unique_site_slug

router = APIRouter()

_FORM_COLS = "id, site_id, name, slug, fields, status, created_at, updated_at"
_SUB_COLS = "id, form_id, data, submitter_email, is_read, created_at"


def _form_row(row) -> dict:
    d = dict(row)
    d["fields"] = loads_list(row["fields"])
    return d


def _sub_row(row) -> dict:
    d = dict(row)
    d["data"] = loads(row["data"])
    return d


# --- Forms ------------------------------------------------------------------

@router.get("/sites/{site_id}/forms", response_model=list[CappeForm])
async def list_forms(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"SELECT {_FORM_COLS} FROM cappe_forms WHERE site_id = $1 ORDER BY created_at DESC",
            site_id,
        )
    return [_form_row(r) for r in rows]


@router.post("/sites/{site_id}/forms", response_model=CappeForm, status_code=status.HTTP_201_CREATED)
async def create_form(
    site_id: UUID, body: CappeFormCreate, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        slug = await unique_site_slug(conn, "cappe_forms", site_id, slugify(body.slug or body.name))
        fields = json.dumps([f.model_dump() for f in body.fields])
        row = await conn.fetchrow(
            f"""INSERT INTO cappe_forms (site_id, name, slug, fields, status)
                VALUES ($1, $2, $3, $4, $5) RETURNING {_FORM_COLS}""",
            site_id, body.name, slug, fields, body.status,
        )
    return _form_row(row)


@router.get("/sites/{site_id}/forms/{form_id}", response_model=CappeForm)
async def get_form(site_id: UUID, form_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        row = await conn.fetchrow(
            f"SELECT {_FORM_COLS} FROM cappe_forms WHERE id = $1 AND site_id = $2", form_id, site_id
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Form not found")
    return _form_row(row)


@router.put("/sites/{site_id}/forms/{form_id}", response_model=CappeForm)
async def update_form(
    site_id: UUID, form_id: UUID, body: CappeFormUpdate,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        sets, args = [], []
        if body.name is not None:
            args.append(body.name)
            sets.append(f"name = ${len(args)}")
        if body.fields is not None:
            args.append(json.dumps([f.model_dump() for f in body.fields]))
            sets.append(f"fields = ${len(args)}")
        if body.status is not None:
            args.append(body.status)
            sets.append(f"status = ${len(args)}")
        if not sets:
            row = await conn.fetchrow(
                f"SELECT {_FORM_COLS} FROM cappe_forms WHERE id = $1 AND site_id = $2", form_id, site_id
            )
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Form not found")
            return _form_row(row)
        sets.append("updated_at = NOW()")
        args.extend([form_id, site_id])
        row = await conn.fetchrow(
            f"UPDATE cappe_forms SET {', '.join(sets)} "
            f"WHERE id = ${len(args) - 1} AND site_id = ${len(args)} RETURNING {_FORM_COLS}",
            *args,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Form not found")
    return _form_row(row)


@router.delete("/sites/{site_id}/forms/{form_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_form(site_id: UUID, form_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        result = await conn.execute(
            "DELETE FROM cappe_forms WHERE id = $1 AND site_id = $2", form_id, site_id
        )
    if result.endswith(" 0"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Form not found")


# --- Submissions ------------------------------------------------------------

@router.get("/sites/{site_id}/forms/{form_id}/submissions", response_model=list[CappeFormSubmission])
async def list_submissions(
    site_id: UUID, form_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        # form_id + site_id both scoped → no cross-site submission leak
        rows = await conn.fetch(
            f"""SELECT {_SUB_COLS} FROM cappe_form_submissions
                WHERE form_id = $1 AND site_id = $2 ORDER BY created_at DESC""",
            form_id, site_id,
        )
    return [_sub_row(r) for r in rows]


@router.patch("/sites/{site_id}/forms/{form_id}/submissions/{submission_id}", response_model=CappeFormSubmission)
async def mark_submission_read(
    site_id: UUID, form_id: UUID, submission_id: UUID,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        row = await conn.fetchrow(
            f"""UPDATE cappe_form_submissions SET is_read = true
                WHERE id = $1 AND form_id = $2 AND site_id = $3 RETURNING {_SUB_COLS}""",
            submission_id, form_id, site_id,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    return _sub_row(row)


@router.delete("/sites/{site_id}/forms/{form_id}/submissions/{submission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_submission(
    site_id: UUID, form_id: UUID, submission_id: UUID,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        result = await conn.execute(
            "DELETE FROM cappe_form_submissions WHERE id = $1 AND form_id = $2 AND site_id = $3",
            submission_id, form_id, site_id,
        )
    if result.endswith(" 0"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
