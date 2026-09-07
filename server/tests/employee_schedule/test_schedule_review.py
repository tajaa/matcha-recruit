"""schedule_review — the one contract every schedule surface renders. Pure.

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_schedule_review.py -q
"""

from app.matcha.services.scheduling.schedule_review import (
    build_review, compliance_status_for, jurisdiction_message, rejected_entry, summarize_review,
)


def _op(index, *, verdict="ok", reasons=(), before=None, after=None, advisories=(), kind="assign", name="Dana Reyes"):
    return {
        "kind": kind, "shift_id": f"s{index}", "shift_role": "shift lead",
        "starts_at": f"2026-08-2{3 + index}T06:00:00+00:00", "ends_at": f"2026-08-2{3 + index}T14:00:00+00:00",
        "to_employee_id": "e-dana", "to_employee_name": name,
        "from_employee_id": None, "from_employee_name": None,
        "advisories": list(advisories),
        "review": {"verdict": verdict, "reasons": list(reasons),
                   "before": before or {"minutes": 0, "shifts": 0, "days": 0},
                   "after": after or {"minutes": 480, "shifts": 1, "days": 1}},
    }


class TestJurisdictionMessage:
    def test_curated_and_catalog_read_as_on_file(self):
        assert "on file (hand-curated)" in jurisdiction_message({"state": "CA", "status": "curated"})["message"]
        assert "approved catalog research" in jurisdiction_message({"state": "ny", "status": "catalog"})["message"]

    def test_unmapped_says_not_verified_and_what_confirming_means(self):
        info = jurisdiction_message({"state": "TX", "status": "unmapped"})
        assert info["status"] == "unmapped"
        assert "NOT verified for TX" in info["message"]
        assert "Confirming means you've checked" in info["message"]

    def test_unavailable_is_temporary_not_an_all_clear(self):
        assert "not an all-clear" in jurisdiction_message({"state": "TX", "status": "unavailable"})["message"]

    def test_no_state_is_unmapped(self):
        info = jurisdiction_message({"state": None, "status": "unmapped"})
        assert info["state"] is None and "no state on file" in info["message"]
        assert jurisdiction_message(None)["status"] == "unmapped"


class TestComplianceStatus:
    def test_mapping(self):
        assert compliance_status_for({"status": "curated"}, []) == "verified"
        assert compliance_status_for({"status": "catalog"}, [{"message": "x"}]) == "advisory"
        assert compliance_status_for({"status": "unmapped"}, []) == "unmapped"
        assert compliance_status_for({"status": "unavailable"}, [{"message": "x"}]) == "unavailable"


class TestBuildReviewEdit:
    def test_assignments_rejected_employees_and_advisories(self):
        doc = {
            "kind": "edit",
            "ops": [
                _op(0, before={"minutes": 0, "shifts": 0, "days": 0}, after={"minutes": 480, "shifts": 1, "days": 1}),
                _op(1, verdict="warn", reasons=[{"code": "rest_gap", "message": "only 0.0h rest", "policy": True}],
                    before={"minutes": 480, "shifts": 1, "days": 1}, after={"minutes": 960, "shifts": 2, "days": 2},
                    advisories=[{"message": "past 40h incurs weekly overtime", "statute": "FLSA"}]),
            ],
            "rejected": [{"shift_id": "s9", "role": "Shift Lead", "starts_at": "2026-08-23T10:00:00+00:00",
                          "ends_at": "2026-08-23T18:00:00+00:00", "employee_name": "Dana Reyes", "op": "assign",
                          "reasons": [{"code": "intra_batch_overlap", "message": "would overlap …", "policy": False}]}],
            "jurisdiction": {"state": "CA", "status": "curated"},
        }
        review = build_review(doc, proposal_id="p1")
        assert review["proposal_id"] == "p1" and review["kind"] == "edit"
        assert [a["verdict"] for a in review["assignments"]] == ["ok", "warn"]
        assert review["rejected"][0]["shift_id"] == "s9"
        assert review["compliance_status"] == "advisory"          # a statutory advisory is attached
        assert review["advisories"] == [{"message": "past 40h incurs weekly overtime", "statute": "FLSA",
                                         "employee_name": "Dana Reyes", "shift_id": "s1"}]
        dana = review["employees"][0]
        assert dana["before"] == {"minutes": 0, "shifts": 0, "days": 0}
        assert dana["after"] == {"minutes": 960, "shifts": 2, "days": 2}   # last accepted op's after
        assert dana["warnings"] == ["only 0.0h rest"]
        assert review["jurisdiction"]["status"] == "curated"

    def test_unmapped_state_overrides_a_clean_batch(self):
        review = build_review({"kind": "edit", "ops": [_op(0)], "jurisdiction": {"state": "TX", "status": "unmapped"}})
        assert review["compliance_status"] == "unmapped"
        assert "NOT verified for TX" in review["jurisdiction"]["message"]

    def test_ops_without_a_review_render_as_ok(self):
        op = _op(0)
        del op["review"]
        review = build_review({"kind": "edit", "ops": [op], "jurisdiction": {"state": "CA", "status": "curated"}})
        assert review["assignments"][0]["verdict"] == "ok" and review["employees"] == []


