"""Cappe style presets — a per-account library of reusable looks.

`kind='theme'` stores a `theme_config` style subset; `kind='section'` stores a
block `_design` bag. On save, `data` is re-validated through the premium gate so
a non-premium account can't smuggle premium tokens into a preset and re-apply it.
"""
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount, CappeStylePreset, CappeStylePresetCreate
from ..services.design_gate import gate_content, gate_theme
from ._shared import loads

router = APIRouter()

_COLS = "id, name, kind, data, created_at"


def _row_to_dict(row) -> dict:
    d = dict(row)
    d["data"] = loads(d.get("data"))
    return d


@router.get("/style-presets", response_model=list[CappeStylePreset])
async def list_style_presets(account: CappeAccount = Depends(require_cappe_account)):
    """List the account's saved style presets, newest first."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"SELECT {_COLS} FROM cappe_style_presets WHERE account_id = $1 ORDER BY created_at DESC",
            account.id,
        )
    return [_row_to_dict(r) for r in rows]


@router.post("/style-presets", response_model=CappeStylePreset, status_code=status.HTTP_201_CREATED)
async def create_style_preset(
    body: CappeStylePresetCreate, account: CappeAccount = Depends(require_cappe_account)
):
    """Save a reusable look. `data` is gate-validated for the account's plan so a
    preset can never carry premium tokens a non-premium account isn't entitled to."""
    if body.kind == "theme":
        data = gate_theme(body.data, account.plan)
    else:
        # Reuse the content gate: wrap the _design bag as a one-block content, gate,
        # then unwrap — a non-premium account's section preset becomes empty.
        wrapped = gate_content({"blocks": [{"type": "_preset", "_design": body.data}]}, account.plan)
        blocks = wrapped.get("blocks") if isinstance(wrapped, dict) else []
        data = (blocks[0].get("_design") if blocks and isinstance(blocks[0], dict) else {}) or {}
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""INSERT INTO cappe_style_presets (account_id, name, kind, data)
                VALUES ($1, $2, $3, $4) RETURNING {_COLS}""",
            account.id, body.name, body.kind, json.dumps(data),
        )
    return _row_to_dict(row)


@router.delete("/style-presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_style_preset(preset_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """Delete one owned preset."""
    async with get_connection() as conn:
        deleted = await conn.fetchval(
            "DELETE FROM cappe_style_presets WHERE id = $1 AND account_id = $2 RETURNING id",
            preset_id, account.id,
        )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preset not found")
