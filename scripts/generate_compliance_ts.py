#!/usr/bin/env python3
"""Generate client/src/generated/complianceCategories.ts from the compliance registry.

Usage:
    python3 scripts/generate_compliance_ts.py

Reads the canonical compliance registry (server/app/core/compliance_registry.py)
and emits a TypeScript file so the frontend stays in sync without manual edits.
"""

import os
import sys

# ---------------------------------------------------------------------------
# Paths — all relative to this script's location
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
SERVER_DIR = os.path.join(PROJECT_ROOT, "server")
OUTPUT_PATH = os.path.join(
    PROJECT_ROOT, "client", "src", "generated", "complianceCategories.ts"
)

# Add server/ to sys.path so we can import app.core.compliance_registry
sys.path.insert(0, SERVER_DIR)

try:
    from app.core.compliance_registry import (
        CATEGORIES,
        REGULATIONS,
        REGULATIONS_BY_CATEGORY,
        LABOR_CATEGORIES,
        HEALTHCARE_CATEGORIES,
        ONCOLOGY_CATEGORIES,
        MEDICAL_COMPLIANCE_CATEGORIES,
    )
except ImportError as exc:
    print(
        f"ERROR: Could not import from app.core.compliance_registry.\n"
        f"  Make sure server/app/core/compliance_registry.py exists and is valid.\n"
        f"  Import error: {exc}",
        file=sys.stderr,
    )
    sys.exit(1)


def _ts_string(s: str) -> str:
    """Escape a string for safe inclusion in a TypeScript single-quoted literal."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def generate() -> str:
    lines: list[str] = []

    lines.append(
        "// Auto-generated from server/app/core/compliance_registry.py"
    )
    lines.append(
        "// Do not edit manually — run: python3 scripts/generate_compliance_ts.py"
    )
    lines.append("")

    # -----------------------------------------------------------------------
    # CATEGORY_LABELS
    # -----------------------------------------------------------------------
    lines.append("export const CATEGORY_LABELS: Record<string, string> = {")
    for cat in CATEGORIES:
        lines.append(f"  '{_ts_string(cat.key)}': '{_ts_string(cat.label)}',")
    lines.append("};")
    lines.append("")

    # -----------------------------------------------------------------------
    # CATEGORY_SHORT_LABELS
    # -----------------------------------------------------------------------
    lines.append(
        "export const CATEGORY_SHORT_LABELS: Record<string, string> = {"
    )
    for cat in CATEGORIES:
        lines.append(
            f"  '{_ts_string(cat.key)}': '{_ts_string(cat.short_label)}',"
        )
    lines.append("};")
    lines.append("")

    # -----------------------------------------------------------------------
    # CategoryGroup type + CATEGORY_GROUPS map
    # -----------------------------------------------------------------------
    groups = sorted({cat.group for cat in CATEGORIES})
    group_union = " | ".join(f"'{g}'" for g in groups)
    lines.append(f"export type CategoryGroup = {group_union};")
    lines.append("")
    lines.append(
        "export const CATEGORY_GROUPS: Record<string, CategoryGroup> = {"
    )
    for cat in CATEGORIES:
        lines.append(
            f"  '{_ts_string(cat.key)}': '{_ts_string(cat.group)}',"
        )
    lines.append("};")
    lines.append("")

    # -----------------------------------------------------------------------
    # Per-group Sets
    # -----------------------------------------------------------------------
    def _emit_set(name: str, keys: frozenset | set) -> None:
        sorted_keys = sorted(keys)
        items = ", ".join(f"'{_ts_string(k)}'" for k in sorted_keys)
        lines.append(f"export const {name} = new Set([{items}]);")

    _emit_set("LABOR_CATEGORIES", LABOR_CATEGORIES)
    _emit_set("HEALTHCARE_CATEGORIES", HEALTHCARE_CATEGORIES)
    _emit_set("ONCOLOGY_CATEGORIES", ONCOLOGY_CATEGORIES)
    _emit_set("MEDICAL_COMPLIANCE_CATEGORIES", MEDICAL_COMPLIANCE_CATEGORIES)

    # Supplementary — anything not in the other groups
    supplementary_keys = {
        cat.key
        for cat in CATEGORIES
        if cat.group == "supplementary"
    }
    if supplementary_keys:
        _emit_set("SUPPLEMENTARY_CATEGORIES", supplementary_keys)

    lines.append("")

    # -----------------------------------------------------------------------
    # ALL_CATEGORY_KEYS
    # -----------------------------------------------------------------------
    all_keys = [cat.key for cat in CATEGORIES]
    items_str = ", ".join(f"'{_ts_string(k)}'" for k in all_keys)
    lines.append(f"export const ALL_CATEGORY_KEYS: string[] = [{items_str}];")
    lines.append("")

    # -----------------------------------------------------------------------
    # REGULATION_NAMES — reg_key -> display name
    # -----------------------------------------------------------------------
    lines.append(
        "export const REGULATION_NAMES: Record<string, string> = {"
    )
    for reg in REGULATIONS:
        lines.append(
            f"  '{_ts_string(reg.key)}': '{_ts_string(reg.name)}',"
        )
    lines.append("};")
    lines.append("")

    # -----------------------------------------------------------------------
    # REGULATION_KEYS_BY_CATEGORY — category_key -> [reg_key, ...]
    # -----------------------------------------------------------------------
    lines.append(
        "export const REGULATION_KEYS_BY_CATEGORY: Record<string, string[]> = {"
    )
    for cat_key in sorted(REGULATIONS_BY_CATEGORY.keys()):
        reg_list = REGULATIONS_BY_CATEGORY[cat_key]
        reg_keys_str = ", ".join(
            f"'{_ts_string(r.key)}'" for r in reg_list
        )
        lines.append(f"  '{_ts_string(cat_key)}': [{reg_keys_str}],")
    lines.append("};")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    ts_source = generate()

    # Ensure output directory exists
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(ts_source)

    n_categories = len(CATEGORIES)
    n_regulations = len(REGULATIONS)
    # Use a relative path for the printed message
    rel_output = os.path.relpath(OUTPUT_PATH, PROJECT_ROOT)
    print(
        f"Generated {rel_output} "
        f"({n_categories} categories, {n_regulations} regulations)"
    )


if __name__ == "__main__":
    main()
