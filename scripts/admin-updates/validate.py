#!/usr/bin/env python3
"""Strictly validate model-authored /admin/updates content against its plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


MATCHA_CATEGORIES = {
    "Admin", "Broker", "Broker Pilot", "Cappe", "Compliance", "Employee Scheduling",
    "Employees", "HR Pilot", "Handbook Pilot", "IR", "Incident Reporting",
    "Legal Defense", "Legal Pilot", "Limit Adequacy", "Marketing", "Matcha Compliance",
    "Matcha Lite", "Matcha Work", "Newsletter", "Ops", "Property", "Werk",
    "Werk (macOS)", "Workforce Compliance", "Analysis Pilot",
}
TELLUS_CATEGORIES = {"Consumer", "Brand", "Places", "Rewards", "Messages", "Billing", "Platform"}
ENTRY_KEYS = {
    "sourcePr", "product", "id", "date", "category", "title", "summary",
    "whatsNew", "howToUse", "setup", "notes", "tag",
}
SKIP_KEYS = {"sourcePr", "product", "reason"}


class ValidationError(ValueError):
    """Model output violated the trusted publication contract."""


def _plain_text(value: Any, *, field: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string")
    text = value.strip()
    if not minimum <= len(text) <= maximum:
        raise ValidationError(f"{field} length must be {minimum}..{maximum}")
    if any(ord(char) < 32 and char not in "\t" for char in text):
        raise ValidationError(f"{field} contains control characters")
    if "\n" in text or "\r" in text:
        raise ValidationError(f"{field} must be one line")
    return text


def _string_list(value: Any, *, field: str, minimum: int, maximum: int) -> list[str]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValidationError(f"{field} must contain {minimum}..{maximum} strings")
    return [
        _plain_text(item, field=f"{field}[{index}]", minimum=1, maximum=320)
        for index, item in enumerate(value)
    ]


def validate(plan: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    if set(draft) != {"schemaVersion", "processedThroughPr", "entries", "skipped"}:
        raise ValidationError("draft must contain only schemaVersion, processedThroughPr, entries, skipped")
    if draft.get("schemaVersion") != 1:
        raise ValidationError("unsupported draft schemaVersion")
    if draft.get("processedThroughPr") != plan.get("targetWatermark"):
        raise ValidationError("processedThroughPr must equal the plan targetWatermark")
    if not isinstance(draft.get("entries"), list) or not isinstance(draft.get("skipped"), list):
        raise ValidationError("entries and skipped must be arrays")

    expected = {
        (int(unit["sourcePr"]), str(unit["product"])): unit
        for unit in plan.get("units") or []
    }
    seen: set[tuple[int, str]] = set()
    normalized_entries: list[dict[str, Any]] = []
    normalized_skips: list[dict[str, Any]] = []

    for entry in draft["entries"]:
        if not isinstance(entry, dict) or set(entry) != ENTRY_KEYS:
            raise ValidationError(f"each entry must contain exactly {sorted(ENTRY_KEYS)}")
        key = (entry.get("sourcePr"), entry.get("product"))
        if key not in expected:
            raise ValidationError(f"entry {key!r} was not requested by the plan")
        if key in seen:
            raise ValidationError(f"duplicate decision for {key!r}")
        seen.add(key)
        unit = expected[key]
        if entry.get("id") != unit["id"] or entry.get("date") != unit["date"]:
            raise ValidationError(f"entry {key!r} changed its trusted id or deployment date")

        categories = MATCHA_CATEGORIES if entry["product"] == "matcha" else TELLUS_CATEGORIES
        if entry.get("category") not in categories:
            raise ValidationError(f"entry {key!r} has an unsupported category")
        if entry.get("setup") is not None:
            raise ValidationError(f"entry {key!r} cannot publish setup prerequisites as deployed")
        if entry.get("tag") not in (None, "new"):
            raise ValidationError(f"entry {key!r} tag must be new or null")

        notes = entry.get("notes")
        if notes is not None:
            notes = _string_list(notes, field=f"entry {key!r}.notes", minimum=1, maximum=4)
        normalized_entries.append({
            **entry,
            "title": _plain_text(entry["title"], field=f"entry {key!r}.title", minimum=4, maximum=140),
            "summary": _plain_text(entry["summary"], field=f"entry {key!r}.summary", minimum=20, maximum=900),
            "whatsNew": _string_list(entry["whatsNew"], field=f"entry {key!r}.whatsNew", minimum=1, maximum=8),
            "howToUse": _string_list(entry["howToUse"], field=f"entry {key!r}.howToUse", minimum=0, maximum=6),
            "notes": notes,
        })

    for skipped in draft["skipped"]:
        if not isinstance(skipped, dict) or set(skipped) != SKIP_KEYS:
            raise ValidationError(f"each skip must contain exactly {sorted(SKIP_KEYS)}")
        key = (skipped.get("sourcePr"), skipped.get("product"))
        if key not in expected:
            raise ValidationError(f"skip {key!r} was not requested by the plan")
        if key in seen:
            raise ValidationError(f"duplicate decision for {key!r}")
        seen.add(key)
        normalized_skips.append({
            **skipped,
            "reason": _plain_text(skipped.get("reason"), field=f"skip {key!r}.reason", minimum=10, maximum=320),
        })

    missing = sorted(set(expected) - seen)
    if missing:
        raise ValidationError(f"draft omitted decisions for: {missing}")

    return {
        "schemaVersion": 1,
        "processedThroughPr": draft["processedThroughPr"],
        "entries": normalized_entries,
        "skipped": normalized_skips,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("draft", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        normalized = validate(
            json.loads(args.plan.read_text(encoding="utf-8")),
            json.loads(args.draft.read_text(encoding="utf-8")),
        )
    except (ValidationError, json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    args.output.write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
