"""Pure, DB-free tests for discipline_templates.resolve_template/render_template.

    cd server && ./venv/bin/python -m pytest tests/discipline/test_discipline_templates.py -q
"""

from app.matcha.services.discipline.discipline_templates import (
    DISCIPLINE_TEMPLATE_PLACEHOLDERS,
    render_template,
    resolve_template,
)


def _template(**overrides):
    base = {
        "id": "t1", "name": "Template", "infraction_type": None, "discipline_type": None,
        "is_active": True, "is_default": False, "updated_at": "2026-01-01",
    }
    base.update(overrides)
    return base


class TestResolveTemplate:
    def test_exact_match_wins_over_infraction_only_and_default(self):
        exact = _template(id="exact", infraction_type="attendance", discipline_type="verbal_warning")
        infraction_only = _template(id="infr", infraction_type="attendance", discipline_type=None)
        default = _template(id="def", is_default=True)
        result = resolve_template(
            [default, infraction_only, exact], infraction_type="attendance", discipline_type="verbal_warning",
        )
        assert result["id"] == "exact"

    def test_falls_back_to_infraction_only(self):
        infraction_only = _template(id="infr", infraction_type="attendance", discipline_type=None)
        default = _template(id="def", is_default=True)
        result = resolve_template(
            [default, infraction_only], infraction_type="attendance", discipline_type="written_warning",
        )
        assert result["id"] == "infr"

    def test_falls_back_to_company_default(self):
        default = _template(id="def", is_default=True)
        other = _template(id="other", infraction_type="safety")
        result = resolve_template(
            [other, default], infraction_type="attendance", discipline_type="verbal_warning",
        )
        assert result["id"] == "def"

    def test_none_when_no_match_draft_from_scratch(self):
        other = _template(id="other", infraction_type="safety")
        result = resolve_template([other], infraction_type="attendance", discipline_type="verbal_warning")
        assert result is None

    def test_none_when_no_templates(self):
        assert resolve_template([], infraction_type="attendance", discipline_type="verbal_warning") is None

    def test_ignores_inactive_templates(self):
        inactive_default = _template(id="inactive", is_default=True, is_active=False)
        result = resolve_template(
            [inactive_default], infraction_type="attendance", discipline_type="verbal_warning",
        )
        assert result is None

    def test_ties_broken_by_newest_updated_at(self):
        older = _template(id="older", infraction_type="attendance", updated_at="2026-01-01")
        newer = _template(id="newer", infraction_type="attendance", updated_at="2026-06-01")
        result = resolve_template(
            [older, newer], infraction_type="attendance", discipline_type="verbal_warning",
        )
        assert result["id"] == "newer"


class TestRenderTemplate:
    def test_replaces_known_placeholders(self):
        rendered, missing = render_template(
            "Dear {{employee_name}}, issued {{issued_date}}.",
            {"employee_name": "Jane Doe", "issued_date": "2026-07-28"},
        )
        assert rendered == "Dear Jane Doe, issued 2026-07-28."
        assert missing == []

    def test_leaves_unknown_placeholders_verbatim(self):
        rendered, missing = render_template("Dear {{typo_token}}.", {})
        assert rendered == "Dear {{typo_token}}."
        assert missing == []

    def test_reports_missing_fields_for_empty_values(self):
        rendered, missing = render_template(
            "Manager: {{manager_name}}.", {"manager_name": None},
        )
        assert rendered == "Manager: ."
        assert missing == ["manager_name"]

    def test_missing_field_for_empty_string_too(self):
        rendered, missing = render_template("{{description}}", {"description": ""})
        assert rendered == ""
        assert missing == ["description"]

    def test_placeholder_vocabulary_is_closed(self):
        body = "".join(f"[{{{{{p}}}}}]" for p in DISCIPLINE_TEMPLATE_PLACEHOLDERS)
        values = {p: f"v-{p}" for p in DISCIPLINE_TEMPLATE_PLACEHOLDERS}
        rendered, missing = render_template(body, values)
        assert missing == []
        for p in DISCIPLINE_TEMPLATE_PLACEHOLDERS:
            assert f"v-{p}" in rendered
            assert f"{{{{{p}}}}}" not in rendered
