"""Cappe staff / stylists — owner CRUD.

Staff are the people a salon books appointments with. Which staff perform which
service is set per booking type (the `staff_ids` replace-set on the booking-type
routes in bookings.py). Public booking reads active staff via public.py.
"""
import csv
import io
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeStaff,
    CappeStaffCreate,
    CappeStaffImportError,
    CappeStaffImportResult,
    CappeStaffUpdate,
)
from ._shared import get_owned_site

router = APIRouter()

_STAFF_COLS = "id, site_id, name, bio, image_url, active, sort_order, location_id, created_at, updated_at"

_MAX_IMPORT_ROWS = 2000
_MAX_IMPORT_BYTES = 2_000_000

# CSV header aliases → canonical column, so a business can hand us their existing
# roster export with slightly different headings.
_STAFF_COL_ALIASES = {
    "name": "name", "full name": "name", "fullname": "name", "staff name": "name",
    "employee": "name", "employee name": "name", "stylist": "name", "team member": "name",
    "branch": "branch", "location": "branch", "branch name": "branch", "store": "branch", "site": "branch",
    "bio": "bio", "title": "bio", "role": "bio", "job title": "bio", "description": "bio",
    "active": "active", "status": "active",
}

# Strings that mean "this staff member is inactive". Anything else (incl. blank)
# is treated as active — the common case for a fresh roster import.
_INACTIVE_VALUES = {"no", "false", "0", "inactive", "disabled", "off", "hidden"}


