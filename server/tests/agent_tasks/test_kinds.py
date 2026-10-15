"""Kinds of search: research with their own questions, facts and limits."""
from dataclasses import replace

import pytest

from app.matcha.services.matcha_work.agent_tasks import allowance, playbooks
from app.matcha.services.matcha_work.agent_tasks.research import contracts, kinds, prompts
from app.matcha.services.matcha_work.agent_tasks.research import PLAYBOOK as RESEARCH
from app.matcha.services.matcha_work.agent_tasks.service import task_view

from ._fixtures import TODAY, task_row

APARTMENT_BRIEF = {"location": "San Francisco", "budget_max": 3500.0, "currency": "USD", "beds_min": 1.0,
                   "pets": ["dogs"], "move_in": "2026-11-01"}


def test_each_kind_is_a_playbook_on_researchs_phases():
    for kind in kinds.KINDS.values():
        playbook = playbooks.get(kind.key)
        assert playbook.label == kind.label and playbook.item_kinds == (kind.item_kind,)
        assert playbook.phase_key(playbook.first_phase) == "research.plan"
        assert playbook.phases is RESEARCH.phases and kind.key in allowance.WEIGHTS
        assert playbooks.startable(playbook) and set(kind.fields) <= set(playbook.field_library)
    assert playbooks.get("products").actions == ("buy",)
    assert kinds.of(task_row(playbook="apartments")) is kinds.APARTMENTS
    assert kinds.of(task_row()) is None and kinds.of(None) is None
    # Every chain phase name runs one function.
    assert set(playbooks.chain_phases()) == {f"research.{name}" for name in RESEARCH.phases}
    clash = replace(playbooks.get("places"), phases={**RESEARCH.phases, "plan": lambda *a: None})
    with pytest.raises(ValueError, match="is another's"):
        playbooks.validate_registry({**playbooks.PLAYBOOKS, "places": clash})
    with pytest.raises(ValueError, match="phase prefix"):
        replace(playbooks.get("places"), phase_prefix="Bad Prefix").validate()
    assert task_view(task_row(playbook="apartments"))["playbook_label"] == "Apartments"
    assert task_view(task_row(playbook="gone"))["playbook_label"] == ""


def test_an_apartments_brief_is_checked():
    check = playbooks.get("apartments").validate_brief
    assert check({"beds_min": 1, "pets": ["dogs", "cats"], "move_in": "2026-11-01"})["pets"] == ["dogs", "cats"]
    for bad in ({"pets": ["birds"]}, {"beds_min": -1}, {"move_in": "soon"}):
        with pytest.raises(ValueError):
            check(bad)
    with pytest.raises(ValueError):  # research doesn't take an apartment's answers
        RESEARCH.validate_brief({"beds_min": 1})


def test_a_kind_fixes_its_plan_and_adds_its_limits():
    model = {"title": "1bd", "item_kind": "product", "source": "shopping", "queries": ["1 bedroom"],
             "fields": ["rating"], "constraints": [{"field": "beds", "op": "gte", "value": 3}],
             "preferences": [], "fit_weight": 0.4, "prefer_sources": [], "summary": ""}
    plan, _ = contracts.normalize_plan({"result": model}, brief=APARTMENT_BRIEF, today=TODAY, kind=kinds.APARTMENTS)
    assert plan["item_kind"] == "listing" and plan["source"] == "web"
    assert plan["fields"][:7] == list(kinds.APARTMENTS.fields) and "rating" in plan["fields"]
    typed = {(c["field"], c["op"]): c for c in plan["constraints"]}
    assert typed[("beds", "gte")]["value"] == 1 and typed[("beds", "gte")]["source"] == "brief"  # the person's, not the model's 3
    assert typed[("price", "lte")]["unit"] == "month" and typed[("pets", "includes")]["value"] == ["dogs"]
    assert typed[("available_date", "before")]["value"] == "2026-11-01"
    assert plan["queries"] == ["1 bedroom San Francisco"]
    # The fallback plan is its kind too.
    products = contracts.plan_from_brief("organic lip balm", {"budget_max": 15}, today=TODAY, kind=kinds.PRODUCTS)
    assert products["item_kind"] == "product" and products["source"] == "shopping"
    assert products["fields"][:3] == ["price", "rating", "review_count"]
    # Without a kind, nothing changes.
    plain = contracts.plan_from_brief("lip balm", {}, today=TODAY)
    assert plain["source"] == "web" and plain["item_kind"] == "other"
    assert kinds.apartment_limits({"baths_min": 1.5}) == [{"field": "baths", "op": "gte", "value": 1.5}]


def test_a_refine_can_change_the_persons_own_limit():
    plan = contracts.finalize_plan(contracts.plan_from_brief("1bd sf", APARTMENT_BRIEF, today=TODAY,
                                                             kind=kinds.APARTMENTS),
                                   APARTMENT_BRIEF, today=TODAY, kind=kinds.APARTMENTS)
    asked = {"result": {"constraints": [{"field": "beds", "op": "gte", "value": 2}], "preferences": [],
                        "fields_add": [], "queries": [], "search_again": False, "note": "2 beds now"}}
    out, _ = contracts.normalize_refine(asked, plan=plan, brief=APARTMENT_BRIEF, today=TODAY, kind=kinds.APARTMENTS)
    beds = [c for c in out["plan"]["constraints"] if c["field"] == "beds"]
    assert [c["value"] for c in beds] == [2]
    # One the refine left out stays.
    assert any(c["field"] == "pets" for c in out["plan"]["constraints"])


def test_the_planner_is_told_the_kind_and_the_answers():
    text = prompts.plan_instructions(TODAY, kinds.PRODUCTS)
    assert "Kind of search: Products. Its item_kind and source are fixed (product, shopping)." in text
    assert "Kind of search" not in prompts.plan_instructions(TODAY)
    turn = prompts.plan_turn("1bd sf", {**APARTMENT_BRIEF, "odd_key": "x"}, None, labels=kinds.APARTMENTS.labels())
    assert "Rent up to (a month): 3500" in turn and "Bedrooms (at least): 1" in turn and "Odd key: x" in turn
    assert "Pets: dogs" in turn and "Move in by: 2026-11-01" in turn
    assert "Budget (max): 15" in prompts.plan_turn("balm", {"budget_max": 15.0}, None)
