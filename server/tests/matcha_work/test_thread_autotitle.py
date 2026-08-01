import inspect

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.matcha.services.matcha_work import thread_title_service as svc


class TestThinkingConfigNeverUsesBudget:
    def test_maybe_autotitle_source_has_no_thinking_budget(self):
        # thinking_budget=0 is a hard 400 on gemini-3.5-flash-lite (this
        # service's model) — found live via dev-remote.sh smoke test after
        # the F1/F2 fixes only covered provider.py + huume/routing.py, not
        # this call site. thinking_level="minimal" is the thinking-off
        # equivalent that actually works.
        assert "thinking_budget=" not in inspect.getsource(svc.maybe_autotitle_thread)


# --- pure helpers -----------------------------------------------------------

class TestCleanTitle:
    def test_strips_quotes_and_markdown(self):
        assert svc._clean_title('"Offer Letter Draft"') == "Offer Letter Draft"
        assert svc._clean_title("**Payer Review**") == "Payer Review"

    def test_collapses_internal_newlines_and_whitespace(self):
        assert svc._clean_title("Offer\nLetter   Draft\n") == "Offer Letter Draft"

    def test_empty_or_whitespace_only_returns_none(self):
        assert svc._clean_title("") is None
        assert svc._clean_title("   ") is None
        assert svc._clean_title('"""') is None

    def test_overlong_title_truncated(self):
        raw = "Word " * 40
        title = svc._clean_title(raw)
        assert title is not None
        assert len(title) <= svc._MAX_TITLE_LEN

    def test_strips_trailing_punctuation(self):
        assert svc._clean_title("Compliance Check.") == "Compliance Check"


class TestBuildTitlePrompt:
    def test_includes_both_messages(self):
        prompt = svc._build_title_prompt("draft an offer letter", "Sure, who's the candidate?")
        assert "draft an offer letter" in prompt
        assert "who's the candidate?" in prompt

    def test_caller_is_responsible_for_truncation(self):
        # _build_title_prompt itself doesn't truncate — maybe_autotitle_thread
        # slices before calling it. Verify it just interpolates verbatim.
        long_text = "x" * 50
        prompt = svc._build_title_prompt(long_text, "reply")
        assert long_text in prompt


# --- maybe_autotitle_thread --------------------------------------------------

def _conn_ctx(conn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class _FakeConn:
    def __init__(self, title, messages, update_hits=True):
        self._title = title
        self._messages = messages
        self._update_hits = update_hits
        self.update_calls = []

    async def fetchrow(self, query, *args):
        if "UPDATE mw_threads" in query:
            self.update_calls.append(args)
            if self._update_hits:
                return {"id": args[1]}
            return None
        return {"title": self._title}

    async def fetch(self, query, *args):
        return self._messages


@pytest.mark.asyncio
async def test_already_renamed_thread_makes_no_gemini_call():
    thread_id = uuid4()
    conn = _FakeConn(title="My Renamed Thread", messages=[])

    with patch.object(svc, "get_connection", return_value=_conn_ctx(conn)):
        with patch.object(svc, "_get_client") as mock_get_client:
            await svc.maybe_autotitle_thread(thread_id)
            mock_get_client.assert_not_called()
    assert conn.update_calls == []


@pytest.mark.asyncio
async def test_no_assistant_reply_yet_skips_without_calling_gemini():
    thread_id = uuid4()
    conn = _FakeConn(
        title="New Chat",
        messages=[{"role": "user", "content": "draft an offer letter"}],
    )

    with patch.object(svc, "get_connection", return_value=_conn_ctx(conn)):
        with patch.object(svc, "_get_client") as mock_get_client:
            await svc.maybe_autotitle_thread(thread_id)
            mock_get_client.assert_not_called()
    assert conn.update_calls == []


@pytest.mark.asyncio
async def test_gemini_failure_returns_without_raising_or_updating():
    thread_id = uuid4()
    conn = _FakeConn(
        title="New Chat",
        messages=[
            {"role": "user", "content": "draft an offer letter"},
            {"role": "assistant", "content": "Sure, who's the candidate?"},
        ],
    )
    fake_client = MagicMock()
    fake_client.aio.models.generate_content = AsyncMock(side_effect=RuntimeError("boom"))

    with patch.object(svc, "get_connection", return_value=_conn_ctx(conn)):
        with patch.object(svc, "_get_client", return_value=fake_client):
            await svc.maybe_autotitle_thread(thread_id)  # must not raise
    assert conn.update_calls == []


@pytest.mark.asyncio
async def test_success_updates_guarded_on_default_title_and_syncs_element():
    thread_id = uuid4()
    conn = _FakeConn(
        title="New Chat",
        messages=[
            {"role": "user", "content": "draft an offer letter"},
            {"role": "assistant", "content": "Sure, who's the candidate?"},
        ],
        update_hits=True,
    )
    fake_resp = MagicMock()
    fake_resp.text = "Offer Letter Draft"
    fake_client = MagicMock()
    fake_client.aio.models.generate_content = AsyncMock(return_value=fake_resp)

    with patch.object(svc, "get_connection", return_value=_conn_ctx(conn)):
        with patch.object(svc, "_get_client", return_value=fake_client):
            with patch(
                "app.matcha.services.matcha_work.matcha_work_document.sync_element_record",
                new=AsyncMock(),
            ) as mock_sync:
                await svc.maybe_autotitle_thread(thread_id)
                mock_sync.assert_awaited_once_with(thread_id)

    assert len(conn.update_calls) == 1
    title_arg, thread_id_arg, guard_title_arg = conn.update_calls[0]
    assert title_arg == "Offer Letter Draft"
    assert thread_id_arg == thread_id
    assert guard_title_arg == "New Chat"


@pytest.mark.asyncio
async def test_lost_rename_race_skips_sync():
    """A concurrent user rename between the Gemini call and the UPDATE means
    the WHERE title='New Chat' guard misses — no row updated, so no sync."""
    thread_id = uuid4()
    conn = _FakeConn(
        title="New Chat",
        messages=[
            {"role": "user", "content": "draft an offer letter"},
            {"role": "assistant", "content": "Sure, who's the candidate?"},
        ],
        update_hits=False,
    )
    fake_resp = MagicMock()
    fake_resp.text = "Offer Letter Draft"
    fake_client = MagicMock()
    fake_client.aio.models.generate_content = AsyncMock(return_value=fake_resp)

    with patch.object(svc, "get_connection", return_value=_conn_ctx(conn)):
        with patch.object(svc, "_get_client", return_value=fake_client):
            with patch(
                "app.matcha.services.matcha_work.matcha_work_document.sync_element_record",
                new=AsyncMock(),
            ) as mock_sync:
                await svc.maybe_autotitle_thread(thread_id)
                mock_sync.assert_not_called()