async def _validate_location(conn, site_id, location_id) -> None:
    if location_id is None:
        return
    if not await conn.fetchval("SELECT 1 FROM cappe_locations WHERE id = $1 AND site_id = $2", location_id, site_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown location")


@router.get("/sites/{site_id}/staff", response_model=list[CappeStaff])
async def list_staff(
    site_id: UUID, location_id: Optional[UUID] = Query(None), shared: bool = Query(False),
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        args: list = [site_id]
        clause = ""
        if shared:
            clause = " AND location_id IS NULL"
        elif location_id is not None:
            args.append(location_id)
            clause = f" AND (location_id IS NULL OR location_id = ${len(args)})"
        rows = await conn.fetch(
            f"SELECT {_STAFF_COLS} FROM cappe_staff WHERE site_id = $1{clause} ORDER BY sort_order, created_at",
            *args,
        )
    return [dict(r) for r in rows]


@router.post("/sites/{site_id}/staff", response_model=CappeStaff, status_code=status.HTTP_201_CREATED)
async def create_staff(
    site_id: UUID, body: CappeStaffCreate, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        await _validate_location(conn, site_id, body.location_id)
        row = await conn.fetchrow(
            f"""INSERT INTO cappe_staff (site_id, name, bio, image_url, active, sort_order, location_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING {_STAFF_COLS}""",
            site_id, body.name, body.bio, body.image_url, body.active, body.sort_order, body.location_id,
        )
    return dict(row)


@router.put("/sites/{site_id}/staff/{staff_id}", response_model=CappeStaff)
async def update_staff(
    site_id: UUID, staff_id: UUID, body: CappeStaffUpdate,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        await _validate_location(conn, site_id, body.location_id)
        sets, args = [], []
        for col in ("name", "bio", "image_url", "active", "sort_order", "location_id"):
            val = getattr(body, col)
            if val is not None:
                args.append(val)
                sets.append(f"{col} = ${len(args)}")
        if not sets:
            row = await conn.fetchrow(
                f"SELECT {_STAFF_COLS} FROM cappe_staff WHERE id = $1 AND site_id = $2", staff_id, site_id
            )
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff not found")
            return dict(row)
        sets.append("updated_at = NOW()")
        args.extend([staff_id, site_id])
        row = await conn.fetchrow(
            f"UPDATE cappe_staff SET {', '.join(sets)} "
            f"WHERE id = ${len(args) - 1} AND site_id = ${len(args)} RETURNING {_STAFF_COLS}",
            *args,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff not found")
    return dict(row)


@router.delete("/sites/{site_id}/staff/{staff_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_staff(
    site_id: UUID, staff_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        result = await conn.execute(
            "DELETE FROM cappe_staff WHERE id = $1 AND site_id = $2", staff_id, site_id
        )
    if result.endswith(" 0"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff not found")


@router.post("/sites/{site_id}/staff/import", response_model=CappeStaffImportResult)
async def import_staff(
    site_id: UUID,
    file: UploadFile = File(...),
    account: CappeAccount = Depends(require_cappe_account),
):
    """Bulk-import a staff/employee CSV. Columns (header row, case-insensitive,
    aliases accepted): name (required), branch, bio, active. `branch` is matched
    to one of the site's location names (case-insensitive) so each employee is
    auto-mapped to the right branch; blank = works at all locations / main.

    Re-importing the same name updates that staff member's branch + bio (matched
    case-insensitively) rather than creating a duplicate.
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file is empty.")
    if len(raw) > _MAX_IMPORT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File too large (max 2 MB).")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("latin-1")
        except Exception:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Couldn't read the file — please save it as a UTF-8 CSV.")

    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file has no rows.")
    header = [_STAFF_COL_ALIASES.get((h or "").strip().lower(), (h or "").strip().lower()) for h in rows[0]]
    if "name" not in header:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Couldn't find a 'name' column. Download the template to see the expected columns.",
        )
    col_idx = {name: header.index(name) for name in set(header)}
    data_rows = rows[1:]
    if len(data_rows) > _MAX_IMPORT_ROWS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"That's {len(data_rows)} rows — please split into files of {_MAX_IMPORT_ROWS} or fewer.",
        )

    result = CappeStaffImportResult()
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        loc_rows = await conn.fetch(
            "SELECT id, lower(name) AS lname FROM cappe_locations WHERE site_id = $1", site_id
        )
        loc_by_name = {r["lname"]: r["id"] for r in loc_rows}
        has_locations = bool(loc_rows)
        # Existing staff by lower(name) → id, so a re-import updates rather than
        # duplicates (cappe_staff has no unique name constraint).
        existing_rows = await conn.fetch(
            "SELECT id, lower(name) AS lname FROM cappe_staff WHERE site_id = $1", site_id
        )
        existing_by_name = {r["lname"]: r["id"] for r in existing_rows}
        seen: set[str] = set()

        for i, row in enumerate(data_rows, start=1):
            def cell(col: str) -> str:
                j = col_idx.get(col)
                return row[j].strip() if (j is not None and j < len(row)) else ""

            name = cell("name")
            if not name and not any((c or "").strip() for c in row):
                continue  # wholly blank line — ignore, don't count
            result.total += 1
            if not name:
                result.errors.append(CappeStaffImportError(row=i, name=None, reason="Missing name"))
                result.skipped += 1
                continue
            key = name.lower()
            if key in seen:
                result.skipped += 1
                continue
            seen.add(key)

            location_id = None
            branch = cell("branch")
            if branch and has_locations:
                location_id = loc_by_name.get(branch.lower())
                if location_id is None:
                    result.errors.append(CappeStaffImportError(row=i, name=name, reason=f"Unknown branch '{branch}'"))
                    result.skipped += 1
                    continue
                result.branches_matched += 1

            bio = cell("bio") or None
            active = cell("active").lower() not in _INACTIVE_VALUES

            existing_id = existing_by_name.get(key)
            if existing_id is not None:
                await conn.execute(
                    """UPDATE cappe_staff
                       SET location_id = $1,
                           bio = COALESCE($2, bio),
                           active = $3,
                           updated_at = NOW()
                       WHERE id = $4 AND site_id = $5""",
                    location_id, bio, active, existing_id, site_id,
                )
                result.updated += 1
            else:
                new_id = await conn.fetchval(
                    """INSERT INTO cappe_staff (site_id, name, bio, active, location_id)
                       VALUES ($1, $2, $3, $4, $5) RETURNING id""",
                    site_id, name, bio, active, location_id,
                )
                existing_by_name[key] = new_id  # so a later dup-by-name row updates, not re-inserts
                result.created += 1

    return result
