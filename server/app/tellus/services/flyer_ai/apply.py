"""The canonical op applier.

**This is inverted from Cappe.** There, `merlinOps.ts` applies and
`merlin/apply.py` is a mirror kept in sync by a shared fixture — Cappe has one
client, so client-side apply is affordable. Tell-Us ships two editors (the web
Konva designer and the SwiftUI one), so applying on the client would mean the
same op semantics written twice more. Here the server applies and the assist
response carries the resulting document; neither client has an applier.

The trade that buys: a local edit made WHILE a turn is in flight has nothing to
rebase onto, so the clients lock the document for the duration of a turn.

Everything here is pure — no I/O, and the caller's document is never mutated.
"""
import uuid
from copy import deepcopy
from typing import Any, Optional

_LABELS = {
    "text": "text", "shape": "shape", "sticker": "sticker", "image": "image", "qr": "claim QR",
}

_SKELETONS: dict[str, dict[str, Any]] = {
    "text": {
        "fontFamily": "Helvetica Neue", "fontSize": 48, "fontStyle": "bold", "fill": "ink",
        "align": "center", "width": 600, "lineHeight": 1.2, "letterSpacing": 0, "text": "",
    },
    "shape": {"shape": "rect", "width": 200, "height": 200, "fill": "brand", "cornerRadius": 0},
    "sticker": {"width": 200, "height": 200},
    # Literals, not tokens — contrast on a QR is a scanning requirement, and
    # `ink` on `paper` inverts under a dark palette (see catalog.MIN_QR_CONTRAST).
    "qr": {"size": 400, "fg": "#17140f", "bg": "#ffffff"},
}


def _label(layer: Optional[dict[str, Any]]) -> str:
    if not layer:
        return "layer"
    kind = layer.get("type")
    if kind == "text":
        text = str(layer.get("text") or "").strip()
        return f'"{text[:24]}"' if text else "text"
    return _LABELS.get(kind, "layer")


def _index_of(design: dict[str, Any], layer_id: str) -> int:
    for i, layer in enumerate(design.get("layers", [])):
        if layer.get("id") == layer_id:
            return i
    return -1


def apply_ops(
    design: dict[str, Any],
    ops: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """-> (next_design, results). `results` is one `{ok, summary}` per op, in
    order, for the transcript chips.

    Ops arrive already validated, but a target can still be missing — an earlier
    op in the same turn may have removed it. That degrades to `ok: False`; it
    never raises.
    """
    doc = deepcopy(design)
    results: list[dict[str, Any]] = []
    # Model-assigned "new-1" -> the real uuid the layer got, for THIS turn only.
    # Two turns could both say "new-1", so the temp name is never persisted.
    temp_ids: dict[str, str] = {}

    def resolve(raw_id: Any) -> str:
        key = raw_id if isinstance(raw_id, str) else ""
        return temp_ids.get(key, key)

    for op in ops:
        name = op.get("op")
        try:
            ok, summary = _apply_one(doc, op, name, resolve, temp_ids)
        except Exception as exc:  # noqa: BLE001 — a bad op costs its own result, not the turn
            ok, summary = False, f"Skipped — could not be applied ({type(exc).__name__})"
        results.append({"ok": ok, "summary": summary})
    return doc, results


def _apply_one(doc, op, name, resolve, temp_ids) -> tuple[bool, str]:
    layers: list[dict[str, Any]] = doc.setdefault("layers", [])

    if name == "set_document":
        doc.clear()
        doc.update(deepcopy(op["design"]))
        return True, "Rebuilt the flyer"

    if name == "set_palette_values":
        doc["palette"] = dict(op["palette"])
        return True, "Recoloured the flyer"

    if name == "set_background":
        doc["background"] = {"kind": "color", "color": op["value"]}
        return True, "Changed the background"

    if name == "add_layer":
        kind = op["kind"]
        layer: dict[str, Any] = {
            "id": str(uuid.uuid4()), "type": kind, "rotation": 0, "opacity": 1,
            **_SKELETONS.get(kind, {}),
        }
        for key, value in op.items():
            if key in ("op", "kind", "id"):
                continue
            layer[key] = value
        layers.append(layer)
        temp = op.get("id")
        if isinstance(temp, str) and temp:
            temp_ids[temp] = layer["id"]
        return True, f"Added {_label(layer)}"

    idx = _index_of(doc, resolve(op.get("layer")))
    if idx < 0:
        return False, "Skipped — that layer no longer exists"
    layer = layers[idx]

    if name == "set_layer":
        layer[op["path"]] = op["value"]
        return True, f"Edited {_label(layer)} — {op['path']}"

    if name == "move_layer":
        layer["x"], layer["y"] = op["x"], op["y"]
        return True, f"Moved {_label(layer)}"

    if name == "resize_layer":
        if layer.get("type") == "qr":
            layer["size"] = op.get("width") or op.get("height")
        else:
            if op.get("width") is not None:
                layer["width"] = op["width"]
            if op.get("height") is not None:
                layer["height"] = op["height"]
        return True, f"Resized {_label(layer)}"

    if name == "remove_layer":
        layers.pop(idx)
        return True, f"Removed {_label(layer)}"

    if name == "reorder_layer":
        to = max(0, min(int(op["to"]), len(layers) - 1))
        layers.insert(to, layers.pop(idx))
        return True, f"Reordered {_label(layer)}"

    return False, f"Skipped — unknown change '{name}'"
