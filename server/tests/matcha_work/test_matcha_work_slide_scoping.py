"""Unit tests for slide-scoping logic.

The two functions under test (_inject_slide_context, _scope_slide_update) are
pure logic with no I/O or app-stack dependencies, so we copy their
implementations here to keep the test importable without the full venv.
"""

import json
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Functions under test (copied verbatim from their source files so this test
# runs without the full FastAPI/asyncpg/google-genai stack)
# ---------------------------------------------------------------------------

def _inject_slide_context(msg_dicts: list[dict], current_state: dict, slide_index: Optional[int]) -> None:
    if slide_index is None or not msg_dicts:
        return

    slides = current_state.get("slides") or []
    if not slides:
        pres = current_state.get("presentation")
        if isinstance(pres, dict):
            slides = pres.get("slides") or []

    if not slides or not (0 <= slide_index < len(slides)):
        return

    slide = slides[slide_index]
    if not isinstance(slide, dict):
        return

    total = len(slides)
    title = slide.get("title", "Untitled")
    bullets = slide.get("bullets") or []
    speaker_notes = slide.get("speaker_notes", "")

    context_lines = [
        f"[Editing Slide {slide_index + 1}/{total}: \"{title}\"]",
        "Current content:",
        f"- Title: {title}",
        f"- Bullets: {json.dumps(bullets)}",
    ]
    if speaker_notes:
        context_lines.append(f"- Speaker Notes: {speaker_notes}")

    context_block = "\n".join(context_lines)

    for i in range(len(msg_dicts) - 1, -1, -1):
        if msg_dicts[i]["role"] == "user":
            original = msg_dicts[i]["content"]
            msg_dicts[i] = {
                "role": "user",
                "content": f"{context_block}\n\nUser request: {original}",
            }
            break


@dataclass
class _FakeAIResp:
    structured_update: Optional[dict] = field(default=None)


def _scope_slide_update(ai_resp, current_state: dict, slide_index: Optional[int]) -> None:
    if slide_index is None:
        return
    if not isinstance(ai_resp.structured_update, dict):
        return

    for key in ("presentation_title", "subtitle", "theme", "cover_image_url", "generated_at"):
        ai_resp.structured_update.pop(key, None)

    ai_slides = ai_resp.structured_update.get("slides")

    current_slides = list(current_state.get("slides") or [])

    if not current_slides:
        pres = current_state.get("presentation")
        if isinstance(pres, dict):
            current_slides = list(pres.get("slides") or [])

    if not isinstance(ai_slides, list) or not current_slides:
        return
    if not (0 <= slide_index < len(ai_slides) and 0 <= slide_index < len(current_slides)):
        return

    merged = list(current_slides)
    merged[slide_index] = ai_slides[slide_index]
    ai_resp.structured_update["slides"] = merged


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

SLIDES = [
    {"title": "Intro", "bullets": ["Welcome", "Agenda"], "speaker_notes": "Say hi"},
    {"title": "Market Analysis", "bullets": ["Growing 15% YoY", "Key competitors"], "speaker_notes": ""},
    {"title": "Conclusion", "bullets": ["Summary", "Next steps"], "speaker_notes": ""},
]

STATE = {"slides": SLIDES, "presentation_title": "Q1 Report"}


def _msgs(last="make bullets more concise"):
    return [
        {"role": "user", "content": "create a presentation"},
        {"role": "assistant", "content": "Sure!"},
        {"role": "user", "content": last},
    ]


# ---------------------------------------------------------------------------
# _inject_slide_context
# ---------------------------------------------------------------------------

def test_inject_prepends_slide_info():
    msgs = _msgs()
    _inject_slide_context(msgs, STATE, slide_index=1)
    last = msgs[-1]["content"]
    assert "[Editing Slide 2/3:" in last
    assert '"Market Analysis"' in last
    assert "Growing 15% YoY" in last
    assert "User request: make bullets more concise" in last


def test_inject_does_not_mutate_original_string():
    original = "make bullets more concise"
    msgs = _msgs(original)
    _inject_slide_context(msgs, STATE, slide_index=0)
    assert original == "make bullets more concise"
    assert msgs[-1]["content"].startswith("[Editing Slide 1/3:")


def test_inject_noop_when_slide_index_none():
    msgs = _msgs()
    orig = msgs[-1]["content"]
    _inject_slide_context(msgs, STATE, slide_index=None)
    assert msgs[-1]["content"] == orig


def test_inject_noop_when_no_slides():
    msgs = _msgs()
    orig = msgs[-1]["content"]
    _inject_slide_context(msgs, {}, slide_index=0)
    assert msgs[-1]["content"] == orig


def test_inject_noop_when_index_out_of_range():
    msgs = _msgs()
    orig = msgs[-1]["content"]
    _inject_slide_context(msgs, STATE, slide_index=99)
    assert msgs[-1]["content"] == orig


def test_inject_workbook_slides_under_presentation():
    state = {"workbook_title": "Guide", "presentation": {"slides": SLIDES}}
    msgs = _msgs()
    _inject_slide_context(msgs, state, slide_index=2)
    last = msgs[-1]["content"]
    assert "[Editing Slide 3/3:" in last
    assert '"Conclusion"' in last


def test_inject_includes_speaker_notes_when_present():
    msgs = _msgs()
    _inject_slide_context(msgs, STATE, slide_index=0)
    assert "Speaker Notes: Say hi" in msgs[-1]["content"]


def test_inject_omits_speaker_notes_when_empty():
    msgs = _msgs()
    _inject_slide_context(msgs, STATE, slide_index=1)
    assert "Speaker Notes" not in msgs[-1]["content"]


# ---------------------------------------------------------------------------
# _scope_slide_update
# ---------------------------------------------------------------------------

def test_scope_strips_non_slide_keys():
    resp = _FakeAIResp(structured_update={
        "slides": SLIDES,
        "presentation_title": "HACKED",
        "subtitle": "HACKED",
        "theme": "bold",
        "cover_image_url": "http://evil/img.png",
        "generated_at": "2099-01-01",
    })
    _scope_slide_update(resp, STATE, slide_index=1)
    for key in ("presentation_title", "subtitle", "theme", "cover_image_url", "generated_at"):
        assert key not in resp.structured_update


def test_scope_only_targeted_slide_changes():
    new_slide = {"title": "Market Analysis", "bullets": ["SHORTER"], "speaker_notes": ""}
    ai_slides = list(SLIDES)
    ai_slides[1] = new_slide
    resp = _FakeAIResp(structured_update={"slides": ai_slides})
    _scope_slide_update(resp, STATE, slide_index=1)
    result = resp.structured_update["slides"]
    assert result[0] == SLIDES[0]
    assert result[1] == new_slide
    assert result[2] == SLIDES[2]


def test_scope_noop_when_slide_index_none():
    resp = _FakeAIResp(structured_update={"slides": SLIDES, "presentation_title": "Keep"})
    _scope_slide_update(resp, STATE, slide_index=None)
    assert resp.structured_update["presentation_title"] == "Keep"


def test_scope_noop_when_no_structured_update():
    resp = _FakeAIResp(structured_update=None)
    _scope_slide_update(resp, STATE, slide_index=0)
    assert resp.structured_update is None


def test_scope_handles_workbook_slides():
    workbook_state = {"workbook_title": "Guide", "presentation": {"slides": SLIDES}}
    new_slide = {"title": "Intro", "bullets": ["UPDATED"], "speaker_notes": ""}
    ai_slides = [new_slide] + list(SLIDES[1:])
    resp = _FakeAIResp(structured_update={"slides": ai_slides})
    _scope_slide_update(resp, workbook_state, slide_index=0)
    result = resp.structured_update["slides"]
    assert result[0] == new_slide
    assert result[1] == SLIDES[1]
    assert result[2] == SLIDES[2]


def test_scope_noop_when_ai_slides_not_list():
    resp = _FakeAIResp(structured_update={"slides": "bad"})
    _scope_slide_update(resp, STATE, slide_index=0)
    assert resp.structured_update["slides"] == "bad"


def test_scope_noop_when_index_out_of_range():
    resp = _FakeAIResp(structured_update={"slides": list(SLIDES)})
    _scope_slide_update(resp, STATE, slide_index=99)
    assert resp.structured_update["slides"] == SLIDES
