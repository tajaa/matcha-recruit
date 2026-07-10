"""codify layer pure core — match_codifications. No DB."""
from app.core.services.scope_registry.codify import match_codifications


def _cls(id, key, kd=None):
    return {"id": id, "regulation_key": key, "key_definition_id": kd}


def _req(id, key, jur="J", category="minimum_wage"):
    return {"id": id, "regulation_key": key, "jurisdiction_id": jur, "category": category}


def test_match_by_key_equality():
    links = match_codifications(
        [_cls("c1", "state_minimum_wage")],
        [_req("r1", "state_minimum_wage")],
    )
    assert len(links) == 1
    assert links[0] == {
        "classification_id": "c1", "jurisdiction_requirement_id": "r1",
        "regulation_key": "state_minimum_wage", "jurisdiction_id": "J",
    }


def test_null_key_classification_never_matches():
    links = match_codifications(
        [_cls("c1", None), _cls("c2", "")],
        [_req("r1", "state_minimum_wage")],
    )
    assert links == []


def test_no_catalog_row_leaves_unmatched():
    links = match_codifications([_cls("c1", "fmla")], [_req("r1", "state_minimum_wage")])
    assert links == []


def test_category_guard_via_rkd():
    # exempt_salary_threshold lives under both minimum_wage and overtime in RKD.
    # A classification tagged (via key_definition_id) to the minimum_wage RKD row
    # must only link the minimum_wage catalog row, not the overtime one.
    links = match_codifications(
        [_cls("c1", "exempt_salary_threshold", kd="kd_mw")],
        [
            _req("r_mw", "exempt_salary_threshold", category="minimum_wage"),
            _req("r_ot", "exempt_salary_threshold", category="overtime"),
        ],
        rkd_category_by_id={"kd_mw": "minimum_wage"},
    )
    assert {l["jurisdiction_requirement_id"] for l in links} == {"r_mw"}


def test_no_key_definition_id_matches_all_categories():
    # Without a kd hint, the guard is off — key equality alone.
    links = match_codifications(
        [_cls("c1", "exempt_salary_threshold")],
        [
            _req("r_mw", "exempt_salary_threshold", category="minimum_wage"),
            _req("r_ot", "exempt_salary_threshold", category="overtime"),
        ],
    )
    assert {l["jurisdiction_requirement_id"] for l in links} == {"r_mw", "r_ot"}


def test_multi_jurisdiction_one_link_per_pair():
    # Same key codified at two levels → one link per catalog row.
    links = match_codifications(
        [_cls("c1", "state_paid_sick_leave")],
        [
            _req("r_state", "state_paid_sick_leave", jur="CA"),
            _req("r_city", "state_paid_sick_leave", jur="SF"),
        ],
    )
    assert len(links) == 2
    assert {l["jurisdiction_id"] for l in links} == {"CA", "SF"}
