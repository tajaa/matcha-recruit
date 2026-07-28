"""Pure message/SSE shaping helpers for matcha-work.

Lifted out of ``routes/matcha_work/_shared.py`` (refactor round 2, stage 5 audit).
None of these touch a Request, a Response, or a dependency — they format an SSE
frame, coerce a JSONB column, cap a byte count, and map a DB row to a Pydantic
model. They lived in the routes package only because that is where the flat
``matcha_work.py`` happened to leave them, which forced
``services/matcha_work/turn_pipeline.py`` to import back into ``routes/`` at
module scope for names it calls in nearly every stage.

``routes/matcha_work/_shared.py`` re-exports all four, so every
``from ._shared import _sse_data`` in the routes package is unchanged.
"""
import json

from app.core.services.storage import get_storage
from app.matcha.models.matcha_work.matcha_work import MWMessageOut

# Cap on extracted attachment text fed to the model as context.
THREAD_FILE_TEXT_CAP = 40000


def _sse_data(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _row_to_message(row: dict) -> MWMessageOut:
    raw_meta = row.get("metadata")
    if isinstance(raw_meta, str):
        try:
            raw_meta = json.loads(raw_meta)
        except (json.JSONDecodeError, TypeError):
            raw_meta = None
    # Strip the server-only extracted `text` from file attachments before the
    # message reaches the client. That text is AI context (can be tens of KB),
    # not display data — the client only needs url/filename/size/kind.
    # Also presign s3:// urls so the desktop chip is clickable (CloudFront
    # urls pass through; stored url stays stable for re-extraction).
    if isinstance(raw_meta, dict) and isinstance(raw_meta.get("attachments"), list):
        _storage = get_storage()
        cleaned = []
        for a in raw_meta["attachments"]:
            if not isinstance(a, dict):
                cleaned.append(a)
                continue
            a = {k: v for k, v in a.items() if k != "text"}
            url = a.get("url") or ""
            if isinstance(url, str) and url.startswith("s3://"):
                signed = _storage.get_presigned_download_url(url, expires_in=3600)
                if signed:
                    a["url"] = signed
            cleaned.append(a)
        raw_meta = {**raw_meta, "attachments": cleaned}
    return MWMessageOut(
        id=row["id"],
        thread_id=row["thread_id"],
        role=row["role"],
        content=row["content"],
        version_created=row.get("version_created"),
        metadata=raw_meta,
        created_at=row["created_at"],
    )
