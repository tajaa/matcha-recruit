"""Admin WC rate-data import (`/admin/wc-rates/*`, require_admin).

Load a licensed NCCI / state-bureau feed via CSV into wc_state_rates +
wc_class_codes, replacing the illustrative demo seed. CSV-only ingestion: the
rate data itself is licensed and must be supplied by the user; this is the
pipeline that consumes it. Idempotent upserts (state+effective_date / state+class).
"""

import csv
import io
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile

from ...database import get_connection
from ...core.dependencies import require_admin

router = APIRouter()


def _read_csv(data: bytes) -> list[dict]:
    text = data.decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _trend(pct: Optional[float]) -> str:
    if pct is None or pct == 0:
        return "flat"
    return "increase" if pct > 0 else "decrease"


@router.get("/summary")
async def summary(current_user=Depends(require_admin)):
    """Row counts by source for both tables — shows seed vs licensed-import coverage."""
    async with get_connection() as conn:
        sr = await conn.fetch("SELECT source, COUNT(*) AS n FROM wc_state_rates GROUP BY source ORDER BY source")
        cc = await conn.fetch("SELECT source, COUNT(*) AS n FROM wc_class_codes GROUP BY source ORDER BY source")
    return {
        "state_rates": {r["source"]: int(r["n"]) for r in sr},
        "class_codes": {r["source"]: int(r["n"]) for r in cc},
    }


@router.post("/state-rates")
async def import_state_rates(file: UploadFile = File(...), source: str = Form("ncci-import"),
                             current_user=Depends(require_admin)):
    """CSV columns: state, loss_cost_change_pct, effective_date, trend?, note?"""
    rows = _read_csv(await file.read())
    imported = 0
    errors: list[str] = []
    async with get_connection() as conn:
        for i, r in enumerate(rows, 1):
            try:
                state = (r.get("state") or "").strip().upper()[:2]
                if not state:
                    continue
                raw_pct = r.get("loss_cost_change_pct")
                pct = float(raw_pct) if raw_pct not in (None, "") else None
                eff = _parse_date(r.get("effective_date")) or date.today()
                trend = (r.get("trend") or "").strip().lower() or _trend(pct)
                if trend not in ("increase", "decrease", "flat"):
                    trend = _trend(pct)
                await conn.execute(
                    """
                    INSERT INTO wc_state_rates (state, loss_cost_change_pct, effective_date, trend, source, note)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT ON CONSTRAINT uq_wc_state_rate DO UPDATE SET
                        loss_cost_change_pct = EXCLUDED.loss_cost_change_pct, trend = EXCLUDED.trend,
                        source = EXCLUDED.source, note = EXCLUDED.note, updated_at = NOW()
                    """,
                    state, pct, eff, trend, source, (r.get("note") or None),
                )
                imported += 1
            except Exception as exc:  # noqa: BLE001 — surface per-row, keep importing
                errors.append(f"row {i}: {exc}")
    return {"imported": imported, "errors": errors[:20]}


@router.post("/class-codes")
async def import_class_codes(file: UploadFile = File(...), source: str = Form("ncci-import"),
                             current_user=Depends(require_admin)):
    """CSV columns: state?, class_code, description, base_rate?"""
    rows = _read_csv(await file.read())
    imported = 0
    errors: list[str] = []
    async with get_connection() as conn:
        for i, r in enumerate(rows, 1):
            try:
                code = (r.get("class_code") or "").strip()
                if not code:
                    continue
                state = (r.get("state") or "US").strip().upper()[:2] or "US"
                desc = (r.get("description") or "").strip() or code
                raw_rate = r.get("base_rate")
                rate = float(raw_rate) if raw_rate not in (None, "") else None
                await conn.execute(
                    """
                    INSERT INTO wc_class_codes (state, class_code, description, base_rate, source)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT ON CONSTRAINT uq_wc_class_code DO UPDATE SET
                        description = EXCLUDED.description, base_rate = EXCLUDED.base_rate, source = EXCLUDED.source
                    """,
                    state, code, desc, rate, source,
                )
                imported += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"row {i}: {exc}")
    return {"imported": imported, "errors": errors[:20]}


_TEMPLATES = {
    "state-rates": ("wc_state_rates_template.csv",
                    "state,loss_cost_change_pct,effective_date,trend,note\n"
                    "CA,-2.0,2026-01-01,decrease,\n"
                    "NV,21.9,2026-01-01,increase,\n"),
    "class-codes": ("wc_class_codes_template.csv",
                    "state,class_code,description,base_rate\n"
                    "CA,8810,Clerical office employees,0.14\n"
                    "CA,5403,Carpentry,8.50\n"),
}


@router.get("/template/{kind}")
async def template(kind: str, current_user=Depends(require_admin)):
    tpl = _TEMPLATES.get(kind)
    if not tpl:
        raise HTTPException(status_code=404, detail="Unknown template")
    filename, body = tpl
    return Response(content=body, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
