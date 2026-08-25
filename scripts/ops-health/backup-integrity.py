#!/usr/bin/env python3
"""Evaluate the newest custom-format production Postgres backup."""
from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

MAX_BACKUP_AGE_SECONDS = 15 * 60 * 60
MIN_BACKUP_SIZE_BYTES = 1024 * 1024
MAX_FUTURE_SKEW_SECONDS = 5 * 60
KEY_RE = re.compile(r"^postgres-selfhosted/[A-Za-z0-9._/-]+\.dump$")


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def validate_backup_key(key: str) -> str:
    if not KEY_RE.fullmatch(key) or ".." in key:
        raise ValueError("backup key is outside the expected prefix")
    return key


def parse_inventory(payload: object) -> list[dict]:
    if not isinstance(payload, list):
        raise ValueError("S3 inventory must be a JSON array")
    objects = []
    for entry in payload:
        if not isinstance(entry, dict):
            raise ValueError("S3 inventory entry must be an object")
        key = validate_backup_key(str(entry.get("key", "")))
        size = entry.get("size_bytes")
        if not isinstance(size, int) or size < 0:
            raise ValueError("backup size must be a non-negative integer")
        objects.append({"key": key, "last_modified": parse_timestamp(str(entry.get("last_modified", ""))), "size_bytes": size})
    return objects


def select_newest(objects: list[dict]) -> dict | None:
    return max(objects, key=lambda item: item["last_modified"], default=None)


def evaluate_backup(objects: list[dict], probe: dict | None, now: datetime) -> dict:
    newest = select_newest(objects)
    if newest is None:
        return {"status": "unhealthy", "failures": ["no backup objects found"], "backup": None}

    now = now.astimezone(UTC)
    age_seconds = int((now - newest["last_modified"]).total_seconds())
    failures = []
    if age_seconds < -MAX_FUTURE_SKEW_SECONDS:
        failures.append("newest backup timestamp is more than five minutes in the future")
    elif age_seconds >= MAX_BACKUP_AGE_SECONDS:
        failures.append("newest backup is at least 15 hours old")
    if newest["size_bytes"] < MIN_BACKUP_SIZE_BYTES:
        failures.append("newest backup is smaller than 1 MiB")

    backup = {
        "key": newest["key"],
        "last_modified": newest["last_modified"].isoformat(),
        "age_seconds": age_seconds,
        "size_bytes": newest["size_bytes"],
        "size_mib": round(newest["size_bytes"] / 1024**2, 2),
    }
    if probe is None:
        return {"status": "unknown", "failures": ["backup readability probe did not run"], "backup": backup}
    if probe.get("key") != newest["key"]:
        return {"status": "unknown", "failures": ["probe key does not match newest backup"], "backup": backup}
    if probe.get("s3_read_rc") != 0:
        return {"status": "unknown", "failures": ["could not read newest backup from S3"], "backup": backup}
    if probe.get("downloaded_size_bytes") != newest["size_bytes"]:
        failures.append("downloaded backup size does not match S3 metadata")
    restore_rc = probe.get("restore_list_rc")
    if restore_rc in {125, 126, 127, -1}:
        return {"status": "unknown", "failures": ["pg_restore probe could not run"], "backup": backup}
    if restore_rc != 0:
        failures.append("pg_restore could not read the backup archive")
    if not isinstance(probe.get("toc_entries"), int) or probe["toc_entries"] <= 0:
        failures.append("backup archive has no readable table-of-contents entries")
    backup["toc_entries"] = probe.get("toc_entries")
    return {"status": "unhealthy" if failures else "healthy", "failures": failures, "backup": backup}


def render_backup_markdown(report: dict, workflow_url: str) -> str:
    backup = report.get("backup")
    lines = ["Production backup integrity check.", ""]
    if backup:
        lines.extend([
            f"- Object: `{backup['key']}`",
            f"- Last modified: `{backup['last_modified']}`",
            f"- Age: `{backup['age_seconds'] // 60} minutes`",
            f"- Size: `{backup['size_bytes']} bytes` ({backup['size_mib']} MiB)",
        ])
        if "toc_entries" in backup:
            lines.append(f"- pg_restore table-of-contents entries: `{backup['toc_entries']}`")
    for failure in report["failures"]:
        lines.append(f"- Failure: {failure}")
    lines.extend(["", f"Workflow: {workflow_url}"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--candidate-output", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--workflow-url", required=True)
    args = parser.parse_args()
    try:
        objects = parse_inventory(json.loads(args.inventory.read_text()))
        if args.candidate_output:
            newest = select_newest(objects)
            if newest is None:
                raise ValueError("no backup objects found")
            args.candidate_output.write_text(json.dumps({
                **newest,
                "last_modified": newest["last_modified"].isoformat(),
            }, indent=2) + "\n")
            args.output.write_text(json.dumps({"status": "candidate"}, indent=2) + "\n")
            args.markdown.write_text("")
            return 0
        probe = json.loads(args.probe.read_text()) if args.probe else None
        report = evaluate_backup(objects, probe, datetime.now(UTC))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {"status": "unknown", "failures": [f"invalid backup check input: {exc}"], "backup": None}
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.markdown.write_text(render_backup_markdown(report, args.workflow_url))
    return 0 if report["status"] == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
