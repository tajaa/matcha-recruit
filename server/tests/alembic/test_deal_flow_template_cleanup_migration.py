"""brokerdrop02 clears the saved Deal Flow templates for the removed broker tabs."""

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

VERSIONS = Path(__file__).parents[2] / "alembic" / "versions"
MIGRATION = VERSIONS / "brokerdrop02_deal_flow_broker_templates.py"


def _load():
    spec = importlib.util.spec_from_file_location("brokerdrop02", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _statements() -> list[str]:
    module = _load()
    recorded: list[str] = []
    module.op = SimpleNamespace(execute=lambda sql: recorded.append(str(sql)))
    module.upgrade()
    return recorded


def test_deletes_the_broker_and_book_templates_and_strips_the_broker_note():
    delete, update = _statements()
    assert delete == "DELETE FROM deal_flow_templates WHERE template_key IN ('broker', 'book')"
    assert "template_key = 'full'" in update
    assert "'sav_n2'" in update


def test_each_statement_is_one_command_without_bind_params():
    for sql in _statements():
        body = re.sub(r"'(?:[^']|'')*'", "''", sql).strip().rstrip(";")
        assert ";" not in body
        assert not text(sql).compile().params, sql


def test_the_stripped_block_is_the_one_the_full_deal_defaults_used_to_ship():
    from app.core.services.deal_full import DEFAULT_FULL_BLOCKS

    assert "sav_n2" not in {block["id"] if isinstance(block, dict) else block.id for block in DEFAULT_FULL_BLOCKS}


def test_chains_after_brokerdrop01_and_is_irreversible():
    module = _load()
    assert module.down_revision == "brokerdrop01"
    with pytest.raises(RuntimeError, match="irreversible"):
        module.downgrade()
