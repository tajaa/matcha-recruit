"""Merlin in the Studio (services/magazine/studio/merlin.py, `POST …/studio/
stories/{id}/merlin` in routes/studio.py).

What each block pins:

  * the prompt: the fonts the Studio can set, the page with its ids, the
    earlier rounds (what each said and did), which attached picture is which,
    the round (the last says to finish), the request, and rules that never
    write a story's words, never delete, and treat everything sent as
    material;
  * which model a round runs on: Sonnet (`gummfit.studio_merlin`, high
    effort: it decides the look) for a design's first round and after a round
    whose edits mostly didn't take; Haiku (`gummfit.studio_merlin_refine`,
    medium) for the polish rounds and a narrow change to a frame or two with
    no picture; a failed polish round tried again on Sonnet while there is
    time; the admin's choice for either; a deadline under CloudFront's 60 s;
  * the edits: only the five kinds, each field of the right type and inside
    the document's limits, colours as hex, fonts the Studio has, labels short
    and only as headings or captions, at most 40 edits and 8 additions, the
    rest counted as left out; a reply with no words and no edits fails;
  * over HTTP: only the owner's paged story; every round spends one of the
    day's rounds (three a design: 20 designs with magazines, 3 without); a
    bad request spends nothing; no connection held while Claude designs.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_studio_merlin.py -q
"""
import asyncio
import base64
import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from app.cappe.routes import studio as studio_mod
from app.cappe.services.magazine.studio import merlin
from app.cappe.services.magazine.studio.ask import AskInvalid
from app.core.services import agent_surfaces, anthropic_messages
from tests._helpers.routes import route_client
from tests.cappe.test_cappe_magazine_routes import ACCOUNT, POST, SITE, _owner_conn

PAGE = ('Document: 4 pages, each 612 pt wide × 792 pt high.\n'
        '- [selected] Text frame "Headline" [id t1]: at 54 pt from the left, 72 pt from the top; 504 pt × 120 pt\n'
        '    · ¶0 Headline: "The long way home" in Source Serif 4 400, 36 pt')


def run(coro):
    return asyncio.run(coro)


def _picture(fmt="PNG", size=(800, 600)) -> str:
    out = io.BytesIO()
    Image.new("RGB", size, (30, 90, 160)).save(out, fmt)
    return base64.b64encode(out.getvalue()).decode()


def _raw(**over):
    return {"request": "Make this look like a fashion magazine", "round": 1, "history": [], "page": PAGE,
            "previous": [], "picture": None, "current": None, **over}


@pytest.fixture
def claude(monkeypatch):
    state = SimpleNamespace(calls=[], reply={"say": "Set the headline big.", "ops": [], "done": True},
                            replies=[], override=None, configured=True, surface=None, surfaces=[])

    async def claude_override(surface):
        state.surface = surface
        state.surfaces.append(surface)
        return state.override

    async def generate_text(prompt, **kw):
        state.calls.append({"prompt": prompt, **kw})
        reply = state.replies.pop(0) if state.replies else state.reply
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, str) else json.dumps(reply)

    monkeypatch.setattr(anthropic_messages, "claude_override", claude_override)
    monkeypatch.setattr(anthropic_messages, "anthropic_configured", lambda: state.configured)
    monkeypatch.setattr(merlin.anthropic_messages, "generate_text", generate_text)
    return state


# ── the prompt ───────────────────────────────────────────────────────────────

