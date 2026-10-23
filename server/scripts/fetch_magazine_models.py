"""Fetch Gummfit Studio's Picture Editor models and (optionally) upload them.

The models (`app/cappe/services/magazine/studio/models_manifest.json`: SlimSAM,
Apache-2.0, for cutting a subject out of its background) are fetched from
their source at the pinned revision and checked against the manifest's
sha256. Each file is saved as `<sha>.onnx`. `--upload` puts each in storage
at `cappe/models/<sha>.onnx`, where `/studio/models/{sha}.onnx`
(`routes/pictures.py`) reads it; run it once per environment, after a
`--dry-run`.

    cd server
    venv/bin/python scripts/fetch_magazine_models.py --out /tmp/models
    venv/bin/python scripts/fetch_magazine_models.py --out /tmp/models --upload --dry-run
    venv/bin/python scripts/fetch_magazine_models.py --out /tmp/models --upload

Point `CAPPE_MODELS_DIR` at `--out` to serve them without uploading (dev).
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.cappe.services.magazine.studio.models import MODEL_KEY, manifest  # noqa: E402


def files() -> list[tuple[str, dict]]:
    """Each file to fetch, with the URL it comes from at the pinned revision."""
    out = []
    for model in manifest()["models"].values():
        for f in model["files"].values():
            out.append((f"{model['source']}/resolve/{model['revision']}/{f['path']}", f))
    return out


def fetch(out: Path) -> None:
    for url, f in files():
        path = out / f"{f['sha']}.onnx"
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == f["sha"]:
            continue
        print(f"fetching {url}")
        with urllib.request.urlopen(url, timeout=120) as res:  # noqa: S310 (a pinned https URL from the manifest)
            data = res.read()
        got = hashlib.sha256(data).hexdigest()
        if got != f["sha"]:
            raise SystemExit(f"{f['path']}: sha256 {got}, the manifest says {f['sha']}")
        path.write_bytes(data)


async def upload(out: Path, dry_run: bool) -> None:
    from app.core.services.storage import get_storage

    storage = get_storage()
    for _, f in files():
        key = MODEL_KEY.format(sha=f["sha"])
        if await storage.get_key(key) is not None:
            continue
        print(("would upload " if dry_run else "uploading ") + key)
        if not dry_run:
            await storage.put_key(key, (out / f"{f['sha']}.onnx").read_bytes(), "application/octet-stream")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, type=Path, help="where the model files go")
    ap.add_argument("--upload", action="store_true", help="upload them to storage")
    ap.add_argument("--dry-run", action="store_true", help="with --upload: say what would be uploaded")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    fetch(args.out)
    if args.upload:
        asyncio.run(upload(args.out, args.dry_run))


if __name__ == "__main__":
    main()
