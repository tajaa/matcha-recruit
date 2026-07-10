"""Turn an eCFR *structure* tree into enumerated authority items.

`government_apis/ecfr.py:_parse_structure` only *counts* subparts and sections
(it feeds a summary requirement row). The scope registry needs the items
themselves — one per subpart AND section, each with a citation and a link to
its parent subpart — so this is a separate, pure walker over the same JSON.

Pure function, no I/O: the fetch stays in `government_apis/ecfr.py`; this is the
testable core exercised by fixtures.

eCFR structure node shape (the fields we read):
    {
      "type": "part" | "subpart" | "subject_group" | "section" | "appendix" | ...,
      "identifier": "1910" | "J" | "1910.147" | ...,
      "label": "Subpart J" | "§ 1910.147",
      "label_description": "General Environmental Controls" | "The control of ...",
      "label_level": "Subpart J",
      "reserved": true,                      # optional
      "children": [ ... ]
    }
"""
from __future__ import annotations

from typing import Dict, List, Optional


def _is_reserved(node: dict) -> bool:
    if node.get("reserved") is True:
        return True
    text = " ".join(
        str(node.get(k) or "")
        for k in ("label", "label_description", "label_level", "heading")
    ).lower()
    return "[reserved]" in text or "(reserved)" in text


def _heading(node: dict) -> Optional[str]:
    return (
        node.get("label_description")
        or node.get("heading")
        or node.get("label")
        or None
    )


def _find_part(node: dict, part_num: int) -> Optional[dict]:
    """Locate the part node for ``part_num`` anywhere in the tree."""
    if node.get("type") == "part":
        identifier = str(node.get("identifier", "")).lower().lstrip("0")
        if identifier in (str(part_num), f"part {part_num}"):
            return node
    for child in node.get("children", []):
        found = _find_part(child, part_num)
        if found:
            return found
    return None


def parse_ecfr_items(structure_json: dict, title_num: int, part_num: int) -> List[dict]:
    """Emit one item dict per subpart and section under ``title/part``.

    Each item: ``{citation, heading, hierarchy, parent_citation, source_url}``.
    ``parent_citation`` links a section to its enclosing subpart (``None`` when
    the section sits directly under the part, e.g. parts with no subparts).
    Reserved nodes are skipped — a reserved section carries no obligation to
    classify. ``subject_group`` and other intermediate nodes are traversed but
    not emitted; a section's parent is always its nearest ancestor *subpart*.

    Deterministic and side-effect-free.
    """
    part_node = _find_part(structure_json, part_num) or structure_json
    items: List[dict] = []

    def section_citation(identifier: str) -> str:
        # eCFR section identifiers already include the part ("1910.147").
        ident = identifier.strip()
        if not ident.startswith(f"{part_num}."):
            # Defensive: some feeds give a bare section number.
            ident = f"{part_num}.{ident}" if "." not in ident else ident
        return f"{title_num} CFR {ident}"

    def subpart_citation(identifier: str) -> str:
        return f"{title_num} CFR {part_num} Subpart {identifier.strip()}"

    def walk(node: dict, current_subpart: Optional[dict]) -> None:
        node_type = node.get("type", "")

        if node_type == "subpart":
            if _is_reserved(node):
                return  # skip the subpart and its (reserved) contents
            ident = str(node.get("identifier", "")).strip()
            citation = subpart_citation(ident)
            items.append({
                "citation": citation,
                "heading": _heading(node),
                "hierarchy": {
                    "title": str(title_num),
                    "part": str(part_num),
                    "subpart": ident,
                },
                "parent_citation": None,  # subpart's parent is the index/part itself
                "source_url": (
                    f"https://www.ecfr.gov/current/title-{title_num}"
                    f"/part-{part_num}/subpart-{ident}"
                ),
            })
            for child in node.get("children", []):
                walk(child, node)
            return

        if node_type == "section":
            if _is_reserved(node):
                return
            ident = str(node.get("identifier", "")).strip()
            citation = section_citation(ident)
            hierarchy = {
                "title": str(title_num),
                "part": str(part_num),
                "section": ident,
            }
            parent_citation = None
            if current_subpart is not None:
                sp_ident = str(current_subpart.get("identifier", "")).strip()
                hierarchy["subpart"] = sp_ident
                parent_citation = subpart_citation(sp_ident)
            items.append({
                "citation": citation,
                "heading": _heading(node),
                "hierarchy": hierarchy,
                "parent_citation": parent_citation,
                "source_url": (
                    f"https://www.ecfr.gov/current/title-{title_num}"
                    f"/section-{ident}"
                ),
            })
            return

        # part / subject_group / division / any container: traverse, carrying
        # the nearest subpart context forward. Intermediate nodes are not
        # emitted as items.
        for child in node.get("children", []):
            walk(child, current_subpart)

    for child in part_node.get("children", []):
        walk(child, None)

    return items
