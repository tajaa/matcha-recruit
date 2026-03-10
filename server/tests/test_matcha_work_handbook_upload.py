from types import SimpleNamespace
from uuid import UUID

import pytest

from app.matcha.services.matcha_work_handbook_upload import (
    AuditedLocation,
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