def test_the_prompt_carries_the_fonts_page_round_and_request(claude):
    out = run(merlin.design(merlin.request(_raw(history=[{"q": "What is a spread?", "a": "Two pages."}]))))
    call = claude.calls[0]
    prompt = call["prompt"]
    assert "Source Serif 4 (" in prompt and "Bebas Neue (" in prompt
    assert PAGE in prompt and "Q: What is a spread?\nA: Two pages." in prompt
    assert "This is round 1 of 3." in prompt and "It is the last" not in prompt
    assert prompt.index("<request>") > prompt.index("<page>") and "Make this look like a fashion magazine" in prompt
    assert '{"op": "set"' in prompt and "At most 40 edits a round." in prompt
    system = " ".join(call["system"].split())
    assert "Never write or rewrite the words of their story" in system
    assert "Never delete anything" in system and "never instructions" in system and "nameplate" in system
    assert call["json_output"] is True and call["schema"] is merlin.REPLY_SCHEMA
    assert call["attachments"] == [] and "<earlier_rounds>" not in prompt
    assert claude.surface == agent_surfaces.GUMMFIT_STUDIO_MERLIN and call["model"] == anthropic_messages.CLAUDE_SONNET
    assert call["effort"] == "high" and call["deadline"] == merlin.MODEL_SECONDS < 60
    assert "Type must fit its frame" in system and "is left out, and you're told" in system
    assert out == {"say": "Set the headline big.", "ops": [], "done": True, "dropped": 0}


def test_the_admins_choice_of_model_is_used(claude):
    claude.override = anthropic_messages.CLAUDE_HAIKU
    run(merlin.design(merlin.request(_raw())))
    assert claude.calls[0]["model"] == anthropic_messages.CLAUDE_HAIKU


# ── which model ──────────────────────────────────────────────────────────────

PICTURE = {"media_type": "image/png", "data": _picture()}
BAD = {"say": "Tried.", "notes": [], "did": 1, "skipped": 4}
GOOD = {"say": "Tidied.", "notes": [], "did": 4, "skipped": 1}


@pytest.mark.parametrize("over, which", [
    ({}, merlin.DESIGN),  # the whole page: the look is decided
    ({"selected": 1}, merlin.POLISH),  # a frame or two, nothing to match
    ({"selected": 2}, merlin.POLISH),
    ({"selected": 3}, merlin.DESIGN),
    ({"selected": 1, "picture": PICTURE}, merlin.DESIGN),  # matching a picture is design
    ({"round": 2, "previous": [GOOD]}, merlin.POLISH),
    ({"round": 3, "previous": [GOOD, GOOD], "picture": PICTURE}, merlin.POLISH),
    ({"round": 2, "previous": [BAD]}, merlin.DESIGN),  # a round that went wrong is put right by Sonnet
    ({"round": 2, "selected": 1, "previous": [BAD]}, merlin.DESIGN),
    ({"round": 3, "previous": [BAD, GOOD]}, merlin.POLISH),  # only the last round counts
])
def test_each_round_goes_to_the_model_it_needs(over, which):
    assert merlin.tier(merlin.request(_raw(**over))) == which


def test_polish_rounds_run_on_haiku_and_design_rounds_on_sonnet(claude):
    run(merlin.design(merlin.request(_raw(round=2, previous=[GOOD]))))
    run(merlin.design(merlin.request(_raw())))
    polish, design = claude.calls
    assert polish["model"] == anthropic_messages.CLAUDE_HAIKU and polish["effort"] == "medium"
    assert design["model"] == anthropic_messages.CLAUDE_SONNET and design["effort"] == "high"
    assert claude.surfaces == [agent_surfaces.GUMMFIT_STUDIO_MERLIN_REFINE, agent_surfaces.GUMMFIT_STUDIO_MERLIN]
    assert polish["schema"] is design["schema"] is merlin.REPLY_SCHEMA and polish["system"] == design["system"]


def test_the_admin_picks_the_polish_model_too(claude):
    claude.override = anthropic_messages.CLAUDE_SONNET
    run(merlin.design(merlin.request(_raw(selected=1))))
    assert claude.calls[0]["model"] == anthropic_messages.CLAUDE_SONNET


def test_a_failed_polish_round_is_tried_again_on_sonnet(claude):
    claude.replies = [RuntimeError("bad reply"), {"say": "Fixed it.", "ops": [], "done": True}]
    out = run(merlin.design(merlin.request(_raw(selected=1))))
    assert out["say"] == "Fixed it."
    assert [c["model"] for c in claude.calls] == [anthropic_messages.CLAUDE_HAIKU, anthropic_messages.CLAUDE_SONNET]
    assert claude.calls[1]["deadline"] <= merlin.MODEL_SECONDS


