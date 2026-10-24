"""A paged story's document, checked and reshaped before it is stored.

    {"v": 1, "size": {"w": 612, "h": 792}, "facing": true,
     "margins": {"t", "b", "i", "o"}, "cols": {"n", "g"}, "baseline": {"start", "step"},
     "grid": {"step"}, "bleed": 9, "units": "in", "paper": "#ffffff",
     "pages": [{"id": "p1"}, ...],
     "guides": [{"id", "page", "axis": "v"|"h", "at"}],
     "items": [{"id", "kind", "page", "x", "y", "w", "h", "rot", ...}],
     "threads": [{"id", "frames": [item ids], "paras": [...], "comp": {"lines": [...]}}],
     "paywall_page": 2 | null}

Every length is in points (2 decimals). An item sits on one page, placed in
that page's coordinates; it may run off its edge (across the spread's gutter,
say). Items stack in list order, the first at the bottom.

Text lives in threads. A thread's `frames` are the text frames it flows
through, in order; a text frame in no thread is empty. A thread's paragraphs
are flat: `{"runs": [{"t": "words", ...character attributes}], ...paragraph
attributes}`, each attribute stored only when it isn't its default
(`limits.CHAR_DEFAULTS`, `limits.PARA_DEFAULTS`). A paragraph's text never
holds a paragraph break; "\\n" is a line break inside it.

`comp` is the thread's composition, set by the Studio: one line per entry,
`[frame, para, start, end, x, baseline, width, align]` — the frame's index in
`frames`, the paragraph's index, the line's text as a UTF-16 range of that
paragraph's text (the browser's own string offsets; `slice16`), the box the
line is aligned in (x and width, from the frame's left) and its baseline
(from the frame's top), and how it is aligned (`limits.LINE_ALIGNS`). The
server never trusts it to be right, only to be possible: the lines must walk
the text in order, leaving out nothing but the spaces and line breaks they
break at, and stop (overset) only at the end. A composition that doesn't is
dropped, and the page falls back to flowed text until the Studio sets it
again.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any, Iterable, Mapping, Optional
from uuid import UUID

from ..fonts import FONTS, has_italic, nearest_weight
from . import cuts
from . import fonts as faces
from . import graphics
from . import limits as L

_ID = re.compile(r"^[a-z0-9]{1,12}$")
_HEX = re.compile(r"^#[0-9a-f]{6}(?:[0-9a-f]{2})?$")
# Half of a character, and controls other than a line break.
_DROP = re.compile(r"[\ud800-\udfff\x00-\x09\x0b-\x1f\x7f]")


class DocError(ValueError):
    """The document can't be stored as given; the message is for the owner."""


# ── numbers, strings, colours ────────────────────────────────────────────────

def num(value: Any, lo: float, hi: float, default: float, places: int = 2) -> float:
    """A number in [lo, hi] rounded half up to `places` decimals, as the client
    rounds (`Math.floor(n * 100 + 0.5) / 100`), never -0; a whole number is
    an int (stored as `12`, as JavaScript writes it)."""
    if isinstance(value, bool):
        return default
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(n) or math.isinf(n):
        return default
    n = max(lo, min(hi, n))
    scale = 10 ** places
    v = math.floor(n * scale + 0.5) / scale + 0.0
    return int(v) if v == int(v) else v


def _int(value: Any, lo: int, hi: int, default: int) -> int:
    return int(num(value, lo, hi, default, 0))


def _choice(value: Any, choices: tuple, default: Any = None) -> Any:
    return value if value in choices else (choices[0] if default is None else default)


def _str(value: Any, limit: int) -> str:
    return _DROP.sub("", value).strip()[:limit] if isinstance(value, str) else ""


def _colour(value: Any, default: Optional[str]) -> Optional[str]:
    if isinstance(value, str) and _HEX.match(value.lower()):
        return value.lower()
    return default


def _id(value: Any, what: str) -> str:
    if isinstance(value, str) and _ID.match(value):
        return value
    raise DocError(f"A {what} in this story has a bad name. Reload the Studio and try again.")


