"""Reusable visual identities; raw references stay separate from resolved type.

The saved magazine identity is a template. A story owns a snapshot, so changing
the template never changes a published issue without an explicit story update.
"""
import json
from copy import deepcopy

MAX_STYLES = 32
MAX_SWATCHES = 24
MAX_PARENTS = 8
MAX_PARENT_ITEMS = 80
MAX_IDENTITY_BYTES = 500_000


def ref(value, rows, what):
    from .schema import DocError
    if value is None:
        return None
    if isinstance(value, str) and any(row["id"] == value for row in rows):
        return value
    raise DocError(f"This story names a {what} that isn't in its magazine identity.")


def _rows(raw, key, limit):
    from .schema import DocError
    rows = raw.get(key, [])
    if not isinstance(rows, list) or len(rows) > limit or any(not isinstance(r, dict) for r in rows):
        raise DocError(f"A magazine identity holds at most {limit} {key}.")
    return rows


def normalize_identity(raw, bank=None):
    from .schema import DocError
    try:
        return _normalize_identity(raw, bank)
    except (TypeError, OverflowError) as exc:
        raise DocError("This magazine identity contains malformed design data.") from exc


def _normalize_identity(raw, bank=None):
    from .schema import DocError, _colour, _id, _str, _unique, char_attrs, normalize_doc, num, para_attrs
    if not isinstance(raw, dict) or raw.get("v", 1) != 1:
        raise DocError("This magazine identity isn't a supported design.")
    if len(json.dumps(raw, separators=(",", ":"))) > MAX_IDENTITY_BYTES:
        raise DocError("This magazine identity is too big. Use fewer parent frames or less text.")

    def label(row):
        name = _str(row.get("name"), 80)
        if not name:
            raise DocError("Give each identity, style, swatch and parent a name.")
        return {"id": _id(row.get("id"), "design"), "name": name}

    swatches = [{**label(s), "color": _colour(s.get("color"), "#1a1a1a")}
                for s in _rows(raw, "swatches", MAX_SWATCHES)]

    def character(value, partial=False):
        value = value if isinstance(value, dict) else {}
        clean = char_attrs(value)
        if partial:
            clean = {k: v for k, v in clean.items() if k in value}
        swatch = ref(value.get("swatch"), swatches, "swatch")
        if swatch:
            clean["swatch"] = swatch
        return clean

    paragraphs = [{**label(s), "char": character(s.get("char")), "para": para_attrs(s.get("para") if isinstance(s.get("para"), dict) else {})}
                  for s in _rows(raw, "paragraphs", MAX_STYLES)]
    characters = [{**label(s), "char": character(s.get("char"), True)} for s in _rows(raw, "characters", MAX_STYLES)]
    for rows in (swatches, paragraphs, characters):
        _unique((r["id"] for r in rows), "designs")
        if len({r["name"].lower() for r in rows}) != len(rows):
            raise DocError("Use distinct names for the styles, swatches or parents in each list.")
    name = _str(raw.get("name"), 80)
    if not name:
        raise DocError("Give the magazine identity a name.")
    f = raw.get("furniture") if isinstance(raw.get("furniture"), dict) else {}
    out = {"v": 1, "name": name, "paragraphs": paragraphs, "characters": characters, "swatches": swatches, "parents": [],
           "furniture": {"numbers": bool(f.get("numbers")), "header": _str(f.get("header"), 120),
                         "start": int(num(f.get("start"), 1, 9999, 1, 0)), "skip_first": bool(f.get("skip_first", True)),
                         "inset": num(f.get("inset"), 0, 288, 24), "char": character(f.get("char"))}}
    parents = []
    for parent in _rows(raw, "parents", MAX_PARENTS):
        items = parent.get("items", [])
        if not isinstance(items, list) or len(items) > MAX_PARENT_ITEMS:
            raise DocError("A parent holds up to 80 frames.")
        # Parent snapshots have no nested parents, guides, paywall or local photos.
        portable = [{**i, "page": "p1", **({"asset_id": None, "caption": ""} if i.get("kind") == "image" else {})}
                    for i in items if isinstance(i, dict)]
        if len(portable) != len(items):
            raise DocError("A parent contains malformed frames.")
        doc = normalize_doc({"size": parent.get("size"), "pages": [{"id": "p1"}], "items": portable,
                             "threads": parent.get("threads", []), "identity": out}, bank)
        parents.append({**label(parent), "size": doc["size"], "items": doc["items"], "threads": doc["threads"]})
    _unique((p["id"] for p in parents), "parents")
    if len({p["name"].lower() for p in parents}) != len(parents):
        raise DocError("Give each parent a distinct name.")
    out["parents"] = parents
    if len(json.dumps(out, separators=(",", ":"))) > MAX_IDENTITY_BYTES:
        raise DocError("This magazine identity is too big. Use fewer parent frames or less text.")
    return out


def resolve_char(raw, base=None, identity=None):
    from .schema import char_attrs
    identity = identity or {}
    named = next((s["char"] for s in identity.get("characters", []) if s["id"] == raw.get("style")), {})
    merged = {**(base or {})}
    for layer in (named, raw):
        if "color" in layer and "swatch" not in layer:
            merged.pop("swatch", None)
        merged.update(layer)
    swatch = next((s for s in identity.get("swatches", []) if s["id"] == merged.get("swatch")), None)
    if swatch:
        merged["color"] = swatch["color"]
    return char_attrs(merged)


def resolve_paras(paras, identity=None):
    from .schema import para_attrs
    if not identity:
        return paras
    out = []
    for p in paras:
        named = next((s for s in identity["paragraphs"] if s["id"] == p.get("style")), {})
        out.append({**para_attrs({**named.get("para", {}), **p}),
                    "runs": [{"t": r["t"], **resolve_char(r, named.get("char"), identity)} for r in p["runs"]]})
    return out


def resolved_threads(doc):
    return [{**t, "paras": resolve_paras(t["paras"], doc.get("identity"))} for t in doc.get("threads", [])]


def resolve_item(item, identity=None):
    if not identity:
        return item
    out = {**item}
    for key in ("fill", "stroke"):
        swatch = next((s for s in identity["swatches"] if s["id"] == item.get(key + "_swatch")), None)
        if swatch and key == "fill" and (item["kind"] != "graphic" or item.get("color") is not None):
            out["color" if item["kind"] == "graphic" else "fill"] = swatch["color"]
        elif swatch and item.get("stroke"):
            out["stroke"] = {**item["stroke"], "c": swatch["color"]}
    return out


def parent_doc(doc, parent):
    identity = {**doc["identity"], "parents": [], "furniture": {**doc["identity"]["furniture"], "numbers": False, "header": ""}}
    return {**doc, "size": parent["size"], "pages": [{"id": "p1"}], "items": parent["items"],
            "threads": parent["threads"], "identity": identity, "paywall_page": None}


def portable_identity(raw, bank=None):
    # Compositions belong to the source font context; the Studio composes the
    # shared snapshot on import. Paragraph/character references remain live.
    out = deepcopy(normalize_identity(raw, bank))
    for p in out["parents"]:
        for t in p["threads"]:
            t.pop("comp", None)
    return out