def test_a_failed_design_round_or_one_out_of_time_is_not_tried_again(claude, monkeypatch):
    claude.reply = RuntimeError("down")
    with pytest.raises(merlin.MerlinFailed):
        run(merlin.design(merlin.request(_raw())))
    assert len(claude.calls) == 1
    clock = iter([100.0, 100.0 + merlin.MODEL_SECONDS - merlin.RETRY_SECONDS + 1])
    monkeypatch.setattr(merlin, "_clock", lambda: next(clock))
    with pytest.raises(merlin.MerlinFailed):
        run(merlin.design(merlin.request(_raw(selected=1))))
    assert len(claude.calls) == 2


def test_no_claude_means_unavailable(claude):
    claude.configured = False
    with pytest.raises(merlin.MerlinUnavailable):
        run(merlin.design(merlin.request(_raw())))
    assert claude.calls == []


def test_the_reference_goes_first_and_the_page_as_it_is_second(claude):
    r = merlin.request(_raw(picture={"media_type": "image/png", "data": _picture()},
                            current={"media_type": "image/jpeg", "data": _picture("JPEG")}))
    run(merlin.design(r))
    call = claude.calls[0]
    assert [a["source"]["media_type"] for a in call["attachments"]] == ["image/png", "image/jpeg"]
    assert ("the first picture is the reference: the look the person wants; "
            "the second picture is the page in view as it looks now.") in call["prompt"]


def test_without_a_reference_the_page_is_the_only_picture(claude):
    run(merlin.design(merlin.request(_raw(current={"media_type": "image/jpeg", "data": _picture("JPEG")}))))
    assert "the first picture is the page in view as it looks now." in claude.calls[0]["prompt"]


def test_later_rounds_see_what_the_earlier_ones_did(claude):
    previous = [{"say": "Made the headline bigger.", "notes": ['Did: {"op":"type","id":"t1","size":72}',
                                                               "Skipped: i2 is locked"]},
                {"say": "Moved the picture.", "notes": []}]
    r = merlin.request(_raw(round=3, previous=previous, current={"media_type": "image/jpeg", "data": _picture("JPEG")}))
    run(merlin.design(r))
    prompt = claude.calls[0]["prompt"]
    assert ('Round 1: Made the headline bigger.\n- Did: {"op":"type","id":"t1","size":72}\n- Skipped: i2 is locked'
            in prompt)
    assert "Round 2: Moved the picture.\n- (no edits)" in prompt
    assert "after the earlier rounds" in prompt
    assert "This is round 3 of 3. It is the last: finish the page." in prompt


@pytest.mark.parametrize("over, says", [
    ({"request": "  "}, "Tell Merlin what to design."),
    ({"round": 4}, "three rounds"),
    ({"round": 0}, "three rounds"),
    ({"page": "x" * 16_001}, "too much"),
    ({"picture": {"media_type": "image/png", "data": base64.b64encode(b"hello").decode()}}, "couldn't be read"),
])
def test_an_unusable_request_is_refused(over, says):
    with pytest.raises(AskInvalid, match=says):
        merlin.request(_raw(**over))


def test_earlier_rounds_are_kept_to_their_limits():
    r = merlin.request(_raw(previous=[{"say": "x" * 2_000, "notes": ["n" * 400] * 80}] * 5))
    assert len(r.previous) == merlin.MAX_ROUNDS - 1
    assert len(r.previous[0]["say"]) == merlin.MAX_SAY and len(r.previous[0]["notes"]) == merlin.MAX_NOTES
    assert len(r.previous[0]["notes"][0]) == merlin.MAX_NOTE


# ── the edits ────────────────────────────────────────────────────────────────

def _objects(node):
    if isinstance(node, dict):
        if node.get("type") == "object":
            yield node
        for v in node.values():
            yield from _objects(v)
    elif isinstance(node, list):
        for v in node:
            yield from _objects(v)


