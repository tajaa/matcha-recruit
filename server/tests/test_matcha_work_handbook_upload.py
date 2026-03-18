from types import SimpleNamespace
from uuid import UUID

import pytest

from app.matcha.services.matcha_work_handbook_upload import (
    MAX_RED_FLAGS,
    AuditedLocation,
    _keyword_list,
    _state_specific_content,
    audit_uploaded_handbook,
    parse_handbook_sections,
)


def test_parse_handbook_sections_splits_heading_blocks():
    text = """
WELCOME

Welcome to the company.

Paid Sick Leave

Employees receive paid sick leave under applicable law.
""".strip()

    sections = parse_handbook_sections(text)

    assert len(sections) >= 2
    assert sections[0].title == "WELCOME"
    assert sections[1].title == "Paid Sick Leave"


def test_audit_uploaded_handbook_flags_missing_location_coverage():
    location = AuditedLocation(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        label="San Francisco, CA",
        state="CA",
        city="San Francisco",
        requirements=[
            SimpleNamespace(
                category="sick_leave",
                title="Paid Sick Leave",
                current_value="40 hours per year",
                jurisdiction_name="San Francisco",
            ),
            SimpleNamespace(
                category="meal_breaks",
                title="Meal and Rest Breaks",
                current_value="State meal and rest periods apply",
                jurisdiction_name="California",
            ),
        ],
    )

    result = audit_uploaded_handbook(
        thread_id=UUID("00000000-0000-0000-0000-000000000010"),
        company_id=UUID("00000000-0000-0000-0000-000000000020"),
        company_name="World Health",
        company_industry="healthcare",
        uploaded_file_url="https://cdn.example.com/handbook.pdf",
        uploaded_filename="world-health-handbook.pdf",
        extracted_text="""
WELCOME

Welcome to the team.

Attendance

Employees are expected to arrive on time.
""".strip(),
        locations=[location],
    )

    assert result["handbook_review_locations"] == ["San Francisco, CA"]
    assert result["handbook_states"] == ["CA"]
    assert result["handbook_sections"]
    assert result["handbook_red_flags"]
    assert any(
        flag["jurisdiction"] == "San Francisco, CA" and "sick leave" in flag["summary"].lower()
        for flag in result["handbook_red_flags"]
    )


def test_audit_uploaded_handbook_caps_section_previews():
    extracted_text = "\n\n".join(
        f"Section {idx}\n\nThis section covers handbook topic {idx}."
        for idx in range(1, 25)
    )
    location = AuditedLocation(
        id=UUID("00000000-0000-0000-0000-000000000111"),
        label="Los Angeles, CA",
        state="CA",
        city="Los Angeles",
        requirements=[
            SimpleNamespace(
                category="sick_leave",
                title="Paid Sick Leave",
                current_value="24 hours per year",
                jurisdiction_name="California",
            ),
        ],
    )

    result = audit_uploaded_handbook(
        thread_id=UUID("00000000-0000-0000-0000-000000000112"),
        company_id=UUID("00000000-0000-0000-0000-000000000113"),
        company_name="Acme",
        company_industry="technology",
        uploaded_file_url="https://cdn.example.com/acme-handbook.pdf",
        uploaded_filename="acme-handbook.pdf",
        extracted_text=extracted_text,
        locations=[location],
    )

    assert len(result["handbook_sections"]) <= 12


def test_audit_uploaded_handbook_rejects_empty_text():
    location = AuditedLocation(
        id=UUID("00000000-0000-0000-0000-000000000201"),
        label="New York, NY",
        state="NY",
        city="New York",
        requirements=[],
    )

    with pytest.raises(ValueError, match="No readable handbook text"):
        audit_uploaded_handbook(
            thread_id=UUID("00000000-0000-0000-0000-000000000202"),
            company_id=UUID("00000000-0000-0000-0000-000000000203"),
            company_name="Acme",
            company_industry="technology",
            uploaded_file_url="https://cdn.example.com/empty.pdf",
            uploaded_filename="empty.pdf",
            extracted_text="   ",
            locations=[location],
        )


# ── Regression tests for accuracy fixes ──────────────────────────────────────


def _make_location(label: str, state: str, city: str | None, category: str, title: str) -> AuditedLocation:
    return AuditedLocation(
        id=UUID("00000000-0000-0000-0000-000000000999"),
        label=label,
        state=state,
        city=city,
        requirements=[
            SimpleNamespace(
                category=category,
                title=title,
                current_value="applicable",
                jurisdiction_name=label,
            )
        ],
    )


