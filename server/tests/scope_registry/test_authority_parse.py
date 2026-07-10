"""The eCFR item-emitting parser. Pure function, fixture-driven, no network."""
import json
from pathlib import Path

import pytest

from app.core.services.scope_registry.authority_parse import parse_ecfr_items

_FIXTURE = Path(__file__).parent / "fixtures" / "ecfr_1910_sample.json"


@pytest.fixture(scope="module")
def items():
    data = json.loads(_FIXTURE.read_text())
    return parse_ecfr_items(data, 29, 1910)


def _by_citation(items, citation):
    return next((i for i in items if i["citation"] == citation), None)


def test_emits_subparts_and_sections(items):
    citations = {i["citation"] for i in items}
    # Subparts A, H, J (B is reserved → skipped).
    assert "29 CFR 1910 Subpart A" in citations
    assert "29 CFR 1910 Subpart H" in citations
    assert "29 CFR 1910 Subpart J" in citations
    # Real sections.
    assert "29 CFR 1910.147" in citations
    assert "29 CFR 1910.119" in citations
    assert "29 CFR 1910.1" in citations


def test_reserved_subpart_skipped(items):
    assert _by_citation(items, "29 CFR 1910 Subpart B") is None


def test_reserved_section_skipped(items):
    # 1910.120 is "[Reserved]" in the fixture.
    assert _by_citation(items, "29 CFR 1910.120") is None


def test_section_parent_is_its_subpart(items):
    lockout = _by_citation(items, "29 CFR 1910.147")
    assert lockout is not None
    # Nested under a subject_group inside Subpart J — parent is the SUBPART,
    # not the intermediate group (which is never emitted).
    assert lockout["parent_citation"] == "29 CFR 1910 Subpart J"
    assert lockout["hierarchy"]["subpart"] == "J"

    psm = _by_citation(items, "29 CFR 1910.119")
    assert psm["parent_citation"] == "29 CFR 1910 Subpart H"


def test_subject_group_not_emitted(items):
    # The intermediate container has no citation of its own.
    assert all("sg-lockout" not in i["citation"] for i in items)
    assert all(i["hierarchy"].get("subpart") != "sg-lockout" for i in items)


def test_subpart_has_no_parent(items):
    sub_j = _by_citation(items, "29 CFR 1910 Subpart J")
    assert sub_j["parent_citation"] is None
    assert "section" not in sub_j["hierarchy"]


def test_hierarchy_shape(items):
    lockout = _by_citation(items, "29 CFR 1910.147")
    assert lockout["hierarchy"] == {"title": "29", "part": "1910", "subpart": "J", "section": "1910.147"}


def test_heading_from_label_description(items):
    lockout = _by_citation(items, "29 CFR 1910.147")
    assert "lockout/tagout" in lockout["heading"].lower()


def test_source_urls_are_ecfr(items):
    for i in items:
        assert i["source_url"].startswith("https://www.ecfr.gov/current/title-29")


def test_no_duplicate_citations(items):
    cits = [i["citation"] for i in items]
    assert len(cits) == len(set(cits))


def test_empty_structure_is_empty_list():
    assert parse_ecfr_items({}, 29, 1910) == []
