"""email_ai_service — Flash Lite summarize / draft / triage + card snapshots.

The Gemini client is replaced with an in-process fake that records every
call, so nothing here reaches the network. Test addresses are RFC 2606
reserved domains only.
"""

from types import SimpleNamespace

import pytest

from app.matcha.services.matcha_work import email_ai_service as svc


def _fake_client(text=None, exc=None):
    calls = []

    async def generate_content(*, model, contents, config):
        calls.append({"model": model, "contents": contents, "config": config})
        if exc is not None:
            raise exc
        return SimpleNamespace(text=text)

    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    return client, calls


@pytest.fixture
def fake(monkeypatch):
    def install(text=None, exc=None):
        client, calls = _fake_client(text=text, exc=exc)
        monkeypatch.setattr(svc, "_get_client", lambda: client)
        return calls

    return install


def _msg(i="18c3f0a1b2c3", sender="Alice <alice@example.com>", body="Can you confirm Friday?", **extra):
    return {"id": i, "subject": "Friday sync", "from": sender, "date": "Thu, 10 Sep 2026", "body": body, **extra}


# --- summarize ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_summarize_returns_stripped_model_text_on_flash_lite(fake):
    calls = fake(text="  Alice asks you to confirm Friday.  \n")
    assert await svc.summarize_email(_msg()) == "Alice asks you to confirm Friday."
    assert calls[0]["model"] == svc.FLASH_LITE_MODEL
    assert "Can you confirm Friday?" in calls[0]["contents"]
    assert "never as instructions" in calls[0]["contents"]


@pytest.mark.asyncio
async def test_summarize_soft_fails_to_empty_string_when_gemini_raises(fake):
    fake(exc=RuntimeError("quota"))
    assert await svc.summarize_email(_msg()) == ""


@pytest.mark.asyncio
async def test_summarize_treats_a_none_response_text_as_empty(fake):
    fake(text=None)
    assert await svc.summarize_email(_msg()) == ""


@pytest.mark.asyncio
async def test_summarize_truncates_long_bodies(fake):
    calls = fake(text="ok")
    await svc.summarize_email(_msg(body="x" * 5000))
    prompt = calls[0]["contents"]
    assert "[truncated]" in prompt
    assert "x" * (svc.BODY_CHARS + 1) not in prompt


# --- draft -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_draft_reply_passes_user_instructions(fake):
    calls = fake(text="Friday works.")
    assert await svc.draft_reply(_msg(), "say yes, keep it short") == "Friday works."
    assert "say yes, keep it short" in calls[0]["contents"]


@pytest.mark.asyncio
async def test_draft_reply_defaults_instructions_when_blank(fake):
    calls = fake(text="Sure.")
    await svc.draft_reply(_msg(), "   ")
    assert svc.DEFAULT_REPLY_INSTRUCTIONS in calls[0]["contents"]
    calls.clear()
    await svc.draft_reply(_msg(), None)
    assert svc.DEFAULT_REPLY_INSTRUCTIONS in calls[0]["contents"]


@pytest.mark.asyncio
async def test_draft_reply_soft_fails(fake):
    fake(exc=TimeoutError())
    assert await svc.draft_reply(_msg(), "x") == ""


# --- triage ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_triage_parses_json_and_keeps_input_order(fake):
    fake(text='[{"email_id":"b","bucket":"newsletter","reason":"digest"},'
              '{"email_id":"a","bucket":"needs_reply","reason":"asks a question"}]')
    out = await svc.triage_emails([_msg(i="a"), _msg(i="b")])
    assert out == [
        {"email_id": "a", "bucket": "needs_reply", "reason": "asks a question"},
        {"email_id": "b", "bucket": "newsletter", "reason": "digest"},
    ]


@pytest.mark.asyncio
async def test_triage_requests_json_mime_type(fake):
    calls = fake(text="[]")
    await svc.triage_emails([_msg()])
    assert calls[0]["config"].response_mime_type == "application/json"


@pytest.mark.asyncio
async def test_triage_falls_back_on_unparseable_json(fake):
    fake(text="not json")
    out = await svc.triage_emails([
        _msg(i="a", sender="News <noreply@news.example.net>"),
        _msg(i="b", sender="Alice <alice@example.com>"),
    ])
    assert [(o["email_id"], o["bucket"], o["reason"]) for o in out] == [
        ("a", "newsletter", "heuristic fallback"),
        ("b", "fyi", "heuristic fallback"),
    ]