class TestBuildReviewCreateAndBatch:
    def _create(self):
        return {
            "kind": "create", "jurisdiction": {"state": "CA", "status": "curated"},
            "shifts": [{
                "id": None, "label": "opener", "starts_at": "2026-08-23T07:00:00+00:00",
                "ends_at": "2026-08-23T15:00:00+00:00",
                "assignees": [{"employee_id": "e1", "name": "Aisha Kim",
                               "violations": [{"message": "meal break", "statute": "Cal. Lab. Code § 512"}]}],
                "intrinsic_violations": [], "excluded": [],
            }, {
                "id": None, "label": "closer", "starts_at": "2026-08-23T15:00:00+00:00",
                "ends_at": "2026-08-23T23:00:00+00:00", "assignees": [], "intrinsic_violations": [], "excluded": [],
            }],
        }

    def test_create_doc(self):
        review = build_review(self._create())
        assert [a["op"] for a in review["assignments"]] == ["create", "create"]
        assert review["assignments"][0]["employee_name"] == "Aisha Kim" and review["assignments"][0]["verdict"] == "warn"
        assert review["assignments"][1]["employee_id"] is None       # open slot still listed
        assert review["compliance_status"] == "advisory"

    def test_batch_doc_merges_both_halves(self):
        doc = {"kind": "batch", "edit": {"ops": [_op(0, kind="cancel")]}, "create": self._create(),
               "rejected": [], "jurisdiction": {"state": "TX", "status": "unmapped"}}
        review = build_review(doc)
        assert [a["op"] for a in review["assignments"]] == ["cancel", "create", "create"]
        assert review["compliance_status"] == "unmapped"


class TestHelpers:
    def test_rejected_entry_is_compact(self):
        op = _op(0, verdict="blocked", reasons=[{"code": "existing_overlap", "message": "already on …", "policy": False}])
        entry = rejected_entry(op)
        assert entry["role"] == "Shift Lead" and entry["employee_name"] == "Dana Reyes"
        assert entry["reasons"][0]["code"] == "existing_overlap" and "review" not in entry

    def test_summarize_review(self):
        review = build_review({
            "kind": "edit",
            "ops": [_op(0), _op(1, verdict="warn", reasons=[{"code": "rest_gap", "message": "only 2h rest", "policy": True}])],
            "rejected": [{"shift_id": "x", "role": "S", "starts_at": "2026-08-23T06:00:00+00:00",
                          "ends_at": "2026-08-23T14:00:00+00:00", "reasons": []}],
            "jurisdiction": {"state": "TX", "status": "unmapped"},
        })
        summary = summarize_review(review)
        assert summary == {
            "staged": 2, "rejected": 1, "unfilled": 0, "warnings": ["only 2h rest"],
            "compliance_status": "unmapped", "jurisdiction_message": review["jurisdiction"]["message"],
        }
