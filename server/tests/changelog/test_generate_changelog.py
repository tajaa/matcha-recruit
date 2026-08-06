"""Pure-function tests for the changelog auto-generator
(server/scripts/generate_changelog.py). No DB, no network, no Gemini call —
see AUTO_CHANGELOG_PLAN.md Part 6 for the full case list.

scripts/ is not an app package, so it's added to sys.path directly (the
script does the same to itself when run standalone).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import generate_changelog as gc  # noqa: E402


def _pr(**overrides):
    defaults = dict(number=1, title="Some PR", body="", merged_at="2026-08-01", files=[])
    defaults.update(overrides)
    return gc.PrInfo(**defaults)


class TestClassifyPr:
    def test_tellus_only(self):
        files = ["server/app/tellus/routes/dms.py", "client/tellus/src/App.tsx"]
        assert gc.classify_pr(files) == {"tellus"}

    def test_matcha_only(self):
        files = ["server/app/matcha/routes/inventory.py"]
        assert gc.classify_pr(files) == {"matcha"}

    def test_mixed(self):
        files = [
            "server/app/matcha/routes/inventory.py",
            "server/app/tellus/routes/dms.py",
        ]
        assert gc.classify_pr(files) == {"matcha", "tellus"}

    def test_docs_only_skips(self):
        files = ["docs/ops/DEPLOY.md", "CLAUDE.md"]
        assert gc.classify_pr(files) == set()

    def test_ci_only_skips(self):
        files = [".github/workflows/ci.yml"]
        assert gc.classify_pr(files) == set()

    def test_product_file_plus_docs_still_classifies(self):
        files = ["server/app/matcha/routes/inventory.py", "docs/ops/DEPLOY.md"]
        assert gc.classify_pr(files) == {"matcha"}


class TestSlugify:
    def test_long_title_truncates_at_word_boundary(self):
        slug = gc.slugify("Inventory stock audit sheet + voice count dictation")
        assert slug == "inventory-stock-audit-sheet-voice-count"
        assert len(slug) <= 40
        assert not slug.startswith("-")
        assert not slug.endswith("-")

    def test_short_title_unchanged_shape(self):
        assert gc.slugify("Fix bug") == "fix-bug"

    def test_punctuation_collapses(self):
        assert gc.slugify("Fix: thing -> other!!") == "fix-thing-other"


class TestEntryId:
    def test_format(self):
        assert gc.entry_id(149, "Fix: thing -> other") == "pr-149-fix-thing-other"


class TestParseEntry:
    def test_skip_response(self):
        assert gc.parse_entry('{"skip": true}', _pr(), "matcha") is None

    def test_valid_entry_forces_id_and_date(self):
        pr = _pr(number=42, title="Ignored model title", merged_at="2026-07-15")
        raw = (
            '{"title": "Model chosen title", "category": "Ops", '
            '"summary": "Did a thing.", "whatsNew": ["Added X"], '
            '"howToUse": ["Go here"], "tag": "new"}'
        )
        entry = gc.parse_entry(raw, pr, "matcha")
        assert entry["id"] == gc.entry_id(42, "Model chosen title")
        assert entry["date"] == "2026-07-15"
        assert entry["tag"] == "new"
        assert entry["whatsNew"] == ["Added X"]

    def test_unknown_tag_coerced_to_none(self):
        raw = '{"title": "T", "summary": "S", "whatsNew": ["x"], "tag": "banana"}'
        entry = gc.parse_entry(raw, _pr(), "matcha")
        assert entry["tag"] is None

    def test_missing_title_raises(self):
        raw = '{"summary": "S", "whatsNew": ["x"]}'
        try:
            gc.parse_entry(raw, _pr(), "matcha")
            assert False, "expected ChangelogEntryError"
        except gc.ChangelogEntryError:
            pass

    def test_empty_whats_new_raises(self):
        raw = '{"title": "T", "summary": "S", "whatsNew": []}'
        try:
            gc.parse_entry(raw, _pr(), "matcha")
            assert False, "expected ChangelogEntryError"
        except gc.ChangelogEntryError:
            pass

    def test_non_json_raises(self):
        try:
            gc.parse_entry("not json at all", _pr(), "matcha")
            assert False, "expected ChangelogEntryError"
        except gc.ChangelogEntryError:
            pass

    def test_markdown_fenced_json_still_parses(self):
        raw = '```json\n{"title": "T", "summary": "S", "whatsNew": ["x"]}\n```'
        entry = gc.parse_entry(raw, _pr(), "matcha")
        assert entry["title"] == "T"

    def test_missing_category_defaults_to_platform(self):
        raw = '{"title": "T", "summary": "S", "whatsNew": ["x"]}'
        entry = gc.parse_entry(raw, _pr(), "matcha")
        assert entry["category"] == "Platform"


class TestBuildPrompt:
    def test_contains_scope_note_and_skip_escape(self):
        pr = _pr(files=["server/app/matcha/x.py", "server/app/tellus/y.py"])
        prompt = gc.build_prompt(pr, "tellus")
        assert "tellus" in prompt
        assert '{"skip": true}' in prompt

    def test_matcha_category_vocab_present(self):
        prompt = gc.build_prompt(_pr(), "matcha")
        assert "Broker" in prompt

    def test_tellus_category_vocab_present(self):
        prompt = gc.build_prompt(_pr(), "tellus")
        assert "Consumer" in prompt