def test_ot_false_positive_fixed():
    """'ot' inside common words should NOT trigger overtime coverage."""
    loc = _make_location("California", "CA", None, "overtime", "Overtime Pay")
    result = audit_uploaded_handbook(
        thread_id=UUID("00000000-0000-0000-0000-000000000301"),
        company_id=UUID("00000000-0000-0000-0000-000000000302"),
        company_name="TestCo",
        company_industry="technology",
        uploaded_file_url="https://example.com/h.pdf",
        uploaded_filename="handbook.pdf",
        # Contains "note", "total", "protocol", "remote" — each has "ot" — but
        # no real overtime language.
        extracted_text=(
            "WELCOME\n\nPlease note the total protocol for remote employees. "
            "Notation of all procedures is important. Devoted team members thrive here."
        ),
        locations=[loc],
    )
    red_summaries = " ".join(f["summary"].lower() for f in result["handbook_red_flags"])
    green_cats = {f["category"] for f in result["handbook_green_flags"]}
    assert "overtime" in red_summaries, "'ot' substring should not falsely cover overtime"
    assert "overtime" not in green_cats


def test_multi_state_fallback_to_full_text():
    """Multi-state handbook with generic language should use full text, not return empty."""
    ca_loc = _make_location("California", "CA", None, "minimum_wage", "Minimum Wage")
    ny_loc = _make_location("New York", "NY", None, "minimum_wage", "Minimum Wage")

    result = audit_uploaded_handbook(
        thread_id=UUID("00000000-0000-0000-0000-000000000401"),
        company_id=UUID("00000000-0000-0000-0000-000000000402"),
        company_name="NationalCo",
        company_industry="retail",
        uploaded_file_url="https://example.com/h.pdf",
        uploaded_filename="handbook.pdf",
        # Generic language — no state names — should still match minimum_wage keyword
        extracted_text=(
            "COMPENSATION\n\nAll employees will be paid at least the applicable "
            "minimum wage as required by federal and state law. Pay is reviewed annually."
        ),
        locations=[ca_loc, ny_loc],
    )
    green_cats = {f["category"] for f in result["handbook_green_flags"]}
    assert "minimum_wage" in green_cats, "Generic minimum wage text should be green for multi-state handbook"


def test_state_abbreviation_matching():
    """Handbook referencing 'CA' (abbreviation) should match California state content."""
    sections = parse_handbook_sections(
        "CA Overtime Policy\n\nEmployees in CA receive overtime after 8 hours in a day as required by California law."
    )
    content = _state_specific_content(sections, "CA", ["CA", "NY"])
    assert "overtime" in content.lower(), "State abbreviation 'CA' should match state-specific content"


def test_scheduling_false_positive_fixed():
    """Generic 'scheduling meetings' should NOT trigger scheduling_reporting coverage."""
    loc = _make_location("Oregon", "OR", None, "scheduling_reporting", "Predictive Scheduling")
    result = audit_uploaded_handbook(
        thread_id=UUID("00000000-0000-0000-0000-000000000501"),
        company_id=UUID("00000000-0000-0000-0000-000000000502"),
        company_name="OfficeCo",
        company_industry="technology",
        uploaded_file_url="https://example.com/h.pdf",
        uploaded_filename="handbook.pdf",
        extracted_text=(
            "MEETINGS\n\nAll scheduling of meetings will be handled by your manager. "
            "Scheduling conflicts should be escalated to HR. Meeting scheduling is tracked in our system."
        ),
        locations=[loc],
    )
    red_summaries = " ".join(f["summary"].lower() for f in result["handbook_red_flags"])
    green_cats = {f["category"] for f in result["handbook_green_flags"]}
    assert "scheduling" in red_summaries, "Generic scheduling language should not cover fair workweek requirement"
    assert "scheduling_reporting" not in green_cats


