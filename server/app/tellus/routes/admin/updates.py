"""Tell-Us internal admin — changelog.

Gated at the router level by require_tellus_admin (TELLUS_ADMIN_EMAILS
allowlist), NOT the consumer/brand account_type split every other tellus
route uses. Not a company/feature-flag surface — Tell-Us has no tenant model.
"""
import json

from fastapi import APIRouter, Depends

from ....database import get_connection
from ...dependencies import require_tellus_admin

router = APIRouter(dependencies=[Depends(require_tellus_admin)])


@router.get("/admin/updates")
async def list_tellus_admin_updates():
    """Product changelog shown at /tellus/admin/updates, newest first."""
    async with get_connection() as conn:
        rows = await conn.fetch("""
            SELECT id, date, category, title, summary, whats_new, how_to_use, setup, notes, tag
            FROM tellus_admin_updates
            ORDER BY position ASC
        """)
        out = []
        for r in rows:
            d = dict(r)
            d["date"] = d["date"].isoformat()
            for col in ("whats_new", "how_to_use", "setup", "notes"):
                if isinstance(d[col], str):
                    d[col] = json.loads(d[col])
            out.append({
                "id": d["id"],
                "date": d["date"],
                "category": d["category"],
                "title": d["title"],
                "summary": d["summary"],
                "whatsNew": d["whats_new"],
                "howToUse": d["how_to_use"],
                "setup": d["setup"],
                "notes": d["notes"],
                "tag": d["tag"],
            })
        return out
