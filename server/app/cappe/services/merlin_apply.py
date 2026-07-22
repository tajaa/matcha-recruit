"""Server-side mirror of the client's Merlin op applier.

`client/src/cappe/pages/site/PageEditor/merlinOps.ts:applyMerlinOps` is the
canonical applier — the client is still the one that mutates real editor state,
and this module never writes a page. It exists so the AGENT LOOP
(`services/merlin_agent.py`) can fold ops onto a throwaway copy of the request
snapshot, render THAT, and screenshot it — i.e. so the model can look at what
its own edit did before committing to it.

Keep the two in sync. `tests/cappe/test_merlin_apply.py` runs the shared fixture
file (`tests/cappe/fixtures/merlin_apply_cases.json`) through this applier and
`merlinOps.test.ts` runs the same file through the TS one, so a divergence in
what an op *does* fails a test rather than silently making the screenshot lie
about the page.

Two deliberate divergences, both because the data lives client-side only:

- **`add_block` has no schema defaults.** The client builds a new block from
  `BLOCK_SCHEMAS[type].make()` (placeholder copy per type, in `blockSchemas.ts`);
  the server has no such registry, so a block added here carries only the op's
  own `content` over an empty kind-derived skeleton. A section the model adds
  without content therefore renders emptier in the screenshot than it will in
  the editor. Self-correcting (the model sees the empty section) and mostly
  moot in practice — `apply_section_preset` expands to an add_block that
  carries full content.
- **`set_theme key="preset"` can't repaint.** The full preset config (palette,
  fonts, radius) lives in `cappeThemes.ts`; `theme_presets.py` mirrors only
  `{id, name, blurb, premium, mode}`. So a preset swap applies `preset` + its
  `mode` and leaves the palette alone. Mode is the axis that actually decides
  whether a design reads, and preset swaps are gated behind explicit theme
  intent, so this rarely bites.

Everything here is pure: no I/O, no DB, no mutation of the caller's lists.
"""
import copy
import uuid
from typing import Any, Optional

from .merlin_catalog import (
    BLOCK_FIELDS,
    BLOCK_LABELS,
    CANVAS_MAX_ELEMENTS,
    LIST_KINDS,
)
from .theme_presets import PRESETS_BY_ID


class ApplyResult:
    """Ops folded onto a snapshot: the next blocks/theme, a per-op chip, and the
    temp-id map an `add_block(id=...)` registered for later ops in the turn."""

    __slots__ = ("blocks", "theme", "results", "temp_id_map")

    def __init__(
        self,
        blocks: list[dict[str, Any]],
        theme: dict[str, Any],
        results: list[dict[str, Any]],
        temp_id_map: dict[str, str],
    ):
        self.blocks = blocks
        self.theme = theme
        self.results = results
        self.temp_id_map = temp_id_map


def _label(btype: Any) -> str:
    return BLOCK_LABELS.get(btype, str(btype or "block"))


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _deep_set(target: Any, parts: list[str], value: Any) -> tuple[bool, Any]:
    """Immutable deep-set over dicts and list indices, mirroring the client's
    `deepSet`. REFUSES on a container mismatch instead of coercing: a named key
    into a list once replaced a whole list of cards with a single object while
    the chat reported success."""
    if not parts:
        return True, value
    key, rest = parts[0], parts[1:]
    idx = int(key) if key.isdigit() else None

    if idx is not None:
        if not isinstance(target, list):
            return False, target
        if idx > len(target):  # == len is an append
            return False, target
        inner_ok, inner = _deep_set(target[idx] if idx < len(target) else None, rest, value)
        if not inner_ok:
            return False, target
        arr = list(target)
        if idx == len(arr):
            arr.append(inner)
        else:
            arr[idx] = inner
        return True, arr

    if isinstance(target, list):
        return False, target
    base = dict(target) if isinstance(target, dict) else {}
    inner_ok, inner = _deep_set(base.get(key), rest, value)
    if not inner_ok:
        return False, target
    base[key] = inner
    return True, base


def _skeleton(btype: str) -> dict[str, Any]:
    """An empty block of `btype`. See the module docstring: the client's real
    per-type placeholder copy isn't available server-side, so fields start
    empty and the op's own `content` fills what it names."""
    out: dict[str, Any] = {"type": btype}
    for name, kind in BLOCK_FIELDS.get(btype, {}).items():
        out[name] = [] if kind in LIST_KINDS else ("" if kind != "bool" else False)
    if btype == "canvas":
        out["elements"] = []
    return out


def _canvas_elements(block: dict[str, Any]) -> list[dict[str, Any]]:
    els = block.get("elements")
    return list(els) if isinstance(els, list) else []


