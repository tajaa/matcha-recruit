"""Build Gummfit Studio's graphics bank and (optionally) upload it.

Sources, each pinned so every environment gets the same bytes:
  * Lucide icons (`lucide-static` 1.59.0 from npm, checked by sha256): ISC,
    with the icons it took from Feather under MIT;
  * Microsoft Fluent Emoji, the flat style, at a pinned commit of
    microsoft/fluentui-emoji (a sparse clone: only the flat SVGs and their
    metadata): MIT;
  * our own shapes, badges, dividers and patterns
    (`app/cappe/services/magazine/studio/graphics_own.py`): CC0.

Every file goes through `graphics.clean_svg` and is saved as `<sha>.svg` in
`--out`. The manifest (`studio/graphics_manifest.json`) and the licences
(`studio/graphics_licenses.txt`) are written next to the code, committed.
`--upload` puts each file in storage at `cappe/graphics/<sha>.svg`, where
`/api/cappe/public/graphics/<sha>.svg` reads it; run it once per environment,
after a `--dry-run`. Point `CAPPE_GRAPHICS_DIR` at `--out` to serve them
without uploading (dev).

    cd server
    venv/bin/python scripts/build_studio_graphics.py --out /tmp/graphics
    venv/bin/python scripts/build_studio_graphics.py --out /tmp/graphics --upload --dry-run
    venv/bin/python scripts/build_studio_graphics.py --out /tmp/graphics --upload

Needs `git` (for the sparse clone) and network access.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.cappe.services.magazine.studio import graphics, graphics_own  # noqa: E402

LUCIDE_VERSION = "1.59.0"
LUCIDE_URL = f"https://registry.npmjs.org/lucide-static/-/lucide-static-{LUCIDE_VERSION}.tgz"
LUCIDE_SHA256 = "39e2f835692c193233ac7bcdf34eb0cc2da0f839fd9f3674c34d2751bccf37f0"
FLUENT_REPO = "https://github.com/microsoft/fluentui-emoji.git"
FLUENT_COMMIT = "1ffb34c752ecf5d402f04cfb4b392c77f57c54bc"
LICENSES = graphics.MANIFEST.with_name("graphics_licenses.txt")
MAX_TAGS = 8
FLUENT_SETS = {  # Fluent's groups, as the Stickers tab names them
    "Smileys & Emotion": "Faces", "People & Body": "People", "Animals & Nature": "Animals and nature",
    "Food & Drink": "Food and drink", "Travel & Places": "Travel and places", "Activities": "Activities",
    "Objects": "Objects", "Symbols": "Symbols", "Flags": "Flags",
}


def _entry(source: str, slug: str, name: str, group: str, tags: list[str], svg: bytes, fit: str, mono: bool,
           out: Path, extra: dict | None = None) -> dict | None:
    try:
        clean, w, h = graphics.clean_svg(svg)
    except graphics.SvgError as exc:
        print(f"skipping {source}/{slug}: {exc}")
        return None
    sha = hashlib.sha256(clean).hexdigest()
    (out / f"{sha}.svg").write_bytes(clean)
    seen: dict[str, None] = {}
    for t in tags:
        t = " ".join(str(t).lower().split())
        if t and t != name.lower():
            seen.setdefault(t, None)
    return {"id": f"{source}/{slug}", "sha": sha, "name": name, "group": group, "tags": list(seen)[:MAX_TAGS],
            "mono": mono, "fit": fit, "w": round(w, 2), "h": round(h, 2), "source": source, **(extra or {})}


def lucide(work: Path, out: Path) -> tuple[list[dict], str]:
    with urllib.request.urlopen(LUCIDE_URL, timeout=120) as res:  # noqa: S310 (pinned, checked below)
        data = res.read()
    got = hashlib.sha256(data).hexdigest()
    if got != LUCIDE_SHA256:
        raise SystemExit(f"lucide-static {LUCIDE_VERSION}: sha256 {got}, expected {LUCIDE_SHA256}")
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(work / "lucide", filter="data")
    pkg = work / "lucide" / "package"
    tags = json.loads((pkg / "tags.json").read_text(encoding="utf-8"))
    entries = []
    for path in sorted((pkg / "icons").glob("*.svg")):
        slug = path.stem
        name = slug.replace("-", " ").capitalize()
        e = _entry("lucide", slug, name, "icons", [*slug.split("-"), *tags.get(slug, [])], path.read_bytes(),
                   "contain", True, out)
        if e:
            entries.append(e)
    return entries, (pkg / "LICENSE").read_text(encoding="utf-8")


def fluent(work: Path, out: Path) -> tuple[list[dict], str]:
    repo = work / "fluent"
    run = lambda *a: subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)  # noqa: E731
    repo.mkdir()
    run("init", "-q")
    run("remote", "add", "origin", FLUENT_REPO)
    run("config", "core.sparseCheckout", "true")
    (repo / ".git" / "info" / "sparse-checkout").write_text(
        "LICENSE\n/assets/*/Flat/*.svg\n/assets/*/Default/Flat/*.svg\n/assets/*/metadata.json\n")
    run("fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", FLUENT_COMMIT)
    run("checkout", "-q", "FETCH_HEAD")
    entries = []
    for folder in sorted(p for p in (repo / "assets").iterdir() if p.is_dir()):
        meta_path = folder / "metadata.json"
        files = sorted(folder.glob("Flat/*.svg")) or sorted(folder.glob("Default/Flat/*.svg"))
        if not meta_path.is_file() or not files:
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        slug = re.sub(r"[^a-z0-9]+", "-", folder.name.lower()).strip("-")
        group = meta.get("group") or ""
        e = _entry("fluent", slug, folder.name[:1].upper() + folder.name[1:], "stickers",
                   [*(meta.get("keywords") or []), FLUENT_SETS.get(group, group)], files[0].read_bytes(), "contain",
                   False, out, {"set": FLUENT_SETS.get(group, "Other")})
        if e:
            entries.append(e)
    return entries, (repo / "LICENSE").read_text(encoding="utf-8")


def own(out: Path) -> list[dict]:
    """Ours, in the order `graphics_own` lists them (the side panel shows them so)."""
    entries = []
    for k, (slug, name, group, tags, svg, fit) in enumerate(graphics_own.all_graphics()):
        e = _entry("gummfit", slug, name, group, tags, svg.encode(), fit, True, out, {"order": k})
        if e:
            entries.append(e)
    return entries


def build(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        icons, lucide_license = lucide(work, out)
        stickers, fluent_license = fluent(work, out)
    entries = own(out) + icons + stickers
    order = {g: k for k, g in enumerate(graphics.GROUPS)}
    entries.sort(key=lambda e: (order[e["group"]], e["source"] != "gummfit", e.get("order", 0), e["name"].lower()))
    for e in entries:
        e.pop("order", None)
    shas = [e["sha"] for e in entries]
    if len(set(shas)) != len(shas):
        dupes = {s for s in shas if shas.count(s) > 1}
        entries = [e for k, e in enumerate(entries) if e["sha"] not in dupes or shas.index(e["sha"]) == k]
    data = {
        "version": hashlib.sha256("".join(e["sha"] for e in entries).encode()).hexdigest()[:16],
        "sources": [
            {"id": "gummfit", "name": "Gummfit", "licence": "CC0-1.0", "url": None},
            {"id": "lucide", "name": f"Lucide {LUCIDE_VERSION}", "licence": "ISC (Feather-derived icons: MIT)",
             "url": "https://lucide.dev"},
            {"id": "fluent", "name": "Microsoft Fluent Emoji (flat)", "licence": "MIT",
             "url": f"https://github.com/microsoft/fluentui-emoji/tree/{FLUENT_COMMIT}"},
        ],
        "graphics": entries,
    }
    graphics.MANIFEST.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    LICENSES.write_text(
        "Gummfit Studio graphics: licences of the sources they come from.\n\n"
        f"== Lucide {LUCIDE_VERSION} (icons) ==\n\n{lucide_license.strip()}\n\n"
        f"== Microsoft Fluent Emoji, flat style ({FLUENT_COMMIT}) ==\n\n{fluent_license.strip()}\n\n"
        "== Gummfit shapes, badges, dividers and patterns ==\n\nCC0 1.0: no rights reserved.\n", encoding="utf-8")
    counts = {g: sum(e["group"] == g for e in entries) for g in graphics.GROUPS}
    print(f"{len(entries)} graphics: {counts}")
    return data


async def upload(out: Path, dry_run: bool) -> None:
    from app.core.services.storage import get_storage

    storage = get_storage()
    for e in json.loads(graphics.MANIFEST.read_text(encoding="utf-8"))["graphics"]:
        key = graphics.GRAPHIC_KEY.format(sha=e["sha"])
        if await storage.get_key(key) is not None:
            continue
        print(("would upload " if dry_run else "uploading ") + key)
        if not dry_run:
            await storage.put_key(key, (out / f"{e['sha']}.svg").read_bytes(), "image/svg+xml")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, type=Path, help="where the files go")
    ap.add_argument("--upload", action="store_true", help="upload them to storage")
    ap.add_argument("--dry-run", action="store_true", help="with --upload: say what would be uploaded")
    args = ap.parse_args()
    build(args.out)
    if args.upload:
        asyncio.run(upload(args.out, args.dry_run))


if __name__ == "__main__":
    main()
