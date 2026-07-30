"""Pure-function tests for the EMS category registry (no DB/Gemini).

    cd server && ./venv/bin/python -m pytest tests/ems/test_categories.py -q
"""

from app.matcha.services.ems import categories


class TestCategories:
    def test_category_keys_unique_and_sections_nonempty(self):
        keys = list(categories.CATEGORIES.keys())
        assert len(keys) == len(set(keys))
        for key, cat in categories.CATEGORIES.items():
            assert cat.key == key
            assert cat.doc_sections
            assert cat.label
            assert cat.example

    def test_six_user_specified_categories_present(self):
        assert set(categories.CATEGORIES.keys()) == {
            "behavioral", "safety", "operational", "equipment", "property", "guest_experience",
        }

    def test_all_keys_includes_fallback(self):
        assert categories.FALLBACK_KEY in categories.ALL_KEYS
        assert categories.ALL_KEYS == set(categories.CATEGORIES.keys()) | {categories.FALLBACK_KEY}


class TestNormalizeCategory:
    def test_known_category_passes_through(self):
        assert categories.normalize_category("safety") == "safety"

    def test_unknown_category_returns_fallback(self):
        assert categories.normalize_category("weather") == categories.FALLBACK_KEY

    def test_none_returns_fallback(self):
        assert categories.normalize_category(None) == categories.FALLBACK_KEY

    def test_empty_string_returns_fallback(self):
        assert categories.normalize_category("") == categories.FALLBACK_KEY


class TestCategoryLabel:
    def test_known_category_label(self):
        assert categories.category_label("guest_experience") == "Guest Experience"

    def test_unknown_category_label_is_uncategorized(self):
        assert categories.category_label("nonsense") == "Uncategorized"


class TestPromptBlock:
    def test_prompt_block_contains_all_six_examples(self):
        block = categories.prompt_block()
        for cat in categories.CATEGORIES.values():
            assert cat.key in block
            assert cat.example in block