def _next_y(elements: list[dict[str, Any]]) -> int:
    """Row below the lowest existing element — the client's `cvNextY`."""
    bottom = 0
    for el in elements:
        d = el.get("d") if isinstance(el, dict) else None
        if isinstance(d, dict):
            y, h = d.get("y"), d.get("h")
            if isinstance(y, (int, float)) and isinstance(h, (int, float)):
                bottom = max(bottom, int(y) + int(h))
    return bottom


def _apply_theme_op(
    theme: dict[str, Any], key: str, value: Any
) -> Optional[dict[str, Any]]:
    """One `set_theme`. None = refuse (unknown preset), matching the client's
    null return."""
    if key == "preset":
        preset = PRESETS_BY_ID.get(value if isinstance(value, str) else "")
        if preset is None:
            return None
        # Palette/fonts resolve client-side (see module docstring) — mode is
        # what the screenshot most needs to be right about.
        return {**theme, "preset": preset.id, "mode": preset.mode}

    if key == "colors.brand" and isinstance(value, str):
        colors = {**_as_dict(theme.get("colors")), "brand": value, "accent": value}
        return {**theme, "colors": colors}

    head, _, sub = key.partition(".")
    if sub:
        bag = _as_dict(theme.get(head))
        if value is None:
            bag.pop(sub, None)
        else:
            bag[sub] = value
        return {**theme, head: bag}

    nxt = dict(theme)
    if value is None:
        nxt.pop(head, None)
    else:
        nxt[head] = value
    return nxt


