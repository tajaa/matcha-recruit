"""Focused pure-function tests for backup and schema operational checks."""
from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    path = ROOT / "scripts" / "ops-health" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


backup = _load("backup-integrity")
schema = _load("schema-drift")
NOW = datetime(2026, 8, 25, 21, 17, tzinfo=UTC)


def _backup(age_hours: int = 1, size: int = 2 * 1024**2) -> dict:
    return {
        "key": "postgres-selfhosted/matcha_prod_2026-08-25_18-00-00.dump",
        "last_modified": (NOW - timedelta(hours=age_hours)).isoformat(),
        "size_bytes": size,
    }


def _probe(**overrides: object) -> dict:
    return {
        "key": _backup()["key"],
        "s3_read_rc": 0,
        "downloaded_size_bytes": _backup()["size_bytes"],
        "restore_list_rc": 0,
        "toc_entries": 50,
        **overrides,
    }


def test_backup_selects_last_modified_not_filename():
    older = _backup(2)
    older["key"] = "postgres-selfhosted/zzzz.dump"
    newest = _backup(1)
    objects = backup.parse_inventory([older, newest])
    assert backup.select_newest(objects)["key"] == newest["key"]


def test_backup_healthy_when_fresh_sized_and_readable():
    report = backup.evaluate_backup(backup.parse_inventory([_backup()]), _probe(), NOW)
    assert report["status"] == "healthy"
    assert report["backup"]["toc_entries"] == 50


def test_backup_flags_exactly_fifteen_hours_stale():
    report = backup.evaluate_backup(backup.parse_inventory([_backup(15)]), _probe(), NOW)
    assert report["status"] == "unhealthy"
    assert "at least 15 hours old" in report["failures"][0]


def test_backup_flags_objects_smaller_than_one_mib():
    report = backup.evaluate_backup(backup.parse_inventory([_backup(size=1024**2 - 1)]), _probe(downloaded_size_bytes=1024**2 - 1), NOW)
    assert report["status"] == "unhealthy"
    assert any("smaller than 1 MiB" in failure for failure in report["failures"])


def test_backup_flags_size_mismatch_and_unreadable_archive():
    report = backup.evaluate_backup(
        backup.parse_inventory([_backup()]),
        _probe(downloaded_size_bytes=1, restore_list_rc=1, toc_entries=0),
        NOW,
    )
    assert report["status"] == "unhealthy"
    assert len(report["failures"]) == 3


def test_backup_probe_tool_failure_is_unknown_not_corruption():
    report = backup.evaluate_backup(backup.parse_inventory([_backup()]), _probe(restore_list_rc=125), NOW)
    assert report["status"] == "unknown"


def test_backup_rejects_empty_inventory_future_timestamp_and_unsafe_key():
    assert backup.evaluate_backup([], None, NOW)["status"] == "unhealthy"
    future = _backup()
    future["last_modified"] = (NOW + timedelta(minutes=6)).isoformat().replace("+00:00", "Z")
    assert backup.evaluate_backup(backup.parse_inventory([future]), _probe(), NOW)["status"] == "unhealthy"
    with pytest.raises(ValueError):
        backup.validate_backup_key("postgres-selfhosted/../../escape.dump")


def test_backup_timestamp_accepts_z_and_explicit_offset():
    assert backup.parse_timestamp("2026-08-25T21:17:00Z") == backup.parse_timestamp("2026-08-25T14:17:00-07:00")


def test_schema_compares_multihand_sets_exactly_and_order_independently():
    report = schema.compare_revision_sets({"revisions": ["head_b", "head_a"]}, {"revisions": ["head_a", "head_b"]})
    assert report["status"] == "equal"
    assert report["dev_revisions"] == ["head_a", "head_b"]


def test_schema_reports_each_side_and_preserves_ancestor_rows():
    report = schema.compare_revision_sets({"revisions": ["ancestor", "child"]}, {"revisions": ["child", "prod_head"]})
    assert report["status"] == "drift"
    assert report["dev_only"] == ["ancestor"]
    assert report["prod_only"] == ["prod_head"]
    assert report["needs_schema_diff"] is True


@pytest.mark.parametrize("payload", [{}, {"revisions": []}, {"revisions": ["bad-id"]}, {"revisions": ["dup", "dup"]}])
def test_schema_rejects_missing_empty_invalid_or_duplicate_revision_sets(payload):
    with pytest.raises(ValueError):
        schema.canonical_revision_set(payload)


def _dump(table_type: str = "integer", *, reordered: bool = False) -> str:
    table = f"""-- Name: demo; Type: TABLE; Schema: public; Owner: matcha
--

CREATE TABLE public.demo (
    id {table_type} NOT NULL
);
"""
    function = """-- Name: demo_fn(); Type: FUNCTION; Schema: public; Owner: matcha
--

CREATE FUNCTION public.demo_fn() RETURNS text
    LANGUAGE plpgsql
    AS $fn$
BEGIN
    -- Name: this is function text, not a pg_dump header
    RETURN 'ok';
END;
$fn$;
"""
    header = "-- Dumped from database version 15.11\r\n\\restrict randomkey\r\n"
    return header + (function + table if reordered else table + function) + "\\unrestrict randomkey\n"


def test_schema_normalizes_headers_owners_line_endings_and_section_order():
    dev, _ = schema.normalize_pg_dump(_dump())
    prod, _ = schema.normalize_pg_dump(_dump(reordered=True))
    assert dev == prod


def test_schema_preserves_ddl_changes_and_dollar_quoted_header_like_text():
    comparison = schema.compare_schemas(_dump("integer"), _dump("bigint"))
    assert comparison["schema_equal"] is False
    assert "public / TABLE / demo" in comparison["changed_objects"]
    normalized, _ = schema.normalize_pg_dump(_dump())
    assert "this is function text" in normalized


def test_schema_diff_is_capped_and_redacts_secrets():
    diff = schema.bounded_unified_diff("\n".join(f"a{i}" for i in range(300)), "postgresql://user:password@example.com/db\nAKIAABCDEFGHIJKLMNOP\ntoken=topsecret", max_lines=5)
    assert "diff truncated" in diff
    assert "password" not in diff
    assert "AKIA" not in diff


def test_revision_drift_remains_actionable_when_normalized_schema_matches():
    report = schema.compare_revision_sets({"revisions": ["dev_head"]}, {"revisions": ["prod_head"]})
    report["schema"] = schema.compare_schemas(_dump(), _dump())
    assert report["status"] == "drift"
    assert report["schema"]["schema_equal"] is True
