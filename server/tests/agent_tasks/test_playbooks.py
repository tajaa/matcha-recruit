"""The playbook registry and its checks."""
from dataclasses import replace

import pytest

from app.matcha.services.matcha_work.agent_tasks import playbooks
from app.matcha.services.matcha_work.agent_tasks.playbook import IntakeField, ItemField
from app.matcha.services.matcha_work.agent_tasks.research import PLAYBOOK, brief

R = PLAYBOOK


def test_the_registry_is_valid_and_chained():
    playbooks.validate_registry()
    assert playbooks.get("research") is R and playbooks.get(None) is None
    assert "research.plan" in playbooks.chain_phases()
    view = R.view()
    assert view["key"] == "research" and view["available"] is True
    assert view["rounds"] == ["document", "more", "refine"]
    files = [f for f in view["intake"] if f["type"] == "file"]
    assert files[0]["accept"] == ["document", "image"] and files[0]["max_count"] == 3
    assert ItemField(key="pets", label="Pets", type="tags", tags={"dogs": "Dogs OK"}).view()["tags"][0]["value"] == "dogs"


@pytest.mark.parametrize("change,why", [
    ({"key": "Bad Key"}, "bad key"),
    ({"key": "unpriced"}, "no cost"),
    ({"engine": "rocket"}, "unknown engine"),
    ({"description": " "}, "description"),
    ({"intake": tuple(IntakeField(key=f"f{i}", label="x", type="text") for i in range(9))}, "more than"),
    ({"intake": (IntakeField(key="a", label="a", type="text"),) * 2}, "duplicate"),
    ({"intake": (IntakeField(key="a", label="a", type="color"),)}, "bad intake"),
    ({"intake": (IntakeField(key="a", label="a", type="select"),)}, "needs options"),
    ({"intake": (IntakeField(key="a", label="a", type="file"),)}, "file field"),
    ({"field_library": {"x": ItemField(key="y", label="y", type="text")}}, "bad item field"),
    ({"field_library": {"t": ItemField(key="t", label="t", type="tags")}}, "needs its values"),
    ({"item_kinds": ("spaceship",)}, "item kind"),
    ({"first_phase": "nope"}, "first phase"),
    ({"round_phases": {"more": "nope"}}, "round"),
    ({"phases": {**R.phases, "Bad": R.phases["plan"]}}, "phase name"),
    ({"consent": "nope"}, "consent"),
])
def test_validate_names_the_problem(change, why):
    with pytest.raises(ValueError) as exc:
        replace(R, **change).validate()
    assert why in str(exc.value)
    with pytest.raises(ValueError):
        playbooks.validate_registry({"other": R})


def test_consent_that_exists_is_fine():
    replace(R, consent="jobs").validate()


def test_brief_is_checked_and_cleaned():
    assert brief.validate_brief({"location": "  San  Francisco ", "budget_max": 3500, "currency": "usd",
                                 "must_haves": ["Dogs", "dogs", " "], "needed_by": "2026-12-01"}) == {
        "location": "San Francisco", "budget_max": 3500.0, "currency": "USD", "must_haves": ["Dogs"],
        "nice_to_haves": [], "avoid": [], "needed_by": "2026-12-01"}
    assert brief.validate_brief({}) == {"currency": "USD", "must_haves": [], "nice_to_haves": [], "avoid": []}
    for bad in ({"budget_max": -1}, {"color": "red"}, {"currency": "U$D"}):
        with pytest.raises(ValueError):
            brief.validate_brief(bad)