def apply_ops(
    blocks: list[dict[str, Any]],
    theme: dict[str, Any],
    ops: list[dict[str, Any]],
) -> ApplyResult:
    """Fold validated ops onto a snapshot. Pure — the caller's blocks/theme are
    never mutated. Ops are expected to have passed `merlin_ops.validate_ops`
    already; anything that still can't be resolved (an id removed by an earlier
    op in the same turn) degrades to a skipped chip, never an exception."""
    next_blocks: list[dict[str, Any]] = [copy.deepcopy(b) for b in blocks]
    next_theme: dict[str, Any] = copy.deepcopy(theme)
    results: list[dict[str, Any]] = []
    temp_id_map: dict[str, str] = {}

    def resolve(block_id: Any) -> Any:
        return temp_id_map.get(block_id, block_id)

    def index_of(block_id: Any) -> int:
        target = resolve(block_id)
        for i, b in enumerate(next_blocks):
            if b.get("id") == target:
                return i
        return -1

    def ok(summary: str) -> None:
        results.append({"ok": True, "summary": summary})

    def skip(summary: str) -> None:
        results.append({"ok": False, "summary": summary})

    for op in ops:
        kind = op.get("op")

        if kind == "set_field":
            idx = index_of(op.get("block"))
            if idx == -1:
                skip("Skipped — section no longer exists")
                continue
            block = next_blocks[idx]
            head, _, rest = str(op.get("path", "")).partition(".")
            if rest:
                changed, new_val = _deep_set(block.get(head), rest.split("."), op.get("value"))
                if not changed:
                    skip(f'Skipped — "{op.get("path")}" doesn\'t match this section\'s shape')
                    continue
            else:
                new_val = op.get("value")
            block[head] = new_val
            ok(f"Edited {_label(block.get('type'))} — {head}")

        elif kind == "set_design":
            idx = index_of(op.get("block"))
            if idx == -1:
                skip("Skipped — section no longer exists")
                continue
            block = next_blocks[idx]
            design = _as_dict(block.get("_design"))
            group_key = str(op.get("group"))
            group = _as_dict(design.get(group_key))
            value = op.get("value")
            # '' / None clears the key — the DesignInspector patch convention.
            if value is None or value == "":
                group.pop(str(op.get("key")), None)
            else:
                group[str(op.get("key"))] = value
            design[group_key] = group
            block["_design"] = design
            ok(f"{_label(block.get('type'))} — {group_key} {op.get('key')}")

        elif kind == "set_design_bulk":
            targets = {resolve(b) for b in (op.get("blocks") or [])}
            design_patch = op.get("design") or {}
            touched: list[str] = []
            changed_count = 0
            for block in next_blocks:
                if block.get("id") not in targets:
                    continue
                design = _as_dict(block.get("_design"))
                for group_key, keys in design_patch.items():
                    design[group_key] = {**_as_dict(design.get(group_key)), **_as_dict(keys)}
                    if group_key not in touched:
                        touched.append(group_key)
                block["_design"] = design
                changed_count += 1
            if changed_count:
                ok(f"Styled {changed_count} section{'' if changed_count == 1 else 's'} — {', '.join(touched)}")
            else:
                skip("Skipped — none of the targeted sections exist")

        elif kind == "add_block":
            btype = op.get("type")
            if btype not in BLOCK_FIELDS:
                skip(f"Skipped — unknown block type \"{btype}\"")
                continue
            new_block = {**_skeleton(btype), **_as_dict(op.get("content"))}
            # The model's temp id BECOMES the working-copy id when it's free.
            # The agent loop calls this once per tool call, so a fresh id would
            # be invisible to the NEXT call's `validate_ops` (which indexes the
            # working blocks) — "add a section, then fill it in" would be
            # rejected as a missing block id. `validate_ops` already refuses a
            # temp id that collides with a real block, and the working copy is
            # per-turn, so adopting it is safe.
            temp_id = op.get("id")
            existing_ids = {b.get("id") for b in next_blocks}
            if isinstance(temp_id, str) and temp_id and temp_id not in existing_ids:
                new_block["id"] = temp_id
            else:
                new_block["id"] = f"srv-{uuid.uuid4().hex[:8]}"
            design = _as_dict(op.get("design"))
            if design:
                new_block["_design"] = design
            if isinstance(temp_id, str) and temp_id:
                temp_id_map[temp_id] = new_block["id"]
            at = max(0, min(int(op.get("at") or 0), len(next_blocks)))
            next_blocks.insert(at, new_block)
            preset = op.get("preset")
            ok(f"Added {_label(btype)} ({preset} preset)" if preset else f"Added {_label(btype)}")

        elif kind == "duplicate_block":
            idx = index_of(op.get("block"))
            if idx == -1:
                skip("Skipped — section no longer exists")
                continue
            clone = copy.deepcopy(next_blocks[idx])
            clone["id"] = f"srv-{uuid.uuid4().hex[:8]}"
            at_raw = op.get("at")
            at = max(0, min(int(at_raw), len(next_blocks))) if isinstance(at_raw, int) else idx + 1
            next_blocks.insert(at, clone)
            ok(f"Duplicated {_label(clone.get('type'))}")

        elif kind == "remove_block":
            idx = index_of(op.get("block"))
            if idx == -1:
                skip("Skipped — section already removed")
                continue
            ok(f"Removed {_label(next_blocks.pop(idx).get('type'))}")

        elif kind == "move_block":
            frm = index_of(op.get("block"))
            if frm == -1:
                skip("Skipped — section no longer exists")
                continue
            to = max(0, min(int(op.get("to") or 0), len(next_blocks) - 1))
            label = _label(next_blocks[frm].get("type"))
            if to == frm:
                ok(f"{label} already in place")
                continue
            next_blocks.insert(to, next_blocks.pop(frm))
            ok(f"Moved {label}")

        elif kind == "set_theme":
            applied = _apply_theme_op(next_theme, str(op.get("key")), op.get("value"))
            if applied is None:
                skip(f'Skipped — no theme called "{op.get("value")}"')
                continue
            next_theme = applied
            ok(
                f"Switched theme to {op.get('value')}"
                if op.get("key") == "preset"
                else f"Updated {op.get('key')}"
            )

        elif kind in ("canvas_add", "canvas_update", "canvas_remove"):
            idx = index_of(op.get("block"))
            if idx == -1 or next_blocks[idx].get("type") != "canvas":
                skip("Skipped — canvas section not found")
                continue
            block = next_blocks[idx]
            els = _canvas_elements(block)

            if kind == "canvas_add":
                if len(els) >= CANVAS_MAX_ELEMENTS:
                    skip("Skipped — canvas is full")
                    continue
                src = _as_dict(op.get("element"))
                el: dict[str, Any] = {"id": uuid.uuid4().hex[:8], "kind": src.get("kind")}
                for key in ("text", "src", "alt", "href", "style"):
                    if src.get(key) is not None:
                        el[key] = src[key]
                el["d"] = src.get("d") or {"x": 1, "y": _next_y(els), "w": 8, "h": 2}
                block["elements"] = [*els, el]
                ok("Added element to canvas")

            elif kind == "canvas_update":
                found = next((e for e in els if e.get("id") == op.get("el")), None)
                if found is None:
                    skip("Skipped — element no longer exists")
                    continue
                block["elements"] = [
                    {**e, **_as_dict(op.get("patch"))} if e.get("id") == op.get("el") else e
                    for e in els
                ]
                ok("Updated canvas element")

            else:  # canvas_remove
                if not any(e.get("id") == op.get("el") for e in els):
                    skip("Skipped — element no longer exists")
                    continue
                block["elements"] = [e for e in els if e.get("id") != op.get("el")]
                ok("Removed canvas element")

        elif kind == "generate_image":
            # Resolved by the agent loop itself (it generates, then folds a
            # set_field), and out-of-band by the client on the single-shot path.
            # A defensive no-op here so it isn't chipped as "unrecognized".
            continue

        else:
            skip("Skipped — unrecognized op")

    return ApplyResult(next_blocks, next_theme, results, temp_id_map)
