"""Pure-function tests for the changelog auto-generator
(server/scripts/generate_changelog.py). No DB, no network, no Gemini call —
see AUTO_CHANGELOG_PLAN.md Part 6 for the full case list.

scripts/ is not an app package, so it's added to sys.path directly (the
script does the same to itself when run standalone).
"""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

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

    def test_skip_with_reason(self):
        raw = '{"skip": true, "reason": "docs and tests only"}'
        assert gc.parse_entry(raw, _pr(), "matcha") is None

    def test_valid_entry_forces_id_and_date(self):
        pr = _pr(number=42, title="Ignored model title", merged_at="2026-07-15")
        raw = (
            '{"title": "Model chosen title", "category": "Ops", '
            '"summary": "Did a thing.", "whatsNew": ["Added X"], '
            '"howToUse": ["Go here"], "tag": "new"}'
        )
        entry = gc.parse_entry(raw, pr, "matcha")
        assert entry["date"] == "2026-07-15"
        assert entry["tag"] == "new"
        assert entry["whatsNew"] == ["Added X"]
        # Display title is whatever the model chose...
        assert entry["title"] == "Model chosen title"

    def test_id_derived_from_pr_title_not_model_title(self):
        # entry_id must come from the PR's own (stable) title, not the
        # model's — otherwise a rerun with a different model title breaks
        # ON CONFLICT dedup and inserts a duplicate row for the same PR.
        pr = _pr(number=42, title="Ignored model title")
        raw = '{"title": "A totally different title", "summary": "S", "whatsNew": ["x"]}'
        entry = gc.parse_entry(raw, pr, "matcha")
        assert entry["id"] == gc.entry_id(42, "Ignored model title")
        assert entry["id"] != gc.entry_id(42, "A totally different title")

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
        assert '"skip": true' in prompt
        assert '"reason"' in prompt

    def test_matcha_category_vocab_present(self):
        prompt = gc.build_prompt(_pr(), "matcha")
        assert "Broker" in prompt

    def test_tellus_category_vocab_present(self):
        prompt = gc.build_prompt(_pr(), "tellus")
        assert "Consumer" in prompt

    def test_skip_rule_is_narrow_not_refactor_blanket(self):
        # A refactor/fix PR must NOT be told it's automatically a skip — the
        # regression this guards: the original prompt's wide "pure refactor"
        # escape hatch caused Gemini to skip real fixes and feature PRs.
        prompt = gc.build_prompt(_pr(), "matcha")
        assert "NEVER a skip" in prompt
        assert "Fixed: " in prompt

    def test_long_body_is_truncated(self):
        pr = _pr(body="x" * 10_000)
        prompt = gc.build_prompt(pr, "matcha")
        assert "(truncated)" in prompt
        assert len(prompt) < 10_000 + 2_000  # well under body length + prompt scaffolding

    def test_files_beyond_cap_are_dropped(self):
        pr = _pr(files=[f"server/app/matcha/f{i}.py" for i in range(200)])
        prompt = gc.build_prompt(pr, "matcha")
        assert "f119.py" in prompt
        assert "f150.py" not in prompt


class _FakeModels:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def generate_content(self, **_kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _fake_client(outcomes):
    return SimpleNamespace(aio=SimpleNamespace(models=_FakeModels(outcomes)))


def _response():
    return SimpleNamespace(text='{"title":"T","summary":"S","whatsNew":["x"]}')


class TestGenerateEntryRetries:
    def test_retries_transient_gemini_error(self, monkeypatch):
        async def no_sleep(_delay):
            return None

        monkeypatch.setattr(gc, "async_sleep", no_sleep)
        client = _fake_client([RuntimeError("500 INTERNAL"), _response()])

        entry = asyncio.run(gc.generate_entry(client, _pr(number=7), "matcha"))

        assert entry["id"] == "pr-7-some-pr"
        assert client.aio.models.calls == 2

    def test_does_not_retry_non_transient_error(self, monkeypatch):
        sleep_calls = []

        async def record_sleep(delay):
            sleep_calls.append(delay)

        monkeypatch.setattr(gc, "async_sleep", record_sleep)
        client = _fake_client([RuntimeError("400 INVALID_ARGUMENT")])

        with pytest.raises(RuntimeError, match="400 INVALID_ARGUMENT"):
            asyncio.run(gc.generate_entry(client, _pr(number=8), "matcha"))

        assert client.aio.models.calls == 1
        assert sleep_calls == []

    def test_retries_use_last_delay_when_attempts_grow(self, monkeypatch):
        sleep_calls = []

        async def record_sleep(delay):
            sleep_calls.append(delay)

        monkeypatch.setattr(gc, "async_sleep", record_sleep)
        monkeypatch.setattr(gc, "_GEMINI_RETRY_ATTEMPTS", 4)
        client = _fake_client([
            RuntimeError("503"),
            RuntimeError("503"),
            RuntimeError("503"),
            _response(),
        ])

        asyncio.run(gc.generate_entry(client, _pr(number=9), "matcha"))

        assert client.aio.models.calls == 4
        assert sleep_calls == [2.0, 5.0, 5.0]


class TestRetryableGeminiError:
    @pytest.mark.parametrize("message", [
        "429 RESOURCE_EXHAUSTED",
        "500 INTERNAL SERVER ERROR",
        "502 BAD GATEWAY",
        "503 UNAVAILABLE",
        "504 DEADLINE_EXCEEDED",
        "rate_limit exceeded",
    ])
    def test_matches_transient_status_messages(self, message):
        assert gc._is_retryable_gemini_error(RuntimeError(message))

    @pytest.mark.parametrize("message", [
        "request id 1429",
        "resource version 1503",
        "400 INVALID_ARGUMENT",
    ])
    def test_ignores_non_transient_messages(self, message):
        assert not gc._is_retryable_gemini_error(RuntimeError(message))
