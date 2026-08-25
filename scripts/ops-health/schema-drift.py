#!/usr/bin/env python3
"""Compare exact Alembic revision sets and normalized pg_dump schema output."""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
from pathlib import Path

REVISION_RE = re.compile(r"^[A-Za-z0-9_]+$")
HEADER_RE = re.compile(r"^-- Name: (?P<name>.*); Type: (?P<type>.*); Schema: (?P<schema>.*); Owner: (?P<owner>.*)$")
DOLLAR_TAG_RE = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
AWS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
URI_CREDENTIAL_RE = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@")
SECRET_ASSIGNMENT_RE = re.compile(r"(?i)\b(password|token|secret|api[_-]?key)\s*=\s*[^\s;]+")
PEM_RE = re.compile(r"-----BEGIN [^-]+-----.*?-----END [^-]+-----", re.DOTALL)


def canonical_revision_set(payload: object) -> tuple[str, ...]:
    if not isinstance(payload, dict) or not isinstance(payload.get("revisions"), list):
        raise ValueError("revision payload must contain a revisions array")
    revisions = payload["revisions"]
    if not revisions or any(not isinstance(value, str) or not REVISION_RE.fullmatch(value) for value in revisions):
        raise ValueError("revision set must contain non-empty Alembic revision identifiers")
    if len(set(revisions)) != len(revisions):
        raise ValueError("revision set contains duplicate rows")
    return tuple(sorted(revisions))


def compare_revision_sets(dev_payload: object, prod_payload: object) -> dict:
    dev = canonical_revision_set(dev_payload)
    prod = canonical_revision_set(prod_payload)
    dev_only = sorted(set(dev) - set(prod))
    prod_only = sorted(set(prod) - set(dev))
    return {
        "status": "equal" if not dev_only and not prod_only else "drift",
        "dev_revisions": list(dev),
        "prod_revisions": list(prod),
        "dev_only": dev_only,
        "prod_only": prod_only,
        "needs_schema_diff": bool(dev_only or prod_only),
    }


def update_dollar_quote_state(line: str, active_delimiter: str | None) -> str | None:
    if active_delimiter:
        return None if line.count(active_delimiter) % 2 else active_delimiter
    for match in DOLLAR_TAG_RE.finditer(line):
        delimiter = match.group(0)
        if line[match.start():].count(delimiter) % 2:
            return delimiter
    return None


def split_pg_dump_objects(text: str) -> dict[str, str]:
    sections: list[tuple[str, list[str]]] = []
    current_key: str | None = None
    current_lines: list[str] = []
    delimiter: str | None = None

    def flush() -> None:
        nonlocal current_key, current_lines
        if current_key is not None:
            body = "\n".join(line.rstrip() for line in current_lines).strip()
            if body:
                sections.append((current_key, body))
        current_key, current_lines = None, []

    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        header = HEADER_RE.match(raw_line) if delimiter is None else None
        if header:
            flush()
            current_key = " / ".join((header["schema"] or "-", header["type"], header["name"]))
            current_lines = [f"-- Object: {current_key}"]
            continue
        # pg_dump emits a random psql restrict key outside object definitions.
        # Drop it before assigning trailing lines to the final object section.
        if delimiter is None and re.match(r"^\\(?:un)?restrict\b", raw_line):
            continue
        if current_key is not None:
            current_lines.append(raw_line)
        delimiter = update_dollar_quote_state(raw_line, delimiter)
    flush()
    if not sections:
        raise ValueError("schema dump has no recognizable object sections")

    counts: dict[str, int] = {}
    objects: dict[str, str] = {}
    for key, body in sorted(sections):
        counts[key] = counts.get(key, 0) + 1
        unique_key = key if counts[key] == 1 else f"{key} #{counts[key]}"
        objects[unique_key] = body + "\n"
    return objects


def normalize_pg_dump(text: str) -> tuple[str, dict[str, str]]:
    objects = split_pg_dump_objects(text)
    normalized = "\n".join(objects[key].rstrip() for key in sorted(objects)) + "\n"
    return normalized, objects


