"""Pure Pydantic + helper tests for the brand-profile write/read validation
added after the 2026-08 review: `hours` was previously unvalidated arbitrary
JSON that could break the iOS `/b/{slug}` decode entirely, and `website` had
no scheme validation. No DB, no HTTP.
"""
import pytest
from pydantic import ValidationError

from app.tellus.models.tellus import TellusBrandUpdate, normalize_brand_hours


class TestHoursWriteValidation:
    def test_accepts_flat_day_map(self):
        body = TellusBrandUpdate(hours={"mon": "9-5", "sun": "closed"})
        assert body.hours == {"mon": "9-5", "sun": "closed"}

    def test_accepts_none(self):
        assert TellusBrandUpdate(hours=None).hours is None

    def test_rejects_nested_value(self):
        with pytest.raises(ValidationError):
            TellusBrandUpdate(hours={"mon": {"open": "9"}})

    def test_rejects_unknown_day_key(self):
        with pytest.raises(ValidationError):
            TellusBrandUpdate(hours={"funday": "9-5"})

    def test_rejects_overlong_value(self):
        with pytest.raises(ValidationError):
            TellusBrandUpdate(hours={"mon": "x" * 41})

    def test_all_blank_values_collapse_to_none(self):
        assert TellusBrandUpdate(hours={"mon": "  "}).hours is None


class TestNormalizeBrandHoursReadPath:
    def test_drops_non_string_values(self):
        assert normalize_brand_hours({"mon": "9-5", "tue": 5}) == {"mon": "9-5"}

    def test_drops_nested_dict_value_entirely(self):
        assert normalize_brand_hours({"mon": {"a": 1}}) is None

    def test_non_dict_input_returns_none(self):
        assert normalize_brand_hours("not a dict") is None
        assert normalize_brand_hours(None) is None

    def test_empty_dict_returns_none(self):
        assert normalize_brand_hours({}) is None


class TestWebsiteWriteValidation:
    def test_accepts_https(self):
        assert TellusBrandUpdate(website="https://acme.test").website == "https://acme.test"

    def test_prepends_scheme_to_bare_host(self):
        assert TellusBrandUpdate(website="acme.test").website == "https://acme.test"

    def test_rejects_javascript_scheme(self):
        with pytest.raises(ValidationError):
            TellusBrandUpdate(website="javascript:alert(1)")

    def test_rejects_non_http_scheme_with_double_slash(self):
        with pytest.raises(ValidationError):
            TellusBrandUpdate(website="ftp://acme.test")

    def test_empty_string_becomes_none(self):
        assert TellusBrandUpdate(website="   ").website is None
