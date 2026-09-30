import inspect

import pytest

from app.matcha.services.matcha_work.agent_runtime import registry, runner
from app.matcha.services.matcha_work.agent_runtime.registry import (
    AgentTool,
    CatalogError,
    declarations,
    offered_tools,
    validate_catalog,
)

from . import helpers
from .helpers import ability, commit_tool, read_tool

HOSTED = AgentTool(
    name="web_search", effect="read", description="", parameters={}, step_kind="search",
    hosted={"type": "web_search"},
)


def test_tool_names_are_unique_across_the_catalog():
    with pytest.raises(CatalogError, match="declared by both"):
        validate_catalog([ability(read_tool("lookup"), key="a"), ability(read_tool("lookup"), key="b")])


def test_ability_keys_are_unique():
    with pytest.raises(CatalogError, match="duplicate ability key"):
        validate_catalog([ability(key="a"), ability(key="a")])


def test_a_commit_tool_without_targets_is_refused():
    with pytest.raises(CatalogError, match="must declare its targets"):
        validate_catalog([ability(commit_tool(targets=None))])


def test_a_commit_tool_without_a_preview_is_refused():
    with pytest.raises(CatalogError, match="must declare its preview"):
        validate_catalog([ability(commit_tool(preview=None))])


def test_a_tool_is_hosted_or_handled_never_both():
    both = AgentTool(name="x", effect="read", description="", parameters={}, step_kind="read",
                     handler=read_tool().handler, hosted={"type": "web_search"})
    neither = AgentTool(name="y", effect="read", description="", parameters={}, step_kind="read")
    for tool in (both, neither):
        with pytest.raises(CatalogError, match="hosted or handled"):
            validate_catalog([ability(tool)])


def test_a_hosted_tool_can_only_read():
    tool = AgentTool(name="x", effect="draft", description="", parameters={}, step_kind="draft",
                     hosted={"type": "web_search"})
    with pytest.raises(CatalogError, match="can only read"):
        validate_catalog([ability(tool)])


def test_finish_and_ask_belong_to_the_runner():
    with pytest.raises(CatalogError, match="belong to the runner"):
        validate_catalog([ability(helpers.FINISH)])
    finish_with_handler = AgentTool(name="finish", effect="finish", description="", parameters={},
                                    step_kind="finish", handler=read_tool().handler)
    with pytest.raises(CatalogError, match="handled by the runner"):
        registry.validate_tool(finish_with_handler)


def test_unknown_effect_step_kind_and_ceiling_are_refused():
    with pytest.raises(CatalogError, match="unknown effect"):
        registry.validate_tool(read_tool(effect="destroy") if False else AgentTool(
            name="x", effect="destroy", description="", parameters={}, step_kind="read",  # type: ignore[arg-type]
            handler=read_tool().handler))
    with pytest.raises(CatalogError, match="unknown step kind"):
        registry.validate_tool(read_tool(step_kind="mystery") if False else AgentTool(
            name="x", effect="read", description="", parameters={}, step_kind="mystery",
            handler=read_tool().handler))
    with pytest.raises(CatalogError, match="ceilings"):
        validate_catalog([ability(commit_tool(ceilings=((0, 60),)))])


def test_result_blocks_are_unique_and_need_a_gate():
    gate = lambda kind, raw, state: (None, [])  # noqa: E731
    with pytest.raises(CatalogError, match="result block"):
        validate_catalog([
            ability(key="a", block_schemas={"picks": {}}, gate=gate),
            ability(key="b", block_schemas={"picks": {}}, gate=gate),
        ])
    with pytest.raises(CatalogError, match="need a gate"):
        validate_catalog([ability(key="a", block_schemas={"picks": {}})])
    assert ability(key="a", block_schemas={"picks": {}}, gate=gate).block_types == ("picks",)


def test_a_tool_missing_a_scope_is_never_offered():
    gated = read_tool("archive", required_scopes=("gmail.modify",))
    pack = ability(read_tool("search"), gated, required_scopes=("gmail.readonly",))
    none = offered_tools([pack], last_call=False, hosted_left=5, granted_scopes=frozenset())
    assert none == []
    some = offered_tools([pack], last_call=False, hosted_left=5, granted_scopes=frozenset({"gmail.readonly"}))
    assert [t.name for t in some] == ["search"]
    all_ = offered_tools([pack], last_call=False, hosted_left=5,
                         granted_scopes=frozenset({"gmail.readonly", "gmail.modify"}))
    assert [t.name for t in all_] == ["search", "archive"]


def test_hosted_tools_are_dropped_when_the_budget_is_spent_or_on_the_last_turn():
    pack = ability(read_tool("lookup"), HOSTED)
    assert [t.name for t in offered_tools([pack], last_call=False, hosted_left=3)] == ["web_search", "lookup"]
    assert [t.name for t in offered_tools([pack], last_call=False, hosted_left=0)] == ["lookup"]
    assert [t.name for t in offered_tools([pack], last_call=True, hosted_left=3)] == ["lookup"]


def test_declarations_render_hosted_and_function_tools():
    out = declarations([HOSTED, read_tool("lookup")])
    assert out[0] == {"type": "web_search"}
    assert out[1]["type"] == "function" and out[1]["name"] == "lookup"
    assert set(out[1]) == {"type", "name", "description", "parameters"}


def test_the_shipped_abilities_form_a_valid_catalog():
    from app.matcha.services.matcha_work.agent_runtime.abilities import shopping, web

    async def fetch(url):
        return {}, set()

    validate_catalog([web.build(fetch_page=fetch, max_fetches=1, fetch_seconds=1), shopping.build()])


def test_no_positional_tool_slicing():
    from app.matcha.services.matcha_work.agent_card import agent

    for module in (runner, agent):
        assert "tools[1:]" not in inspect.getsource(module)
