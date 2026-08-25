#!/usr/bin/env python3
"""Compare two server-error snapshots without writing production state."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

NORMALIZE = [
    (re.compile(r"[0-9a-f]{8}-[0-9a-f-]{27,}", re.I), "<uuid>"),
    (re.compile(r"0x[0-9a-f]+", re.I), "<hex>"),
    (re.compile(r"\b[0-9a-f]{8,}\b", re.I), "<hexid>"),
    (re.compile(r"'[^']{0,120}'"), "'<s>'"),
    (re.compile(r'"[^"]{0,120}"'), '"<s>"'),
    (re.compile(r"\b\d+\b"), "<n>"),
]
EMAIL = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", re.I)
QUERY = re.compile(r"\?[^\s]+")


def normalize(value: str) -> str:
    for pattern, replacement in NORMALIZE:
        value = pattern.sub(replacement, value)
    return value


def stable_key(row: dict) -> str:
    top_frame = next((line.strip() for line in (row.get("traceback") or "").splitlines() if line.strip().startswith("File ")), "")
    raw = "|".join((row.get("kind") or "", row.get("exception_type") or "", normalize((row.get("message") or "")[:200]), normalize(top_frame)))
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def redact_path(path: str | None) -> str:
    return (path or "unknown endpoint").split("?", 1)[0]


def redact_message(message: str) -> str:
    return QUERY.sub("?[QUERY_REDACTED]", EMAIL.sub("[EMAIL]", message))


def grouped(rows: list[dict]) -> dict[str, dict]:
    values: dict[str, dict] = {}
    for row in rows:
        key = stable_key(row)
        current = values.get(key)
        if current is None or row["last_seen"] > current["last_seen"]:
            values[key] = {**row, "stable_key": key}
        else:
            current["occurrences"] = max(current["occurrences"], row["occurrences"])
    return values


def evaluate(baseline_rows: list[dict], final_rows: list[dict]) -> dict:
    baseline = grouped(baseline_rows)
    final = grouped(final_rows)
    changes = []
    for key, row in final.items():
        before = baseline.get(key, {}).get("occurrences", 0)
        delta = max(0, row["occurrences"] - before)
        is_new = key not in baseline
        if delta or is_new:
            changes.append({
                "stable_key": key,
                "new": is_new,
                "delta": row["occurrences"] if is_new else delta,
                "level": row["level"],
                "kind": row["kind"],
                "source": row["source"],
                "exception_type": row.get("exception_type") or "Error",
                "message": redact_message(normalize((row.get("message") or "")[:200])),
                "path": redact_path(row.get("request_path")),
                "error_id": row["id"],
            })
    new_keys = [row for row in changes if row["new"]]
    total_delta = sum(row["delta"] for row in changes)
    alert = any(row["level"] == "CRITICAL" and row["new"] for row in changes)
    alert = alert or len(new_keys) >= 2 or any(row["delta"] >= 3 for row in changes) or total_delta >= 5
    return {"alert": alert, "total_delta": total_delta, "changes": sorted(changes, key=lambda row: row["delta"], reverse=True)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--final", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(json.loads(args.baseline.read_text())["errors"], json.loads(args.final.read_text())["errors"])
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    return 1 if result["alert"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