def redact_diff(text: str) -> str:
    text = PEM_RE.sub("[PEM REDACTED]", text)
    text = URI_CREDENTIAL_RE.sub(r"\1[REDACTED]@", text)
    text = SECRET_ASSIGNMENT_RE.sub(r"\1=[REDACTED]", text)
    text = AWS_KEY_RE.sub("[AWS KEY REDACTED]", text)
    return EMAIL_RE.sub("[EMAIL REDACTED]", text)


def bounded_unified_diff(dev_text: str, prod_text: str, max_lines: int = 200, max_bytes: int = 20 * 1024) -> str:
    lines = list(difflib.unified_diff(dev_text.splitlines(), prod_text.splitlines(), fromfile="dev", tofile="prod", lineterm=""))
    output: list[str] = []
    size = 0
    for line in lines:
        encoded = (line + "\n").encode()
        if len(output) >= max_lines or size + len(encoded) > max_bytes:
            output.append("... diff truncated ...")
            break
        output.append(line)
        size += len(encoded)
    return redact_diff("\n".join(output))


def compare_schemas(dev_text: str, prod_text: str) -> dict:
    dev_normalized, dev_objects = normalize_pg_dump(dev_text)
    prod_normalized, prod_objects = normalize_pg_dump(prod_text)
    dev_keys = set(dev_objects)
    prod_keys = set(prod_objects)
    changed = sorted(key for key in dev_keys & prod_keys if dev_objects[key] != prod_objects[key])
    return {
        "schema_equal": dev_normalized == prod_normalized,
        "dev_only_objects": sorted(dev_keys - prod_keys),
        "prod_only_objects": sorted(prod_keys - dev_keys),
        "changed_objects": changed,
        "dev_schema_sha256": hashlib.sha256(dev_normalized.encode()).hexdigest(),
        "prod_schema_sha256": hashlib.sha256(prod_normalized.encode()).hexdigest(),
        "diff": bounded_unified_diff(dev_normalized, prod_normalized),
    }


def render_schema_markdown(report: dict, workflow_url: str) -> str:
    lines = ["Production schema drift check.", ""]
    lines.append(f"- Dev Alembic revisions: `{', '.join(report.get('dev_revisions', [])) or 'unavailable'}`")
    lines.append(f"- Prod Alembic revisions: `{', '.join(report.get('prod_revisions', [])) or 'unavailable'}`")
    for key, label in (("dev_only", "Only in dev"), ("prod_only", "Only in prod")):
        for revision in report.get(key, []):
            lines.append(f"- {label}: `{revision}`")
    schema = report.get("schema")
    if schema:
        lines.append(f"- Normalized schema equal: `{schema['schema_equal']}`")
        for key, label in (("dev_only_objects", "Schema object only in dev"), ("prod_only_objects", "Schema object only in prod"), ("changed_objects", "Schema object changed")):
            for value in schema[key][:50]:
                lines.append(f"- {label}: `{value}`")
        if schema["diff"]:
            lines.extend(["", "```diff", schema["diff"], "```"])
    for failure in report.get("failures", []):
        lines.append(f"- Failure: {failure}")
    lines.extend(["", "Alembic revision drift remains actionable even when DDL is equal: the migration may be data-only or bookkeeping may be stale.", f"Workflow: {workflow_url}"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev-revisions", type=Path, required=True)
    parser.add_argument("--prod-revisions", type=Path, required=True)
    parser.add_argument("--dev-schema", type=Path)
    parser.add_argument("--prod-schema", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--workflow-url", required=True)
    args = parser.parse_args()
    try:
        report = compare_revision_sets(json.loads(args.dev_revisions.read_text()), json.loads(args.prod_revisions.read_text()))
        if bool(args.dev_schema) != bool(args.prod_schema):
            raise ValueError("both schema dumps are required together")
        if args.dev_schema and args.prod_schema:
            report["schema"] = compare_schemas(args.dev_schema.read_text(), args.prod_schema.read_text())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {"status": "unknown", "failures": [f"invalid schema check input: {exc}"], "needs_schema_diff": False}
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.markdown.write_text(render_schema_markdown(report, args.workflow_url))
    return 0 if report["status"] == "equal" else 1


if __name__ == "__main__":
    raise SystemExit(main())
