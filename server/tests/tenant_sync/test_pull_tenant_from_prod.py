"""DB-free safety tests for the one-tenant production pull engine."""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


edd = _load("pull_test_export_dev_data", "export-dev-data.py")
pull = _load("pull_tenant_from_prod", "pull_tenant_from_prod.py")


class _FakeConnection:
    async def fetchrow(self, sql, value):
        if 'FROM "jurisdictions"' in sql and value == "j-1":
            return {"id": "j-1", "name": "California"}
        return None

    async def fetch(self, sql, value):
        return []


def test_global_parent_is_skipped_by_default():
    collector = edd.Collector(
        _FakeConnection(),
        {"requirements": ["id", "jurisdiction_id"], "jurisdictions": ["id", "name"]},
        {"requirements": ["id"], "jurisdictions": ["id"]},
        [{
            "child": "requirements", "child_col": "jurisdiction_id",
            "parent": "jurisdictions", "parent_col": "id",
        }],
        set(),
    )
    asyncio.run(collector.collect(
        "requirements", {"id": "r-1", "jurisdiction_id": "j-1"}, descend=True
    ))
    assert not collector.rows["jurisdictions"]
    assert collector.skipped_global["jurisdictions"] == {"j-1"}


def test_global_parent_can_be_included_as_ascend_only_dependency():
    collector = edd.Collector(
        _FakeConnection(),
        {"requirements": ["id", "jurisdiction_id"], "jurisdictions": ["id", "name"]},
        {"requirements": ["id"], "jurisdictions": ["id"]},
        [{
            "child": "requirements", "child_col": "jurisdiction_id",
            "parent": "jurisdictions", "parent_col": "id",
        }],
        set(),
        include_global_dependencies=True,
    )
    asyncio.run(collector.collect(
        "requirements", {"id": "r-1", "jurisdiction_id": "j-1"}, descend=True
    ))
    row, descend = collector.rows["jurisdictions"][("j-1",)]
    assert row["name"] == "California"
    assert descend is False


def test_emit_delete_uses_one_statement_for_self_referencing_rows():
    sql = pull.emit_delete("employees", ["id"], [("2",), ("1",)], edd.lit)
    assert sql == (
        'DELETE FROM "employees" WHERE ("id" = \'1\') OR ("id" = \'2\');'
    )


def test_replacement_deletes_only_target_owned_rows_and_preserves_company_root():
    source = {
        "users": {("u1",): pull.RowSnap({"id": "u1", "email": "dev@example.com"}, False)},
        "companies": {("c1",): pull.RowSnap({"id": "c1", "name": "Prod"}, True)},
        "employees": {("e1",): pull.RowSnap({"id": "e1", "company_id": "c1"}, True)},
    }
    target = {
        "users": {("u1",): pull.RowSnap({"id": "u1", "email": "local@example.com"}, False)},
        "companies": {("c1",): pull.RowSnap({"id": "c1", "name": "Local"}, True)},
        "employees": {
            ("old",): pull.RowSnap({"id": "old", "company_id": "c1"}, True),
            ("shared",): pull.RowSnap({"id": "shared", "company_id": "c1"}, False),
        },
    }
    cols = {
        "users": ["id", "email"],
        "companies": ["id", "name"],
        "employees": ["id", "company_id"],
    }
    pks = {table: ["id"] for table in cols}
    fks = [
        {"child": "employees", "child_col": "company_id", "parent": "companies", "parent_col": "id"},
    ]

    lines, summary = pull.build_replacement_sql(source, target, cols, pks, fks, edd)
    sql = "\n".join(lines)

    assert 'DELETE FROM "employees" WHERE ("id" = \'old\');' in sql
    assert '"id" = \'shared\'' not in sql
    assert 'DELETE FROM "companies"' not in sql
    assert 'INSERT INTO "users"' in sql and "ON CONFLICT DO NOTHING" in sql
    assert 'INSERT INTO "companies"' in sql and "DO UPDATE SET" in sql
    assert summary["deleted_local_rows"] == 1
    assert summary["source_tenant_rows"] == 2
    assert summary["source_dependency_rows"] == 1


def test_relevant_schema_drift_is_a_hard_failure_input():
    source = {"employees": {}}
    problems = pull._relevant_schema_drift(
        source, {},
        {"employees": ["id", "new_col"]},
        {"employees": ["id"]},
        {"employees": ["id"]},
        {"employees": ["id"]},
    )
    assert problems == [
        "employees: prod-only columns ['new_col']; local-only columns []"
    ]


def test_wrapper_keeps_database_credentials_out_of_child_argv():
    wrapper = (SCRIPTS / "pull-tenant-from-prod.sh").read_text()
    assert '--prod-dsn "$PROD_URL"' not in wrapper
    assert '--dev-dsn "$DEV_URL"' not in wrapper
    assert 'PROD_DATABASE_URL="$PROD_URL" DEV_DATABASE_URL="$DEV_URL"' in wrapper


def test_rewrite_foreign_keys_maps_prod_shared_id_to_existing_local_id():
    fks = [{
        "child": "authority_index_items", "child_col": "authority_index_id",
        "parent": "authority_indexes", "parent_col": "id",
    }]
    row = {"id": "item-prod", "authority_index_id": "index-prod"}
    mapped = pull.rewrite_foreign_keys(
        row,
        "authority_index_items",
        fks,
        {("authority_indexes", "id", "index-prod"): "index-local"},
    )
    assert mapped == {"id": "item-prod", "authority_index_id": "index-local"}
    assert row["authority_index_id"] == "index-prod"  # source snapshot not mutated