def _asset_id(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    try:
        return str(UUID(str(value)))
    except ValueError as exc:
        raise DocError("A picture in this story isn't from your library.") from exc


def _stroke(raw: Any, default: Optional[dict] = None) -> Optional[dict]:
    if not isinstance(raw, dict):
        return default
    width = num(raw.get("w"), 0, L.STROKE_MAX, 0)
    if width <= 0:
        return default
    return {"c": _colour(raw.get("c"), "#1a1a1a"), "w": width}


# ── UTF-16 offsets (the browser's) ───────────────────────────────────────────

def len16(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def slice16(text: str, start: int, end: int) -> Optional[str]:
    """text[start:end] in UTF-16 code units, or None when a range cuts a
    character in half."""
    raw = text.encode("utf-16-le")[2 * start:2 * end]
    try:
        return raw.decode("utf-16-le")
    except UnicodeDecodeError:
        return None


# ── text ─────────────────────────────────────────────────────────────────────

def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return _DROP.sub("", value.replace("\t", " ").replace("\r\n", "\n").replace("\r", "\n"))


def ot_tags(value: Any) -> str:
    """OpenType tags as stored: allowed ones, each once, sorted, comma-separated."""
    if not isinstance(value, str) or not value:
        return ""
    return ",".join(sorted({t for t in value.split(",") if t in L.OT_TAGS}))


def _face(raw: dict) -> tuple[str, int, bool]:
    custom = faces.custom_face(raw.get("font"), raw.get("wt", L.CHAR_DEFAULTS["wt"]), raw.get("it"))
    if custom:
        return custom
    if cuts.cut(raw.get("font")):  # a Gummfit cut (cuts.py)
        font = raw["font"]
        wt = cuts.nearest_weight(font, raw.get("wt", L.CHAR_DEFAULTS["wt"]))
        return font, wt, bool(raw.get("it")) and cuts.has_italic(font, wt)
    font = raw.get("font") if raw.get("font") in FONTS else L.CHAR_DEFAULTS["font"]
    wt = nearest_weight(font, raw.get("wt", L.CHAR_DEFAULTS["wt"]))
    return font, wt, bool(raw.get("it")) and has_italic(font, wt)


def char_attrs(raw: dict) -> dict:
    """A run's character attributes, every one present."""
    d = L.CHAR_DEFAULTS
    font, wt, it = _face(raw)
    return {
        "font": font,
        "wt": wt,
        "it": it,
        "size": num(raw.get("size"), 1, L.SIZE_MAX, d["size"]),
        "track": _int(raw.get("track"), L.TRACK_MIN, L.TRACK_MAX, d["track"]),
        "color": _colour(raw.get("color"), d["color"]),
        "u": bool(raw.get("u")),
        "kern": _int(raw.get("kern"), L.KERN_MIN, L.KERN_MAX, d["kern"]),
        "ot": ot_tags(raw.get("ot")),
    }


def para_attrs(raw: dict) -> dict:
    """A paragraph's own attributes, every one present."""
    d = L.PARA_DEFAULTS
    li = num(raw.get("li"), 0, L.INDENT_MAX, d["li"])
    dc = _int(raw.get("dc"), 0, L.DROPCAP_LINES, d["dc"])
    return {
        "align": _choice(raw.get("align"), L.ALIGNS),
        "li": li,
        "ri": num(raw.get("ri"), 0, L.INDENT_MAX, d["ri"]),
        "fi": num(raw.get("fi"), -li, L.INDENT_MAX, d["fi"]),
        "sb": num(raw.get("sb"), 0, L.INDENT_MAX, d["sb"]),
        "sa": num(raw.get("sa"), 0, L.INDENT_MAX, d["sa"]),
        "lead": num(raw.get("lead"), 0, L.LEAD_MAX, d["lead"]),
        "role": _choice(raw.get("role"), L.ROLES),
        "dc": 0 if dc == 1 else dc,
        "dcn": _int(raw.get("dcn"), 1, L.DROPCAP_CHARS, d["dcn"]),
        "kw": _int(raw.get("kw"), 1, L.KEEP_MAX, d["kw"]),
        "ko": _int(raw.get("ko"), 1, L.KEEP_MAX, d["ko"]),
        "runt": _int(raw.get("runt"), 1, L.KEEP_MAX, d["runt"]),
    }


def _sparse(full: dict, defaults: dict) -> dict:
    return {k: v for k, v in full.items() if v != defaults[k]}


def _para(raw: Any, budget: list[int], identity=None) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    from .identity import ref
    identity = identity or {}
    style = ref(raw.get("style"), identity.get("paragraphs", []), "paragraph style")
    named = next((s for s in identity.get("paragraphs", []) if s["id"] == style), {})
    runs: list[dict] = []
    last_attrs: Optional[dict] = None
    raw_runs = raw.get("runs") if isinstance(raw.get("runs"), list) else []
    if len(raw_runs) > L.MAX_RUNS:
        raise DocError("A paragraph has too many changes of type. Simplify it.")
    for r in raw_runs:
        if not isinstance(r, dict):
            continue
        text = _clean_text(r.get("t"))
        character_style = ref(r.get("style"), identity.get("characters", []), "character style")
        character = next((s["char"] for s in identity.get("characters", []) if s["id"] == character_style), {})
        full = char_attrs({**named.get("char", {}), **character, **r})
        attrs = {k: v for k, v in full.items() if k in r} if style or character_style else _sparse(full, L.CHAR_DEFAULTS)
        if character_style:
            attrs["style"] = character_style
        swatch = ref(r.get("swatch"), identity.get("swatches", []), "swatch")
        if swatch:
            attrs["swatch"] = swatch
        last_attrs = attrs
        if not text:
            continue
        budget[0] -= len16(text)
        if runs and {k: v for k, v in runs[-1].items() if k != "t"} == attrs:
            runs[-1]["t"] += text
        else:
            runs.append({"t": text, **attrs})
    if budget[0] < 0:
        raise DocError("A text frame's story is too long. Split it into two.")
    if not runs:
        # An empty paragraph keeps its type, for the height of its line.
        runs = [{"t": "", **(last_attrs or {})}]
    full = para_attrs({**named.get("para", {}), **raw})
    attrs = {k: v for k, v in full.items() if k in raw} if style else _sparse(full, L.PARA_DEFAULTS)
    return {"runs": runs, **attrs, **({"style": style} if style else {})}


def para_text(p: dict) -> str:
    return "".join(r.get("t", "") for r in p.get("runs") or [])


# ── composition ──────────────────────────────────────────────────────────────

def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v: Any) -> bool:
    return (isinstance(v, (int, float)) and not isinstance(v, bool)
            and not math.isnan(v) and not math.isinf(v) and abs(v) <= L.COORD)


def _breaks_only(text: Optional[str]) -> bool:
    return text is not None and text.strip(" \n") == ""


def valid_comp(raw: Any, paras: list[dict], frames: int) -> Optional[dict]:
    """The composition as stored, or None when it isn't one of this text."""
    if not isinstance(raw, dict) or not isinstance(raw.get("lines"), list):
        return None
    lines = raw["lines"]
    if len(lines) > L.MAX_LINES or (lines and not paras):
        return None
    texts = [para_text(p) for p in paras]
    lens = [len16(t) for t in texts]
    out: list[list] = []
    pf, pp, pe = 0, -1, 0
    for ln in lines:
        if not isinstance(ln, list) or len(ln) != 8:
            return None
        f, p, s, e, x, b, w, a = ln
        if not all(_is_int(v) for v in (f, p, s, e, a)) or not all(_is_num(v) for v in (x, b, w)):
            return None
        if not (pf <= f < frames) or a not in L.LINE_ALIGNS or not (0 <= p < len(paras)):
            return None
        if p == pp:
            if s < pe or not _breaks_only(slice16(texts[p], pe, s)):
                return None
        elif p == pp + 1:
            if pp >= 0 and not _breaks_only(slice16(texts[pp], pe, lens[pp])):
                return None
            if s != 0:
                return None
        else:
            return None
        if not (s <= e <= lens[p]) or slice16(texts[p], s, e) is None:
            return None
        out.append([f, p, s, e, num(x, -L.COORD, L.COORD, 0), num(b, -L.COORD, L.COORD, 0),
                    num(w, 0, L.COORD, 0), a])
        pf, pp, pe = f, p, e
    comp: dict = {"lines": out}
    caps = _caps(raw.get("caps"), out, texts)
    if caps is None:
        return None
    if caps:
        comp["caps"] = caps
    return comp


def _caps(raw: Any, lines: list[list], texts: list[str]) -> Optional[list]:
    """A composition's drop caps, `[para, length, x, baseline, size]`: each the
    start of a paragraph's first line, in paragraph order, at most
    `DROPCAP_CHARS` characters (counted whole). None: not drop caps of this text."""
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > len(lines):
        return None
    first = {}
    for ln in lines:
        first.setdefault(ln[1], ln)
    out, last = [], -1
    for cap in raw:
        if not isinstance(cap, list) or len(cap) != 5:
            return None
        p, n16, x, b, size = cap
        if not (_is_int(p) and _is_int(n16)) or not all(_is_num(v) for v in (x, b, size)):
            return None
        line = first.get(p)
        if line is None or p <= last or line[2] != 0 or not (1 <= n16 <= line[3]):
            return None
        head = slice16(texts[p], 0, n16)
        if not head or len(head) > L.DROPCAP_CHARS or size <= 0:
            return None
        out.append([p, n16, num(x, -L.COORD, L.COORD, 0), num(b, -L.COORD, L.COORD, 0), num(size, 1, L.COORD, 1)])
        last = p
    return out


def overset(thread: dict) -> bool:
    """Whether some of a thread's text has no line (no frame left to hold it)."""
    paras = thread.get("paras") or []
    lines = (thread.get("comp") or {}).get("lines") or []
    if not paras:
        return False
    if not lines:
        return any(para_text(p) for p in paras)
    last = lines[-1]
    if last[1] < len(paras) - 1:
        return True
    text = para_text(paras[last[1]])
    return not _breaks_only(slice16(text, last[3], len16(text)))


# ── items ────────────────────────────────────────────────────────────────────

def _geometry(raw: dict) -> dict:
    return {
        "x": num(raw.get("x"), -L.COORD, L.COORD, 0),
        "y": num(raw.get("y"), -L.COORD, L.COORD, 0),
        "w": num(raw.get("w"), 0, L.COORD, 0),
        "h": num(raw.get("h"), 0, L.COORD, 0),
        "rot": num(raw.get("rot"), -180, 180, 0),
        "opacity": _int(raw.get("opacity"), 0, 100, 100),
        "locked": bool(raw.get("locked")),
        "hidden": bool(raw.get("hidden")),
        "name": _str(raw.get("name"), L.MAX_NAME),
    }


def _item(raw: Any, pages: set[str], bank: Mapping[str, dict], identity=None) -> dict:
    if not isinstance(raw, dict) or raw.get("kind") not in L.KINDS:
        raise DocError("Something on a page isn't a kind of frame a story can have.")
    kind = raw["kind"]
    page = raw.get("page")
    if page not in pages:
        raise DocError("A frame sits on a page that isn't in the story. Reload the Studio and try again.")
    out = {"id": _id(raw.get("id"), "frame"), "kind": kind, "page": page, **_geometry(raw)}
    from .identity import ref
    for key in ("fill_swatch", "stroke_swatch"):
        swatch = ref(raw.get(key), (identity or {}).get("swatches", []), "swatch")
        if swatch:
            out[key] = swatch
    if kind == "text":
        out.update(cols=_int(raw.get("cols"), 1, 12, 1), gutter=num(raw.get("gutter"), 0, L.GUTTER_MAX, 12),
                   inset=num(raw.get("inset"), 0, L.GUTTER_MAX, 0), valign=_choice(raw.get("valign"), L.VALIGNS),
                   fill=_colour(raw.get("fill"), None), stroke=_stroke(raw.get("stroke")))
    elif kind == "image":
        out.update(asset_id=_asset_id(raw.get("asset_id")), fit=_choice(raw.get("fit"), L.FITS),
                   fx=num(raw.get("fx"), 0, 100, 50), fy=num(raw.get("fy"), 0, 100, 50),
                   zoom=_int(raw.get("zoom"), L.ZOOM_MIN, L.ZOOM_MAX, 100),
                   fill=_colour(raw.get("fill"), None), stroke=_stroke(raw.get("stroke")),
                   radius=num(raw.get("radius"), 0, L.RADIUS_MAX, 0), caption=_str(raw.get("caption"), L.MAX_CAPTION))
        link = raw.get("link")  # frames showing one picture across a spread (client model/crops.ts); kept only when set
        if isinstance(link, str) and _ID.match(link):
            out["link"] = link
        shape = _shape(raw.get("shape"))
        if shape:
            out["shape"] = shape
        if raw.get("cutout") is True and link:  # the subject in front: a linked frame showing the cut-out
            out["cutout"] = True
    elif kind in ("rect", "ellipse"):
        out.update(fill=_colour(raw.get("fill"), None), stroke=_stroke(raw.get("stroke")))
        if kind == "rect":
            out["radius"] = num(raw.get("radius"), 0, L.RADIUS_MAX, 0)
    elif kind == "graphic":  # built in (graphics.py) or the curated bank's (bank.py); one-colour ones take a colour
        src = raw.get("src")
        g = graphics.by_sha(src) or (bank.get(src) if isinstance(src, str) else None)
        if g is None:
            raise DocError("A graphic on a page isn't one the Studio has. Reload the Studio and try again.")
        out.update(src=g["sha"], color=_colour(raw.get("color"), "#1a1a1a") if g.get("mono") else None,
                   fit=_choice(raw.get("fit"), L.GRAPHIC_FITS, g.get("fit") if g.get("fit") in L.GRAPHIC_FITS else None),
                   tile=num(raw.get("tile"), L.TILE_MIN, L.TILE_MAX, L.TILE_DEFAULT))
    else:  # a line, from its box's top-left corner to its bottom-right (or, flipped, bottom-left to top-right)
        out.update(stroke=_stroke(raw.get("stroke"), {"c": "#1a1a1a", "w": 1.0}), flip=bool(raw.get("flip")))
    wrap = raw.get("wrap")
    if kind != "text" and kind != "line" and isinstance(wrap, dict) and wrap.get("m") in L.WRAP_MODES:
        # Text keeps away from this frame's box, or (a picture with a cut-out shape) from its subject.
        mode = wrap["m"] if kind == "image" and "shape" in out else "box"
        out["wrap"] = {"m": mode, "o": num(wrap.get("o"), 0, L.WRAP_OFFSET_MAX, 0)}
    return out


def _shape(raw: Any) -> Optional[dict]:
    """A picture's cut-out subject, row by row (client compose/wrap.ts), or None."""
    if not isinstance(raw, dict) or not isinstance(raw.get("rows"), list):
        return None
    rows = raw["rows"]
    if not 1 <= len(rows) <= L.WRAP_ROWS or not _is_num(raw.get("ar")):
        return None
    out = []
    for row in rows:
        if not isinstance(row, list) or len(row) != 2 or not all(_is_num(v) for v in row):
            return None
        out.append([num(row[0], 0, 1, 0, 3), num(row[1], 0, 1, 0, 3)])
    return {"ar": num(raw["ar"], 0.05, 20, 1, 4), "rows": out}


def _thread(raw: Any, text_frames: set[str], used: set[str], budget: list[int], identity=None) -> dict:
    if not isinstance(raw, dict):
        raise DocError("A story's text is damaged. Reload the Studio and try again.")
    frames = raw.get("frames") if isinstance(raw.get("frames"), list) else []
    if not frames:
        raise DocError("Text in this story has no frame to sit in.")
    for f in frames:
        if f not in text_frames:
            raise DocError("Text flows into something that isn't a text frame.")
        if f in used:
            raise DocError("A text frame holds two stories' text. Unthread one of them.")
        used.add(f)
    raw_paras = raw.get("paras") if isinstance(raw.get("paras"), list) else []
    if len(raw_paras) > L.MAX_PARAS:
        raise DocError("A text has too many paragraphs. Split it into two.")
    mine = [L.MAX_THREAD_CHARS]
    paras = [_para(p, mine, identity) for p in raw_paras]
    budget[0] -= L.MAX_THREAD_CHARS - mine[0]
    if mine[0] < 0:
        raise DocError("A text frame's story is too long. Split it into two.")
    out = {"id": _id(raw.get("id"), "text"), "frames": list(frames), "paras": paras}
    comp = valid_comp(raw.get("comp"), paras, len(frames))
    if comp is not None:
        out["comp"] = comp
    return out


# ── the document ─────────────────────────────────────────────────────────────

def _sections(raw: Any, page_order: list[str]) -> list[dict]:
    """The issue's stories (the issue board): each starts at a page and runs to
    the next one's first page. One per page, in page order; a story whose page
    is gone, a bad or repeated id, or more than `MAX_SECTIONS` are dropped
    rather than refused (they only label pages)."""
    at = {pid: k for k, pid in enumerate(page_order)}
    kept: dict[str, dict] = {}
    ids: set[str] = set()
    for item in raw[:L.MAX_SECTIONS * 2] if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        sid, page = item.get("id"), item.get("page")
        # The page is checked to be a string first: a list or object can't be looked up.
        if not (isinstance(sid, str) and _ID.match(sid)) or sid in ids or not isinstance(page, str) or page not in at or page in kept:
            continue
        ids.add(sid)
        kept[page] = {"id": sid, "page": page, "name": _str(item.get("name"), L.MAX_SECTION_NAME)}
    return sorted(kept.values(), key=lambda sec: at[sec["page"]])[:L.MAX_SECTIONS]


def _unique(ids: Iterable[str], what: str) -> None:
    seen: set[str] = set()
    for i in ids:
        if i in seen:
            raise DocError(f"Two {what} in this story share a name. Reload the Studio and try again.")
        seen.add(i)


_FONT_KEY = re.compile(r'"font":"(u-[0-9a-f]{16})"')
FACE_KEYS = ("family", "name", "weight", "italic", "sha", "bytes", "upm", "asc", "desc", "cap", "x", "features")


def normalize_doc(raw: Any, bank: Optional[Mapping[str, dict]] = None,
                  faces_map: Optional[Mapping[str, list]] = None) -> dict:
    """The storable form of a paged story's document. Raises `DocError` for
    anything the owner has to fix. `bank`: the curated bank's graphics the
    document names (`bank.doc_graphics`), besides the built-in ones.
    `faces_map`: the site's own fonts it names (`custom_fonts.doc_faces`); a
    font the site doesn't have is set in the default face. The faces the
    document uses are stored with it (`faces`), so its pages set them."""
    if faces_map is None and faces.checking_faces() is not None:
        return _normalize_doc(raw, bank)  # inside another check (a parent layout): its fonts
    with faces.checking(faces_map):
        out = _normalize_doc(raw, bank)
        used = set(_FONT_KEY.findall(json.dumps(out, separators=(",", ":"))))
        own = sorted((f for key in used for f in (faces_map or {}).get(key) or []),
                     key=lambda f: (f["family"], int(f["weight"]), bool(f["italic"]), f["sha"]))
    if own:
        out["faces"] = [{k: f.get(k) for k in FACE_KEYS} for f in own]
        if len(json.dumps(out, separators=(",", ":"))) > L.MAX_DOC_BYTES:
            raise DocError("This story is too big to save. Split it into two.")
    return out


def _normalize_doc(raw: Any, bank: Optional[Mapping[str, dict]] = None) -> dict:
    if not isinstance(raw, dict):
        raise DocError("A paged story is a document of pages.")
    from .identity import normalize_identity, ref
    identity = normalize_identity(raw["identity"], bank) if "identity" in raw else None
    size = raw.get("size") if isinstance(raw.get("size"), dict) else {}
    w = num(size.get("w"), L.PAGE_MIN, L.PAGE_MAX, 612)
    h = num(size.get("h"), L.PAGE_MIN, L.PAGE_MAX, 792)
    m = raw.get("margins") if isinstance(raw.get("margins"), dict) else {}
    cols = raw.get("cols") if isinstance(raw.get("cols"), dict) else {}
    base = raw.get("baseline") if isinstance(raw.get("baseline"), dict) else {}
    grid = raw.get("grid") if isinstance(raw.get("grid"), dict) else {}

    raw_pages = raw.get("pages") if isinstance(raw.get("pages"), list) else []
    if not raw_pages:
        raise DocError("A paged story has at least one page.")
    if len(raw_pages) > L.MAX_PAGES:
        raise DocError(f"A story holds at most {L.MAX_PAGES} pages.")
    pages = [{"id": _id(p.get("id") if isinstance(p, dict) else None, "page")} for p in raw_pages]
    for page, source in zip(pages, raw_pages):
        parent = ref(source.get("parent"), (identity or {}).get("parents", []), "parent layout")
        if parent:
            page["parent"] = parent
        if source.get("hide_furniture"):
            page["hide_furniture"] = True
        if "header" in source:
            page["header"] = _str(source["header"], 120)
    _unique((p["id"] for p in pages), "pages")
    page_ids = {p["id"] for p in pages}

    raw_items = raw.get("items") if isinstance(raw.get("items"), list) else []
    if len(raw_items) > L.MAX_ITEMS:
        raise DocError(f"A story holds at most {L.MAX_ITEMS} frames and shapes.")
    items = [_item(i, page_ids, bank or {}, identity) for i in raw_items]
    _unique((i["id"] for i in items), "frames")
    per_page: dict[str, int] = {}
    for i in items:
        per_page[i["page"]] = per_page.get(i["page"], 0) + 1
        if per_page[i["page"]] > L.MAX_ITEMS_PER_PAGE:
            raise DocError(f"A page holds at most {L.MAX_ITEMS_PER_PAGE} frames and shapes.")

    raw_threads = raw.get("threads") if isinstance(raw.get("threads"), list) else []
    if len(raw_threads) > L.MAX_THREADS:
        raise DocError(f"A story holds at most {L.MAX_THREADS} separate texts.")
    text_frames = {i["id"] for i in items if i["kind"] == "text"}
    used: set[str] = set()
    budget = [L.MAX_DOC_CHARS]
    threads = [_thread(t, text_frames, used, budget, identity) for t in raw_threads]
    if budget[0] < 0:
        raise DocError("This story holds too much text. Split it into two.")
    _unique((t["id"] for t in threads), "texts")

    raw_guides = raw.get("guides") if isinstance(raw.get("guides"), list) else []
    guides = []
    for g in raw_guides[:L.MAX_GUIDES]:
        if not isinstance(g, dict) or g.get("page") not in page_ids:
            continue
        guides.append({"id": _id(g.get("id"), "guide"), "page": g["page"], "axis": _choice(g.get("axis"), ("v", "h")),
                       "at": num(g.get("at"), -L.COORD, L.COORD, 0)})
    _unique((g["id"] for g in guides), "guides")

    sections = _sections(raw.get("sections"), [p["id"] for p in pages])

    paywall = raw.get("paywall_page")
    out = {
        "v": 1,
        "size": {"w": w, "h": h},
        "facing": bool(raw.get("facing", True)),
        "margins": {k: num(m.get(k), 0, min(w, h) / 2, 36) for k in ("t", "b", "i", "o")},
        "cols": {"n": _int(cols.get("n"), 1, 24, 1), "g": num(cols.get("g"), 0, L.GUTTER_MAX, 12)},
        "baseline": {"start": num(base.get("start"), 0, h, 36), "step": num(base.get("step"), 1, 144, 12)},
        "grid": {"step": num(grid.get("step"), 1, 288, 12)},
        "bleed": num(raw.get("bleed"), 0, 72, 9),
        "units": _choice(raw.get("units"), L.UNITS, "in"),
        "paper": _colour(raw.get("paper"), "#ffffff"),
        "pages": pages,
        "guides": guides,
        "items": items,
        "threads": threads,
        "paywall_page": (_int(paywall, 2, len(pages), 2) if paywall is not None and len(pages) > 1 else None),
    }
    if sections:  # left out when there are none, so stories without any are stored as they always were
        out["sections"] = sections
    if identity is not None:
        out["identity"] = identity
        # Recurring frames count too: a small stored parent must not bypass
        # the normal document/rendering limits through repetition.
        inherited_items = inherited_threads = inherited_chars = 0
        def line_cost(t):
            return len(t["comp"]["lines"]) if t.get("comp") is not None else len(t["paras"])

        lines = sum(line_cost(t) for t in threads)
        for page in pages:
            parent = next((p for p in identity["parents"] if p["id"] == page.get("parent")), None)
            if parent:
                inherited_items += len(parent["items"])
                inherited_threads += len(parent["threads"])
                inherited_chars += sum(len16(para_text(p)) for t in parent["threads"] for p in t["paras"])
                lines += sum(line_cost(t) for t in parent["threads"])
                if per_page.get(page["id"], 0) + len(parent["items"]) > L.MAX_ITEMS_PER_PAGE:
                    raise DocError("This page and its parent hold too many frames.")
        if len(items) + inherited_items > L.MAX_ITEMS or len(threads) + inherited_threads > L.MAX_THREADS:
            raise DocError("This story and its parents hold too many frames or separate texts.")
        if L.MAX_DOC_CHARS - budget[0] + inherited_chars > L.MAX_DOC_CHARS:
            raise DocError("This story and its parents hold too much text.")
        if lines > L.MAX_LINES:
            raise DocError("This story and its parents hold too many composed lines.")
    if len(json.dumps(out, separators=(",", ":"))) > L.MAX_DOC_BYTES:
        raise DocError("This story is too big to save. Split it into two.")
    return out


def starter_doc() -> dict:
    """A new paged story: two Letter pages, facing, three columns, and an
    empty text frame threaded from the first page to the second."""
    w, h, m = 612, 792, 54
    frame = {"kind": "text", "x": m, "y": m, "w": w - 2 * m, "h": h - 2 * m, "cols": 3, "gutter": 12}
    return normalize_doc({
        "size": {"w": w, "h": h}, "facing": True, "margins": {"t": m, "b": m, "i": m, "o": m},
        "cols": {"n": 3, "g": 12}, "baseline": {"start": m, "step": 12},
        "pages": [{"id": "p1"}, {"id": "p2"}],
        "items": [{**frame, "id": "t1", "page": "p1"}, {**frame, "id": "t2", "page": "p2"}],
        "threads": [{"id": "s1", "frames": ["t1", "t2"], "paras": [{"runs": [{"t": ""}]}]}],
    })


# ── reading a document ───────────────────────────────────────────────────────

def doc_asset_ids(doc: Optional[dict]) -> set[str]:
    return {i["asset_id"] for i in (doc or {}).get("items") or [] if i.get("kind") == "image" and i.get("asset_id")}


def spreads(doc: dict) -> list[list[int]]:
    """The pages (indexes) on each spread: facing pages open on a right-hand
    page alone, then go in pairs; otherwise each page is its own."""
    n = len(doc.get("pages") or [])
    if not doc.get("facing"):
        return [[i] for i in range(n)]
    out = [[0]] if n else []
    i = 1
    while i < n:
        out.append([i, i + 1] if i + 1 < n else [i])
        i += 2
    return out


def paywall_from(post: dict) -> Optional[int]:
    """A paid paged story's first page for subscribers (never the first), or
    None when every page is free."""
    doc = (post.get("content") or {}).get("doc") or {}
    if post.get("access") != "paid" or len(doc.get("pages") or []) < 2:
        return None
    return int(doc.get("paywall_page") or 2)


def flow_frame(doc: dict, thread: dict, locked_from: Optional[int] = None) -> int:
    """Which of a thread's frames holds its words while it has no composition:
    the first, or, when some of its frames are on subscribers' pages, the
    first of those, so nothing paid is ever printed on a free page."""
    if locked_from:
        page_index = {p["id"]: i for i, p in enumerate(doc.get("pages") or [])}
        pages = {i["id"]: i["page"] for i in doc.get("items") or []}
        for k, f in enumerate(thread["frames"]):
            if page_index.get(pages.get(f), -1) + 1 >= locked_from:
                return k
    return 0


def page_side(doc: dict, index: int) -> str:
    """"left" or "right" for a facing page ("right" when pages don't face)."""
    return "left" if doc.get("facing") and index % 2 == 1 else "right"