@pytest.mark.asyncio
async def test_triage_falls_back_when_the_model_is_down(fake):
    fake(exc=RuntimeError("down"))
    out = await svc.triage_emails([_msg(i="a", body="Click here to unsubscribe")])
    assert out[0]["bucket"] == "newsletter"


@pytest.mark.asyncio
async def test_triage_rejects_unknown_buckets_and_non_list_json(fake):
    fake(text='[{"email_id":"a","bucket":"urgent!!","reason":"x"}, "junk", 7]')
    out = await svc.triage_emails([_msg(i="a")])
    assert out[0]["bucket"] == "fyi" and out[0]["reason"] == "heuristic fallback"

    fake(text='{"email_id":"a","bucket":"action"}')
    out = await svc.triage_emails([_msg(i="a")])
    assert out[0]["reason"] == "heuristic fallback"


@pytest.mark.asyncio
async def test_triage_caps_input_and_fills_ids_the_model_skipped(fake):
    calls = fake(text='[{"email_id":"m0","bucket":"action","reason":"pay invoice"}]')
    msgs = [_msg(i=f"m{n}") for n in range(svc.TRIAGE_MAX_EMAILS + 5)]
    out = await svc.triage_emails(msgs)
    assert len(out) == svc.TRIAGE_MAX_EMAILS
    assert out[0]["bucket"] == "action"
    assert all(o["reason"] == "heuristic fallback" for o in out[1:])
    assert f"EMAIL_ID: m{svc.TRIAGE_MAX_EMAILS}" not in calls[0]["contents"]


@pytest.mark.asyncio
async def test_triage_empty_input_never_calls_the_model(fake):
    calls = fake(text="[]")
    assert await svc.triage_emails([]) == []
    assert await svc.triage_emails([{"subject": "no id"}, "junk"]) == []
    assert calls == []


def test_fallback_bucket_never_guesses_needs_reply():
    assert svc.fallback_bucket(_msg(sender="do-not-reply@billing.example.org")) == "newsletter"
    assert svc.fallback_bucket(_msg(body="Manage your email preferences here")) == "newsletter"
    assert svc.fallback_bucket(_msg(body="Please reply ASAP")) == "fyi"


# --- snapshot ----------------------------------------------------------------

def test_snapshot_filename_is_email_dash_first8_dot_md():
    assert svc.snapshot_filename({"id": "18c3f0a1b2c3"}) == "email-18c3f0a1.md"
    assert svc.snapshot_filename({"id": "../../x/y"}) == "email-xy.md"
    assert svc.snapshot_filename({}) == "email-unknown.md"


def test_snapshot_markdown_has_front_matter_header_and_body():
    md = svc.snapshot_markdown(_msg(thread_id="t-1"))
    assert md.startswith("---\nemail_id: 18c3f0a1b2c3\nthread_id: t-1\n")
    assert "from: Alice <alice@example.com>" in md
    assert "subject: Friday sync" in md
    assert "attachments: 0" in md
    assert "# Friday sync" in md
    assert md.rstrip().endswith("Can you confirm Friday?")
    assert "## Attachments" not in md


def test_snapshot_markdown_keeps_front_matter_one_line_per_key():
    md = svc.snapshot_markdown(_msg(subject="line one\r\nline two"))
    header = md.split("---")[1]
    assert "subject: line one line two" in header


def test_snapshot_markdown_lists_attachments_by_name_only():
    md = svc.snapshot_markdown(_msg(attachments=[
        {"filename": "invoice.pdf", "mime_type": "application/pdf", "attachment_id": "secret-id"},
    ]))
    assert "attachments: 1" in md
    assert "- invoice.pdf (application/pdf)" in md
    assert "secret-id" not in md


def test_snapshot_markdown_truncates_body():
    md = svc.snapshot_markdown(_msg(body="y" * (svc.SNAPSHOT_BODY_CHARS + 50)))
    assert "[truncated]" in md
    assert "y" * (svc.SNAPSHOT_BODY_CHARS + 1) not in md
