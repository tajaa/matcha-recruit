"""The Picture Editor's models (SlimSAM, for cutting a subject out of its
background): run in the owner's browser, served from our own origin so the
dashboard needs no other origin, and addressed by sha256 like the faces.

`models_manifest.json` pins the files (source, revision, licence, sha, size);
`server/scripts/fetch_magazine_models.py` fetches them at that revision,
checks them, and writes them to `CAPPE_MODELS_DIR` or uploads them to storage
(`cappe/models/<sha>.onnx`). Only files in the manifest are ever served.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .....core.services.storage import get_storage

MODEL_KEY = "cappe/models/{sha}.onnx"
_cache: dict[str, bytes] = {}


@lru_cache(maxsize=1)
def manifest() -> dict:
    return json.loads((Path(__file__).with_name("models_manifest.json")).read_text())


def by_sha(sha: str) -> Optional[dict]:
    for model in manifest()["models"].values():
        for f in model["files"].values():
            if f["sha"] == sha:
                return f
    return None


def _local(sha: str) -> Optional[bytes]:
    root = os.environ.get("CAPPE_MODELS_DIR")
    if not root:
        return None
    path = Path(root) / f"{sha}.onnx"
    return path.read_bytes() if path.is_file() else None


async def model_bytes(sha: str) -> Optional[bytes]:
    """A model file's bytes, checked against its sha (kept in memory once read:
    the two files are about 14 MB)."""
    if sha in _cache:
        return _cache[sha]
    data = await asyncio.to_thread(_local, sha) or await get_storage().get_key(MODEL_KEY.format(sha=sha))
    if data is None or hashlib.sha256(data).hexdigest() != sha:
        return None
    _cache[sha] = data
    return data