def test_work_permit_false_positive_fixed():
    """Immigration 'work permit' language should NOT trigger minor_work_permit coverage."""
    loc = _make_location("California", "CA", None, "minor_work_permit", "Minor Work Permit")
    result = audit_uploaded_handbook(
        thread_id=UUID("00000000-0000-0000-0000-000000000601"),
        company_id=UUID("00000000-0000-0000-0000-000000000602"),
        company_name="MfgCo",
        company_industry="manufacturing",
        uploaded_file_url="https://example.com/h.pdf",
        uploaded_filename="handbook.pdf",
        extracted_text=(
            "ELIGIBILITY TO WORK\n\nAll new hires must provide a valid work permit or other "
            "employment authorization document as required by federal immigration law. "
            "I-9 verification is required for all employees."
        ),
        locations=[loc],
    )
    red_summaries = " ".join(f["summary"].lower() for f in result["handbook_red_flags"])
    green_cats = {f["category"] for f in result["handbook_green_flags"]}
    assert "youth employment" in red_summaries, "Immigration work permit language should not cover youth employment requirement"
    assert "minor_work_permit" not in green_cats


def test_total_red_flag_count_tracked():
    """handbook_total_red_flag_count should be present and reflect pre-cap total."""
    # Create enough categories to potentially exceed old cap of 20
    categories = [
        ("minimum_wage", "Minimum Wage"),
        ("overtime", "Overtime"),
        ("sick_leave", "Sick Leave"),
        ("meal_breaks", "Meal Breaks"),
        ("final_pay", "Final Pay"),
        ("pay_frequency", "Pay Frequency"),
        ("minor_work_permit", "Minor Work Permit"),
        ("scheduling_reporting", "Predictive Scheduling"),
    ]
    states = ["CA", "NY", "TX", "FL", "WA", "OR", "IL", "CO"]
    locations = [
        AuditedLocation(
            id=UUID(f"00000000-0000-0000-0000-{i:012d}"),
            label=f"{state} Office",
            state=state,
            city=None,
            requirements=[
                SimpleNamespace(category=cat, title=title, current_value="applicable", jurisdiction_name=state)
                for cat, title in categories
            ],
        )
        for i, state in enumerate(states, start=700)
    ]

    result = audit_uploaded_handbook(
        thread_id=UUID("00000000-0000-0000-0000-000000000800"),
        company_id=UUID("00000000-0000-0000-0000-000000000801"),
        company_name="NationalCorp",
        company_industry="retail",
        uploaded_file_url="https://example.com/h.pdf",
        uploaded_filename="handbook.pdf",
        extracted_text="WELCOME\n\nWelcome to the team. We value all employees.",
        locations=locations,
    )

    assert "handbook_total_red_flag_count" in result
    assert result["handbook_total_red_flag_count"] >= len(result["handbook_red_flags"])
    assert len(result["handbook_red_flags"]) <= MAX_RED_FLAGS


def test_toc_only_match_blocked():
    """A keyword appearing only in a short ToC line should not count as coverage."""
    loc = _make_location("California", "CA", None, "minimum_wage", "Minimum Wage")
    result = audit_uploaded_handbook(
        thread_id=UUID("00000000-0000-0000-0000-000000000901"),
        company_id=UUID("00000000-0000-0000-0000-000000000902"),
        company_name="TocCo",
        company_industry="technology",
        uploaded_file_url="https://example.com/h.pdf",
        uploaded_filename="handbook.pdf",
        # "minimum wage" only in a short ToC line — no substantive policy content
        extracted_text=(
            "TABLE OF CONTENTS\n\n"
            "1. Welcome\n2. At-Will Employment\n3. Minimum Wage\n4. Overtime\n\n"
            "WELCOME\n\nWelcome to our company. We are an equal opportunity employer."
        ),
        locations=[loc],
    )
    red_summaries = " ".join(f["summary"].lower() for f in result["handbook_red_flags"])
    green_cats = {f["category"] for f in result["handbook_green_flags"]}
    assert "minimum wage" in red_summaries, "ToC-only mention should not count as minimum wage coverage"
    assert "minimum_wage" not in green_cats


def test_new_mandatory_categories_use_dedicated_keywords():
    """New categories like discrimination/harassment should use their dedicated keyword lists."""
    disc_kw = _keyword_list("discrimination", "Anti-Discrimination Policy")
    assert "discrimination" in disc_kw
    assert "equal employment" in disc_kw
    # Should NOT fall through to generic word extraction
    assert "anti" not in disc_kw

    har_kw = _keyword_list("harassment", "Harassment Prevention Policy")
    assert "harassment" in har_kw
    assert "anti-harassment" in har_kw

    wc_kw = _keyword_list("workers_compensation", "Workers Compensation")
    assert "workers compensation" in wc_kw or "workers' compensation" in wc_kw
