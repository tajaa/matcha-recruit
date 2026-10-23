"""Build Gummfit Studio's faces and (optionally) upload them.

Every face in the magazine catalog (`app/cappe/services/magazine/fonts.FONTS`:
each family's weights and italics) is built from google/fonts (OFL/Apache/
UFL) at a pinned commit:

  * a variable font is instanced at the weight (every other axis at its
    default), a static one taken as it is;
  * subset to Latin (with typographic punctuation), every OpenType layout
    feature kept, hinting dropped;
  * vertical metrics made the same in every table any browser might read
    (hhea = OS/2 typo = OS/2 win, line gap 0, USE_TYPO_METRICS on), so all
    of them put a baseline where the Studio measured it;
  * saved without a new timestamp, so a build is the same bytes everywhere.

Each face is named by its sha256. `--manifest` writes the list the server
and the Studio read (`studio/fonts_manifest.json`, committed). `--upload`
puts each face in storage at `cappe/fonts/<sha>.ttf`, where the font route
(`routes/public/fonts.py`) reads it; run it once per environment, after a
`--dry-run`.

    cd server
    venv/bin/python scripts/build_magazine_fonts.py --out /tmp/faces --manifest
    venv/bin/python scripts/build_magazine_fonts.py --out /tmp/faces --upload --dry-run
    venv/bin/python scripts/build_magazine_fonts.py --out /tmp/faces --upload

`--families "Inter,Source Serif 4"` builds only those (a quick local build;
point `CAPPE_FONTS_DIR` at `--out` to serve them without uploading).
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fontTools import subset  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402
from fontTools.varLib import instancer  # noqa: E402

from app.cappe.services.magazine.fonts import FONTS  # noqa: E402
from app.cappe.services.magazine.studio.fonts import MANIFEST  # noqa: E402

# google/fonts main on 2026-10-21. Change it only together with a full
# rebuild and upload: every face's bytes (and so its sha) may change.
COMMIT = "45e3d5269e4a17d823f6d84470bc084dc5ae46f6"
RAW = f"https://raw.githubusercontent.com/google/fonts/{COMMIT}"
LICENSES = ("ofl", "apache", "ufl")

LATIN = sorted({*range(0x20, 0x7F), *range(0xA0, 0x180), *range(0x2010, 0x2028), *range(0x2030, 0x203B),
                0x2044, 0x20AC, 0x2122, 0x2212, 0xFB01, 0xFB02, 0x0131, 0x02C6, 0x02DA, 0x02DC})
_FONT = re.compile(r"fonts\s*\{(.*?)\}", re.S)
_FIELD = re.compile(r'(\w+):\s*"?([^"\n]*)"?')


def _get(url: str, cache: Path) -> bytes | None:
    path = cache / re.sub(r"[^A-Za-z0-9._-]", "_", url.split(COMMIT + "/", 1)[-1])
    if path.exists():
        return path.read_bytes()
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    path.write_bytes(data)
    return data


def family_dir(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def sources(name: str, cache: Path) -> tuple[str, list[dict]]:
    """The family's directory and its font files (style, weight, filename)."""
    for lic in LICENSES:
        meta = _get(f"{RAW}/{lic}/{family_dir(name)}/METADATA.pb", cache)
        if meta:
            files = [dict(_FIELD.findall(block)) for block in _FONT.findall(meta.decode("utf-8"))]
            return f"{lic}/{family_dir(name)}", files
    raise SystemExit(f"{name}: not found in google/fonts")


def _pick(files: list[dict], weight: int, italic: bool) -> dict | None:
    style = "italic" if italic else "normal"
    mine = [f for f in files if f.get("style") == style]
    variable = [f for f in mine if "[" in f.get("filename", "")]
    if variable:
        return variable[0]
    return next((f for f in mine if int(f.get("weight", 0)) == weight), None)


def build_face(font: TTFont, weight: int) -> TTFont:
    if "fvar" in font:
        axes = {a.axisTag: a for a in font["fvar"].axes}
        loc = {tag: a.defaultValue for tag, a in axes.items()}
        if "wght" in axes:
            loc["wght"] = max(axes["wght"].minValue, min(axes["wght"].maxValue, weight))
        font = instancer.instantiateVariableFont(font, loc, updateFontNames=False)
    opts = subset.Options()
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.name_languages = ["*"]
    opts.notdef_outline = True
    opts.hinting = False
    opts.glyph_names = False
    opts.drop_tables += ["DSIG", "STAT"]
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=LATIN)
    sub.subset(font)
    os2, hhea = font["OS/2"], font["hhea"]
    asc, desc = os2.sTypoAscender, os2.sTypoDescender  # desc is negative
    if asc <= 0:  # a face without typo metrics: take its hhea's
        asc, desc = hhea.ascent, hhea.descent
        os2.sTypoAscender, os2.sTypoDescender = asc, desc
    hhea.ascent, hhea.descent, hhea.lineGap = asc, desc, 0
    os2.sTypoLineGap = 0
    os2.usWinAscent, os2.usWinDescent = max(asc, 0), max(-desc, 0)
    if 2 <= os2.version < 4:
        os2.version = 4  # the flag below is read from version 4 on; 2 and 3 have the same fields
    os2.fsSelection |= 1 << 7  # USE_TYPO_METRICS
    return font