def test_the_reply_schema_has_no_optional_fields():
    # Structured outputs refuse a schema with more than 24 optional fields
    # (checked 2026-10-27); this one has none, so any edit kind can be added.
    objects = list(_objects(merlin.REPLY_SCHEMA))
    assert len(objects) > 5
    for obj in objects:
        assert obj["additionalProperties"] is False
        assert sorted(obj["required"]) == sorted(obj["properties"]), obj["required"]
    edits = {e["properties"]["op"]["enum"][0] for e in merlin.REPLY_SCHEMA["properties"]["ops"]["items"]["anyOf"]}
    assert edits == set(merlin.OPS)


def test_an_edit_in_the_replys_shape_is_flattened_and_cleaned():
    ops, dropped = merlin.clean_ops([
        {"op": "type", "id": "t6", "paras": [], "fields": [{"name": "size", "value": 90}, {"name": "font", "value": "Bebas Neue"}]},
        {"op": "add", "kind": "rect", "to": "back", "text": "", "role": "",
         "fields": [{"name": "x", "value": 0}, {"name": "y", "value": 0}, {"name": "w", "value": 612},
                    {"name": "h", "value": 792}, {"name": "fill", "value": "#F4EFE6"}]},
        {"op": "add", "kind": "text", "to": "front", "text": "FASHION", "role": "h3",
         "fields": [{"name": "x", "value": 36}, {"name": "y", "value": 40}, {"name": "w", "value": 200},
                    {"name": "h", "value": 20}, {"name": "size", "value": 11}, {"name": "id", "value": "t1"}]},
        {"op": "set", "id": "r1", "fields": [{"name": "stroke", "value": None}, {"name": "stroke", "value": {"c": "#000000", "w": 1}}]},
    ])
    assert dropped == 0
    assert ops[0] == {"op": "type", "id": "t6", "font": "Bebas Neue", "size": 90}
    assert ops[1] == {"op": "add", "kind": "rect", "x": 0, "y": 0, "w": 612, "h": 792, "fill": "#f4efe6", "to": "back"}
    assert ops[2]["type"] == {"size": 11} and ops[2]["text"] == "FASHION" and "id" not in ops[2]
    assert ops[3] == {"op": "set", "id": "r1", "stroke": None}  # the first of a field named twice

def test_a_set_keeps_known_fields_cleaned_to_the_documents_limits():
    op = merlin.clean_op({"op": "set", "id": "t1", "x": 12.346, "y": -50_000, "w": "wide", "rot": 400,
                          "opacity": 55.6, "fill": "#AABBCC", "stroke": {"c": "#112233", "w": 500},
                          "cols": 30, "valign": "middle", "hidden": "yes", "asset_id": "x", "locked": False})
    assert op == {"op": "set", "id": "t1", "x": 12.35, "y": -20_000, "rot": 180, "opacity": 56, "fill": "#aabbcc",
                  "stroke": {"c": "#112233", "w": 144}, "cols": 12}


def test_fill_and_stroke_can_be_taken_away():
    assert merlin.clean_op({"op": "set", "id": "r1", "fill": None, "stroke": None}) == {
        "op": "set", "id": "r1", "fill": None, "stroke": None}
    assert merlin.clean_op({"op": "set", "id": "r1", "stroke": {"c": "red", "w": 1}}) is None


def test_type_takes_fonts_the_studio_has_and_weights_by_the_hundred():
    op = merlin.clean_op({"op": "type", "id": "t1", "paras": [2, 0, 0, -1, "1", True], "font": "Bebas Neue",
                          "wt": 650, "it": True, "size": 2_000, "track": -900, "align": "c", "lead": 80, "dc": 9})
    assert op == {"op": "type", "id": "t1", "paras": [0, 2], "font": "Bebas Neue", "wt": 700, "it": True,
                  "size": 1296, "track": -500, "align": "c", "lead": 80, "dc": 6}
    assert merlin.clean_op({"op": "type", "id": "t1", "font": "Helvetica Neue"}) is None
    assert merlin.clean_op({"op": "type", "id": "t1"}) is None


