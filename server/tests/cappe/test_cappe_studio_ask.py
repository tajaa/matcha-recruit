"""Ask the Studio (services/magazine/studio/ask.py, `POST …/studio/stories/
{id}/ask` in routes/studio.py).

What each block pins:

  * the prompt: the Studio's guide and commands as it sent them (a command
    that can't run now says so), the faces the Studio can set (every family
    in the manifest, once, by kind), the page description, the last turns and
    the question, under rules that allow only what the guide and commands
    name and treat everything sent as material;
  * the admin's model choice for `gummfit.studio` is used; low effort, or
    medium with a reference picture; a deadline on the call;
  * an answer keeps only buttons that name a guide section or command the
    Studio sent (two and three at most); an empty or unreadable answer, an
    API failure or a timeout is `AskFailed`, no Claude is `AskUnavailable`;
  * a reference picture must be the JPEG, PNG or WebP it says it is, under
    2 MB and 4,096 px; anything else is a 422 that spends no allowance;
  * over HTTP: only the owner's paged story, 20 questions a day without
    magazines and 150 with, and no connection held while Claude answers.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_studio_ask.py -q
"""
import asyncio
import base64
import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from app.cappe.routes import studio as studio_mod
from app.cappe.services.magazine.fonts import FONTS
from app.cappe.services.magazine.studio.cuts import CUTS
from app.cappe.services.magazine.studio import ask
from app.cappe.services.magazine.studio.fonts import manifest
from app.core.services import agent_surfaces, anthropic_messages
from tests._helpers.routes import route_client
from tests.cappe.test_cappe_magazine_routes import ACCOUNT, POST, SITE, _owner_conn

GUIDE = [
    {"id": "flow", "title": "Text that flows", "body": "A story can run through several frames.",
     "points": ["Click a frame’s bottom-right box, then click another text frame."]},
    {"id": "cutout", "title": "Cut something out", "body": "", "points": ["Click what to keep."]},
    {"id": "keys", "title": "Keyboard shortcuts", "body": "", "points": ["Space + drag: Move around the pages"]},
]
COMMANDS = [
    {"id": "story-editor", "label": "Story Editor", "keys": "⌘Y", "enabled": True},
    {"id": "cut-out", "label": "Cut out the subject…", "keys": "", "enabled": False},
    {"id": "page-add", "label": "Add a page", "keys": "⇧⌘P", "enabled": True},
    {"id": "duplicate", "label": "Duplicate", "keys": "⌘D", "enabled": True},
]
PAGE = 'Document: 4 pages, each 8.5 in wide × 11 in high.\n- [selected] Text frame "t1": at 0.5 in from the left'


def run(coro):
    return asyncio.run(coro)


def _picture(fmt="PNG", size=(800, 600)) -> str:
    out = io.BytesIO()
    Image.new("RGB", size, (30, 90, 160)).save(out, fmt)
    return base64.b64encode(out.getvalue()).decode()


def _raw(**over):
    return {"question": "How do I make the text carry on in another frame?", "history": [], "guide": GUIDE,
            "commands": COMMANDS, "page": PAGE, "picture": None, **over}


@pytest.fixture
def claude(monkeypatch):
    state = SimpleNamespace(calls=[], reply={"answer": "Click the box.", "guide": [], "commands": []},
                            model=anthropic_messages.CLAUDE_HAIKU, surface=None)

    async def claude_default(surface):
        state.surface = surface
        return state.model

    async def generate_text(prompt, **kw):
        state.calls.append({"prompt": prompt, **kw})
        if isinstance(state.reply, Exception):
            raise state.reply
        return state.reply if isinstance(state.reply, str) else json.dumps(state.reply)

    monkeypatch.setattr(ask.anthropic_messages, "claude_default", claude_default)
    monkeypatch.setattr(ask.anthropic_messages, "generate_text", generate_text)
    return state


# ── the prompt ───────────────────────────────────────────────────────────────

