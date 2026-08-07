from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.codes import UpcCode
from app.models.enums import UpcStatus
from app.models.release import Release


class UpcError(Exception):
    pass


class PoolEmpty(UpcError):
    pass


class AlreadyAssigned(UpcError):
    pass


class InvalidUpcFormat(UpcError):
    def __init__(self, codes: list[str]) -> None:
        self.codes = codes
        super().__init__(f"Invalid UPC/EAN codes (bad length or check digit): {codes}")


def _gtin_check_digit_valid(code13: str) -> bool:
    digits = [int(c) for c in code13]
    payload, check = digits[:-1], digits[-1]
    total = 0
    for i, d in enumerate(reversed(payload)):
        weight = 3 if i % 2 == 0 else 1
        total += d * weight
    return (10 - total % 10) % 10 == check


def _normalize(raw: str) -> str | None:
    code = raw.strip()
    if len(code) == 12 and code.isdigit():
        code = "0" + code
    if len(code) != 13 or not code.isdigit():
        return None
    if not _gtin_check_digit_valid(code):
        return None
    return code


def add_upcs(db: Session, codes: list[str]) -> int:
    normalized: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()
    for raw in codes:
        code = _normalize(raw)
        if code is None:
            invalid.append(raw)
            continue
        if code in seen:
            continue
        seen.add(code)
        normalized.append(code)

    if invalid:
        raise InvalidUpcFormat(invalid)

    added = 0
    for code in normalized:
        exists = db.execute(sa.select(UpcCode).where(UpcCode.code == code)).scalar_one_or_none()
        if exists is not None:
            continue
        db.add(UpcCode(code=code, status=UpcStatus.available))
        added += 1
    db.flush()
    return added


def assign_upc(db: Session, release_id: UUID) -> str:
    release = db.get(Release, release_id)
    if release is None:
        raise UpcError(f"Release {release_id} not found")
    if release.upc is not None:
        raise AlreadyAssigned(f"Release {release_id} already has UPC {release.upc}")

    row = db.execute(
        sa.select(UpcCode)
        .where(UpcCode.status == UpcStatus.available)
        .order_by(UpcCode.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise PoolEmpty("UPC pool empty — add codes in Settings")

    row.status = UpcStatus.assigned
    row.release_id = release_id
    row.assigned_at = datetime.now(timezone.utc)
    release.upc = row.code
    db.flush()
    return row.code