def test_case_and_arrange_take_only_their_choices():
    assert merlin.clean_op({"op": "case", "id": "t1", "to": "upper"}) == {"op": "case", "id": "t1", "to": "upper"}
    assert merlin.clean_op({"op": "case", "id": "t1", "to": "shout"}) is None
    assert merlin.clean_op({"op": "arrange", "id": "r1", "to": "back"}) == {"op": "arrange", "id": "r1", "to": "back"}
    assert merlin.clean_op({"op": "arrange", "id": "r1", "to": "under"}) is None


@pytest.mark.parametrize("raw", [
    {"op": "delete", "id": "t1"},
    {"op": "set", "id": "T 1", "x": 3},
    {"op": "set", "id": "t1"},
    "set t1",
    {"op": "add", "kind": "image", "x": 0, "y": 0, "w": 10, "h": 10},
    {"op": "add", "kind": "rect", "x": 0, "y": 0, "w": 10},
    {"op": "add", "kind": "text", "x": 0, "y": 0, "w": 10, "h": 10, "text": "Body", "role": "p"},
    {"op": "add", "kind": "text", "x": 0, "y": 0, "w": 10, "h": 10, "text": "A quote", "role": "quote"},
    {"op": "add", "kind": "text", "x": 0, "y": 0, "w": 10, "h": 10, "text": "  ", "role": "h3"},
])
def test_edits_merlin_cant_make_are_left_out(raw):
    assert merlin.clean_op(raw) is None


def test_an_added_label_is_short_and_a_heading_or_caption():
    op = merlin.clean_op({"op": "add", "kind": "text", "x": 54, "y": 40, "w": 200, "h": 20, "to": "back",
                          "text": "FASHION\nWEEK " + "x" * 100, "role": "h3", "font": "Bebas Neue", "size": 11,
                          "fill": "#000000", "cols": 2})
    assert op["text"].startswith("FASHION WEEK x") and len(op["text"]) == merlin.MAX_LABEL
    assert op["role"] == "h3" and op["type"] == {"font": "Bebas Neue", "size": 11} and op["to"] == "back"
    assert op["fill"] == "#000000" and op["cols"] == 2 and (op["x"], op["y"], op["w"], op["h"]) == (54, 40, 200, 20)
    shape = merlin.clean_op({"op": "add", "kind": "rect", "x": 0, "y": 0, "w": 612, "h": 792, "fill": "#f4efe6"})
    assert shape == {"op": "add", "kind": "rect", "x": 0, "y": 0, "w": 612, "h": 792, "fill": "#f4efe6"}


def test_at_most_forty_edits_and_eight_additions_a_round():
    add = {"op": "add", "kind": "rect", "x": 0, "y": 0, "w": 10, "h": 10}
    ops, dropped = merlin.clean_ops([add] * 10 + [{"op": "set", "id": "t1", "x": 1}] * 40 + ["junk"])
    assert sum(op["op"] == "add" for op in ops) == merlin.MAX_ADDS and len(ops) == merlin.MAX_OPS
    assert dropped == 2 + 8 + 1  # two additions, eight edits past forty, one that isn't an edit
    assert merlin.clean_ops("not a list") == ([], 0)


def test_a_reply_keeps_its_good_edits_and_counts_the_rest(claude):
    claude.reply = {"say": "Bigger headline.", "done": False,
                    "ops": [{"op": "type", "id": "t1", "size": 72}, {"op": "delete", "id": "i2"}]}
    out = run(merlin.design(merlin.request(_raw())))
    assert out == {"say": "Bigger headline.", "ops": [{"op": "type", "id": "t1", "size": 72}], "done": False,
                   "dropped": 1}


def test_a_reply_with_no_edits_is_done(claude):
    claude.reply = {"say": "It already matches.", "ops": [], "done": False}
    assert run(merlin.design(merlin.request(_raw())))["done"] is True


@pytest.mark.parametrize("reply", [
    "not json at all",
    {"say": "", "ops": [{"op": "delete", "id": "t1"}]},
    RuntimeError("api down"),
    TimeoutError(),
])
def test_an_unusable_reply_is_a_failure(claude, reply):
    claude.reply = reply
    with pytest.raises(merlin.MerlinFailed):
        run(merlin.design(merlin.request(_raw())))