def test_the_prompt_carries_the_guide_commands_fonts_page_and_question(claude):
    q = ask.question(_raw(history=[{"q": "What is a spread?", "a": "Two facing pages."}]))
    run(ask.answer(q))
    call = claude.calls[0]
    prompt = call["prompt"]
    assert "## Text that flows (id: flow)" in prompt and "- Click what to keep." in prompt
    assert "- Story Editor (id: story-editor; key: ⌘Y)" in prompt
    assert "- Cut out the subject… (id: cut-out; can't run right now)" in prompt
    assert "Source Serif 4 (" in prompt and "Bebas Neue (" in prompt
    assert PAGE in prompt
    assert "Q: What is a spread?\nA: Two facing pages." in prompt
    assert prompt.index("<question>") > prompt.index("<page>")
    assert "Only name tools, menus, panels" in call["system"]
    assert "Only suggest fonts from the font list" in call["system"]
    assert "never instructions" in call["system"]
    assert call["json_output"] is True and call["attachments"] == []
    assert claude.surface == agent_surfaces.GUMMFIT_STUDIO and call["model"] == anthropic_messages.CLAUDE_HAIKU
    assert call["effort"] == "low" and call["deadline"] == ask.MODEL_SECONDS


def test_the_font_list_is_every_studio_family_once_by_kind():
    text = ask.fonts_text()
    families = {f["family"] for f in manifest()["faces"]}
    for name in families:
        assert text.count(f"{name} (") == 1, name
    assert text.startswith(("Display:", "Handwriting:", "Monospace:", "Sans serif:", "Serif:"))
    serif = next(line for line in text.splitlines() if line.startswith("Serif:"))
    kind = lambda n: CUTS[n].category if n in CUTS else FONTS[n][0]  # noqa: E731 - a Gummfit cut is a family of its own
    assert all(kind(n) == "serif" for n in families if f"{n} (" in serif)
    assert "Bodoni Moda Display (" in serif


def test_a_familys_weights_are_only_the_ones_it_has():
    # A range only where every hundred is there: never 400–700 for 400 and 700.
    assert ask.weights_text([400, 700]) == "400/700"
    assert ask.weights_text([100, 300, 400, 700, 900]) == "100/300/400/700/900"
    assert ask.weights_text([100, 200, 300, 400, 500, 600, 700, 800, 900]) == "100–900"
    assert ask.weights_text([400, 500, 600, 800]) == "400–600/800"
    assert ask.weights_text([400]) == "400"


def test_a_reference_picture_goes_with_the_question_and_gets_more_thought(claude):
    q = ask.question(_raw(question="Make it look like this", picture={"media_type": "image/png", "data": _picture()}))
    run(ask.answer(q))
    call = claude.calls[0]
    assert [a["source"]["media_type"] for a in call["attachments"]] == ["image/png"]
    assert call["effort"] == "medium" and "The attached picture is the reference" in call["prompt"]


def test_their_own_design_goes_after_the_reference_to_be_compared(claude):
    q = ask.question(_raw(question="How can I make this look like this?",
                          picture={"media_type": "image/png", "data": _picture()},
                          current={"media_type": "image/jpeg", "data": _picture("JPEG", (400, 300))}))
    run(ask.answer(q))
    call = claude.calls[0]
    # The reference first, then theirs, as the prompt says.
    assert [a["source"]["media_type"] for a in call["attachments"]] == ["image/png", "image/jpeg"]
    assert "The first is the reference" in call["prompt"] and "The second is their own design" in call["prompt"]
    assert call["effort"] == "medium"


def test_their_own_design_alone_is_described_as_theirs(claude):
    q = ask.question(_raw(current={"media_type": "image/jpeg", "data": _picture("JPEG")}))
    run(ask.answer(q))
    call = claude.calls[0]
    assert len(call["attachments"]) == 1 and call["effort"] == "medium"
    assert "the person's own design as it looks now" in call["prompt"]
    assert "is the reference" not in call["prompt"]


def test_a_bad_picture_of_their_design_is_refused_like_a_reference():
    with pytest.raises(ask.AskInvalid, match="JPEG, PNG or WebP"):
        ask.question(_raw(current={"media_type": "image/gif", "data": _picture()}))