def _features(font: TTFont) -> list[str]:
    tags: set[str] = set()
    for table in ("GSUB", "GPOS"):
        if table in font and font[table].table.FeatureList:
            tags |= {fr.FeatureTag for fr in font[table].table.FeatureList.FeatureRecord}
    return sorted(tags)


def build(families: list[str], out: Path, cache: Path) -> list[dict]:
    faces = []
    for name in families:
        _cat, _body, weights, italics = FONTS[name]
        where, files = sources(name, cache)
        styles = [(w, False) for w in weights] + [(w, True) for w in italics]
        for weight, italic in styles:
            src = _pick(files, weight, italic)
            if src is None:
                print(f"  {name} {weight}{' italic' if italic else ''}: no source, skipped", file=sys.stderr)
                continue
            data = _get(f"{RAW}/{where}/{src['filename']}", cache)
            if data is None:
                print(f"  {name}: {src['filename']} missing, skipped", file=sys.stderr)
                continue
            font = build_face(TTFont(BytesIO(data), recalcTimestamp=False), weight)
            buf = BytesIO()
            font.recalcTimestamp = False
            font.save(buf)
            ttf = buf.getvalue()
            sha = hashlib.sha256(ttf).hexdigest()
            (out / f"{sha}.ttf").write_bytes(ttf)
            os2 = font["OS/2"]
            faces.append({
                "family": name, "weight": weight, "italic": italic, "sha": sha, "bytes": len(ttf),
                "upm": font["head"].unitsPerEm, "asc": os2.sTypoAscender, "desc": os2.sTypoDescender,
                "cap": getattr(os2, "sCapHeight", 0) or 0, "x": getattr(os2, "sxHeight", 0) or 0,
                "features": _features(font),
            })
        print(f"{name}: {sum(1 for f in faces if f['family'] == name)} faces", flush=True)
    return faces


async def upload(faces: list[dict], out: Path, dry_run: bool) -> None:
    from app.cappe.routes.public.fonts import FONT_KEY
    from app.core.services.storage import get_storage

    storage = get_storage()
    for f in faces:
        key = FONT_KEY.format(sha=f["sha"])
        if await storage.get_key(key) is not None:
            continue
        print(("would upload " if dry_run else "uploading ") + key)
        if not dry_run:
            await storage.put_key(key, (out / f"{f['sha']}.ttf").read_bytes(), "font/ttf")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, type=Path, help="where the built faces go")
    ap.add_argument("--families", default="", help="comma-separated families (default: the whole catalog)")
    ap.add_argument("--manifest", action="store_true", help="write studio/fonts_manifest.json")
    ap.add_argument("--upload", action="store_true", help="upload the faces in the manifest to storage")
    ap.add_argument("--dry-run", action="store_true", help="with --upload: say what would be uploaded")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    cache = args.out / "_sources"
    cache.mkdir(exist_ok=True)
    if args.upload:
        faces = json.loads(MANIFEST.read_text())["faces"]
        missing = [f for f in faces if not (args.out / f"{f['sha']}.ttf").exists()]
        if missing:
            families = sorted({f["family"] for f in missing})
            print(f"building {len(missing)} faces first ({', '.join(families)})")
            built = {f["sha"] for f in build(families, args.out, cache)}
            lost = [f for f in missing if f["sha"] not in built]
            if lost:
                raise SystemExit(f"{len(lost)} faces built to other bytes than the manifest's: rebuild the manifest")
        asyncio.run(upload(faces, args.out, args.dry_run))
        return
    names = [n.strip() for n in args.families.split(",") if n.strip()] or list(FONTS)
    unknown = [n for n in names if n not in FONTS]
    if unknown:
        raise SystemExit(f"not in the catalog: {', '.join(unknown)}")
    faces = build(names, args.out, cache)
    print(f"{len(faces)} faces, {sum(f['bytes'] for f in faces) / 1e6:.1f} MB")
    if args.manifest:
        if args.families:
            raise SystemExit("--manifest builds the whole catalog: leave out --families")
        MANIFEST.write_text(json.dumps({"version": COMMIT, "faces": faces}, indent=1) + "\n")
        print(f"wrote {MANIFEST}")


if __name__ == "__main__":
    main()