def test_the_daily_rounds():
    assert merlin.daily_rounds({"magazine": True}) == merlin.MAGAZINE_RUNS_PER_DAY * merlin.MAX_ROUNDS == 60
    assert merlin.daily_rounds({}) == merlin.FREE_RUNS_PER_DAY * merlin.MAX_ROUNDS == 9


# ── over HTTP ────────────────────────────────────────────────────────────────

@pytest.fixture
def wired(monkeypatch):
    state = SimpleNamespace(open=0, limits=[], features={"magazine": True}, rounds=[],
                            conn=_owner_conn(fetchval={"SELECT format FROM cappe_posts": "pages"}),
                            answer={"say": "Done.", "ops": [{"op": "set", "id": "t1", "x": 5}], "done": True,
                                    "dropped": 0})

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

    async def design(r):
        assert state.open == 0, "Claude must not design while a connection is held"
        state.rounds.append(r)
        if isinstance(state.answer, Exception):
            raise state.answer
        return state.answer

    monkeypatch.setattr(studio_mod, "get_connection", lambda: Ctx())
    monkeypatch.setattr(studio_mod, "check_rate_limit", limit)
    monkeypatch.setattr(studio_mod, "resolve_entitlements", entitlements)
    monkeypatch.setattr(merlin, "design", design)
    return state


def _post(body):
    with route_client(studio_mod.router, overrides={studio_mod.require_cappe_account: ACCOUNT}) as client:
        return client.post(f"/sites/{SITE}/studio/stories/{POST}/merlin", json=body)


def test_a_round_is_designed_and_spends_one_of_the_days_rounds(wired):
    res = _post(_raw(round=2, selected=1, previous=[{"say": "First pass.", "notes": ["Did: x"], "did": 3, "skipped": 1}],
                     picture={"media_type": "image/png", "data": _picture()},
                     current={"media_type": "image/jpeg", "data": _picture("JPEG")}))
    assert res.status_code == 200 and res.json() == wired.answer
    assert wired.limits == [(str(ACCOUNT.id), "cappe_studio_merlin", 60, 86_400)]
    r = wired.rounds[0]
    assert r.round == 2 and r.page == PAGE and r.selected == 1
    assert r.previous == [{"say": "First pass.", "notes": ["Did: x"], "did": 3, "skipped": 1}]
    assert r.picture["source"]["media_type"] == "image/png" and r.current["source"]["media_type"] == "image/jpeg"


def test_without_magazines_there_are_three_designs_a_day(wired):
    wired.features = {}
    assert _post(_raw()).status_code == 200
    assert wired.limits[0][2] == 9


@pytest.mark.parametrize("fmt, code", [(None, 404), ("blocks", 409)])
def test_only_a_paged_story_can_be_designed(wired, fmt, code):
    wired.conn.set("fetchval", "SELECT format FROM cappe_posts", fmt)
    assert _post(_raw()).status_code == code
    assert wired.limits == [] and wired.rounds == []


@pytest.mark.parametrize("over", [
    {"request": ""},
    {"request": "x" * 1_001},
    {"round": 4},
    {"previous": [{"say": "x", "notes": []}] * 3},
    {"previous": [{"say": "x", "notes": ["n" * 301]}]},
    {"previous": [{"say": "x", "notes": [], "did": -1}]},
    {"selected": -1},
    {"page": "x" * 16_001},
    {"picture": {"media_type": "image/gif", "data": "R0lG"}},
    {"current": {"media_type": "image/png", "data": base64.b64encode(b"hello").decode()}},
])
def test_requests_out_of_bounds_spend_nothing(wired, over):
    assert _post(_raw(**over)).status_code == 422
    assert wired.limits == [] and wired.rounds == []


@pytest.mark.parametrize("error, code, says", [
    (merlin.MerlinUnavailable(), 503, merlin.UNAVAILABLE),
    (merlin.MerlinFailed("x"), 502, merlin.FAILED),
])
def test_failures_say_what_to_do(wired, error, code, says):
    wired.answer = error
    res = _post(_raw())
    assert res.status_code == code and res.json()["detail"] == says