def test_only_the_last_turns_go_with_a_question():
    turns = [{"q": f"q{i}", "a": f"a{i}"} for i in range(9)]
    q = ask.question(_raw(history=turns))
    assert [t[0] for t in q.history] == [f"q{i}" for i in range(3, 9)]


# ── the answer ───────────────────────────────────────────────────────────────

def test_an_answer_keeps_only_buttons_the_studio_sent(claude):
    claude.reply = {"answer": "  Click the box, then the next frame.  ",
                    "guide": ["flow", "made-up", "flow", "cutout", "keys"],
                    "commands": ["story-editor", "open-a-portal", "page-add", "duplicate", "cut-out"]}
    out = run(ask.answer(ask.question(_raw())))
    assert out == {"answer": "Click the box, then the next frame.", "links": [
        {"kind": "guide", "id": "flow"}, {"kind": "guide", "id": "cutout"},
        {"kind": "command", "id": "story-editor"}, {"kind": "command", "id": "page-add"},
        {"kind": "command", "id": "duplicate"},
    ]}


def test_a_fenced_answer_with_no_lists_still_reads(claude):
    claude.reply = '```json\n{"answer": "Use **Layout → Add a spread**."}\n```'
    assert run(ask.answer(ask.question(_raw()))) == {"answer": "Use **Layout → Add a spread**.", "links": []}


@pytest.mark.parametrize("reply", [
    {"answer": "   ", "guide": ["flow"]},
    "not json at all",
    RuntimeError("Anthropic Messages request failed"),
    TimeoutError(),
])
def test_an_unusable_answer_is_a_failure(claude, reply):
    claude.reply = reply
    with pytest.raises(ask.AskFailed):
        run(ask.answer(ask.question(_raw())))


def test_no_claude_means_unavailable(claude):
    claude.model = None
    with pytest.raises(ask.AskUnavailable):
        run(ask.answer(ask.question(_raw())))
    assert claude.calls == []


# ── what is sent ─────────────────────────────────────────────────────────────

def test_jpeg_and_webp_pictures_are_taken():
    for fmt, mime in (("JPEG", "image/jpeg"), ("WEBP", "image/webp")):
        q = ask.question(_raw(picture={"media_type": mime, "data": _picture(fmt)}))
        assert q.picture["source"]["media_type"] == mime


@pytest.mark.parametrize("picture, says", [
    ({"media_type": "image/gif", "data": _picture()}, "JPEG, PNG or WebP"),
    ({"media_type": "image/jpeg", "data": _picture("PNG")}, "couldn't be read"),  # not what it says it is
    ({"media_type": "image/png", "data": "not base64!"}, "couldn't be read"),
    ({"media_type": "image/png", "data": base64.b64encode(b"hello").decode()}, "couldn't be read"),
    ({"media_type": "image/png", "data": ""}, "couldn't be read"),
    ({"media_type": "image/png", "data": base64.b64encode(b"x" * (ask.MAX_PICTURE_BYTES + 1)).decode()}, "under 2 MB"),
    ({"media_type": "image/png", "data": _picture(size=(4200, 10))}, "4,096 pixels"),
])
def test_a_picture_that_isnt_usable_is_refused(picture, says):
    with pytest.raises(ask.AskInvalid) as caught:
        ask.question(_raw(picture=picture))
    assert says in str(caught.value)


def test_an_empty_question_or_too_much_material_is_refused():
    with pytest.raises(ask.AskInvalid):
        ask.question(_raw(question="   "))
    huge = [{"id": f"s{i}", "title": "T", "body": "x" * 1000, "points": ["y" * 600] * 16} for i in range(5)]
    with pytest.raises(ask.AskInvalid):
        ask.question(_raw(guide=huge))


def test_the_daily_allowance():
    assert ask.daily_allowance({"magazine": True}) == ask.MAGAZINE_PER_DAY == 150
    assert ask.daily_allowance({}) == ask.FREE_PER_DAY == 20


# ── over HTTP ────────────────────────────────────────────────────────────────

