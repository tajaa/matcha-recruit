"""The server-side op applier, driven by the shared parity fixture.

`services/merlin_apply.py` builds the page the agent loop screenshots. If it
disagrees with the client's `merlinOps.ts` — the applier that mutates the real
editor state — then the model critiques a page the user will never see, which
is a worse failure than editing blind, because it looks like it worked.

`fixtures/merlin_apply_cases.json` is read by BOTH this file and
`merlinOps.test.ts`. Add a case there, not here.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_merlin_apply.py -q
"""
import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.services.merlin_apply import apply_ops  # noqa: E402

_FIXTURE = Path(__file__).parent / "fixtures" / "merlin_apply_cases.json"
_CASES = json.loads(_FIXTURE.read_text())["cases"]


def _ids(case):
    return case["name"]


@pytest.mark.parametrize("case", _CASES, ids=_ids)
def test_shared_parity_fixture(case):
    result = apply_ops(case["blocks"], case["theme"], case["ops"])

    if "expect_ok" in case:
        assert [r["ok"] for r in result.results] == case["expect_ok"]

    if "expect_blocks" in case:
        assert result.blocks == case["expect_blocks"]

    if "expect_theme" in case:
        assert result.theme == case["expect_theme"]

    if "expect_theme_subset" in case:
        for key, expected in case["expect_theme_subset"].items():
            actual = result.theme.get(key)
            if isinstance(expected, dict):
                assert isinstance(actual, dict)
                for sub_key, sub_val in expected.items():
                    assert actual.get(sub_key) == sub_val
            else:
                assert actual == expected

    if "expect_block_count" in case:
        assert len(result.blocks) == case["expect_block_count"]

    if "expect_element_count" in case:
        assert len(result.blocks[0].get("elements") or []) == case["expect_element_count"]

    if "expect_last_element_y" in case:
        els = result.blocks[0]["elements"]
        assert els[-1]["d"]["y"] == case["expect_last_element_y"]

    if "expect_field" in case:
        spec = case["expect_field"]
        assert result.blocks[spec["index"]][spec["path"]] == spec["value"]


def test_apply_is_pure():
    """The agent folds ops onto a working COPY. Mutating the caller's snapshot
    would corrupt the very blocks `validate_ops` is checking against on the next
    tool call."""
    blocks = [{"id": "b1", "type": "hero", "heading": "Old", "_design": {"bg": {"color": "x"}}}]
    theme = {"colors": {"brand": "#111"}}
    apply_ops(
        blocks,
        theme,
        [
            {"op": "set_field", "block": "b1", "path": "heading", "value": "New"},
            {"op": "set_design", "block": "b1", "group": "bg", "key": "color", "value": "surface"},
            {"op": "set_theme", "key": "colors.brand", "value": "#fff"},
        ],
    )
    assert blocks[0]["heading"] == "Old"
    assert blocks[0]["_design"]["bg"]["color"] == "x"
    assert theme["colors"]["brand"] == "#111"


def test_added_blocks_get_distinct_ids():
    """Two adds in one turn must not collide — a later op resolves its target by
    id, and a duplicate would silently retarget the wrong section."""
    result = apply_ops(
        [],
        {},
        [
            {"op": "add_block", "type": "faq", "at": 0, "id": "new-1"},
            {"op": "add_block", "type": "cta", "at": 1, "id": "new-2"},
        ],
    )
    ids = [b["id"] for b in result.blocks]
    assert len(set(ids)) == 2
    assert set(result.temp_id_map) == {"new-1", "new-2"}


def test_unknown_op_is_reported_not_raised():
    """The loop must survive a model inventing an op — skip-and-report is the
    whole validation philosophy."""
    result = apply_ops([], {}, [{"op": "teleport_block", "block": "b1"}])
    assert result.results == [{"ok": False, "summary": "Skipped — unrecognized op"}]