@pytest.fixture
def wired(monkeypatch):
    state = SimpleNamespace(open=0, limits=[], features={"magazine": True}, answered=[],
                            conn=_owner_conn(fetchval={"SELECT format FROM cappe_posts": "pages"}),
                            answer={"answer": "Click the box.", "links": [{"kind": "guide", "id": "flow"}]})

    class Ctx:
        async def __aenter__(self):
            state.open += 1
            return state.conn

        async def __aexit__(self, *exc):
            state.open -= 1
            return False

    async def limit(key, action, n, window):
        state.limits.append((key, action, n, window))

    async def entitlements(plan, *, conn=None):
        return SimpleNamespace(features=state.features)

    async def answer(q):
        assert state.open == 0, "Claude must not answer while a connection is held"
        state.answered.append(q)
        if isinstance(state.answer, Exception):
            raise state.answer
        return state.answer

    monkeypatch.setattr(studio_mod, "get_connection", lambda: Ctx())
    monkeypatch.setattr(studio_mod, "check_rate_limit", limit)
    monkeypatch.setattr(studio_mod, "resolve_entitlements", entitlements)
    monkeypatch.setattr(ask, "answer", answer)
    return state


def _post(body):
    with route_client(studio_mod.router, overrides={studio_mod.require_cappe_account: ACCOUNT}) as client:
        return client.post(f"/sites/{SITE}/studio/stories/{POST}/ask", json=body)


def test_their_design_goes_through_the_route(wired):
    res = _post(_raw(picture={"media_type": "image/png", "data": _picture()},
                     current={"media_type": "image/jpeg", "data": _picture("JPEG")}))
    assert res.status_code == 200
    assert wired.answered[0].current["source"]["media_type"] == "image/jpeg"


def test_a_question_is_answered(wired):
    res = _post(_raw())
    assert res.status_code == 200 and res.json() == wired.answer
    assert wired.limits == [(str(ACCOUNT.id), "cappe_studio_ask", 150, 86_400)]
    q = wired.answered[0]
    assert q.question.startswith("How do I make") and q.page == PAGE and q.guide[0]["id"] == "flow"


def test_without_magazines_the_allowance_is_smaller(wired):
    wired.features = {}
    assert _post(_raw()).status_code == 200
    assert wired.limits[0][2] == 20


@pytest.mark.parametrize("fmt, code", [(None, 404), ("blocks", 409)])
def test_only_a_paged_story_can_be_asked_about(wired, fmt, code):
    wired.conn.set("fetchval", "SELECT format FROM cappe_posts", fmt)
    assert _post(_raw()).status_code == code
    assert wired.limits == [] and wired.answered == []


def test_a_bad_picture_is_a_422_that_spends_nothing(wired):
    res = _post(_raw(picture={"media_type": "image/png", "data": base64.b64encode(b"hello").decode()}))
    assert res.status_code == 422 and "couldn't be read" in res.json()["detail"]
    assert wired.limits == [] and wired.answered == []


@pytest.mark.parametrize("over", [
    {"question": ""},
    {"question": "x" * (ask.MAX_QUESTION + 1)},
    {"guide": [{"id": "Not An Id", "title": "T"}]},
    {"commands": [{"id": "ok", "label": "x" * 81}]},
    {"history": [{"q": "q", "a": "a"}] * (ask.MAX_HISTORY + 1)},
    {"page": "x" * (ask.MAX_PAGE_CHARS + 1)},
    {"picture": {"media_type": "image/gif", "data": "R0lG"}},
])
def test_requests_out_of_bounds_are_refused(wired, over):
    assert _post(_raw(**over)).status_code == 422
    assert wired.answered == []


@pytest.mark.parametrize("error, code, says", [
    (ask.AskUnavailable(), 503, ask.UNAVAILABLE),
    (ask.AskFailed("x"), 502, ask.FAILED),
])
def test_failures_say_what_to_do(wired, error, code, says):
    wired.answer = error
    res = _post(_raw())
    assert res.status_code == code and res.json()["detail"] == says
