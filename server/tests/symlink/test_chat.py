"""Pure-logic tests for the sym-link chat engine.

`coerce_fields` / `is_complete` / `missing_items` / `build_prompt` never touch
Gemini. `next_turn` is exercised with a monkeypatched client on the DEFINING
module (`app.matcha.services.symlink.chat`), per server/CLAUDE.md.
"""
import asyncio
import json

import pytest

from app.matcha.models.symlink import SpecAttachmentOverride, SpecFieldOverride, SpecOverrides
from app.matcha.services.symlink import chat
from app.matcha.services.symlink.kinds import materialize_spec

CRED = materialize_spec("credential_upload")
REVIEW = materialize_spec("manager_review")


def test_coerce_drops_unknown_keys_and_enforces_max_len():
    merged = chat.coerce_fields(
        {"credential_name": "  RN   license ", "hacker": "x", "notes": "n" * 9000},
        {},
        CRED,
    )
    assert merged["credential_name"] == "RN license"
    assert "hacker" not in merged
    assert len(merged["notes"]) == 4000
    assert set(merged) == {f["key"] for f in CRED["fields"]}


def test_coerce_never_blanks_a_known_value():
    known = {"credential_name": "RN license", "expires_on": "2027-03"}
    merged = chat.coerce_fields({"credential_name": None, "expires_on": "   "}, known, CRED)
    assert merged["credential_name"] == "RN license"
    assert merged["expires_on"] == "2027-03"
    merged = chat.coerce_fields({"expires_on": "March 2027"}, known, CRED)
    assert merged["expires_on"] == "March 2027"


def test_coerce_choice_matches_case_insensitively_and_by_unique_substring():
    assert chat.coerce_fields({"overall_rating": "meets expectations"}, {}, REVIEW)["overall_rating"] == "Meets expectations"
    assert chat.coerce_fields({"overall_rating": "needs"}, {}, REVIEW)["overall_rating"] == "Needs improvement"
    # "expectations" matches two choices → ambiguous → ignored
    assert chat.coerce_fields({"overall_rating": "expectations"}, {}, REVIEW)["overall_rating"] is None
    assert chat.coerce_fields({"overall_rating": "amazing"}, {}, REVIEW)["overall_rating"] is None


def test_coerce_number_field():
    spec = materialize_spec(
        "custom",
        SpecOverrides(goal="count", fields=[SpecFieldOverride(key="headcount", label="Headcount", type="number")]),
    )
    assert chat.coerce_fields({"headcount": "1,250"}, {}, spec)["headcount"] == 1250
    assert chat.coerce_fields({"headcount": "12.5"}, {}, spec)["headcount"] == 12.5
    assert chat.coerce_fields({"headcount": "lots"}, {}, spec)["headcount"] is None
    assert chat.coerce_fields({"headcount": True}, {}, spec)["headcount"] is None


def test_completion_is_deterministic_over_required_fields_and_attachments():
    fields = {
        "credential_name": "RN license",
        "expires_on": "2027-03-01",
    }
    # Required fields filled, required attachment missing → not complete.
    assert not chat.is_complete(fields, [], CRED)
    missing = chat.missing_items(fields, [], CRED)
    assert missing == [{"kind": "attachment", "key": "document", "label": "A clear photo or PDF of the document"}]
    # Attachment present → complete; optional fields irrelevant.
    assert chat.is_complete(fields, ["document"], CRED)
    # Drop a required field → incomplete again.
    assert not chat.is_complete({"credential_name": "x"}, ["document"], CRED)


def test_optional_attachment_does_not_block_completion():
    spec = materialize_spec(
        "custom",
        SpecOverrides(
            goal="g",
            fields=[SpecFieldOverride(key="answer", label="Answer")],
            attachments=[SpecAttachmentOverride(slot="photo", label="Photo", required=False)],
        ),
    )
    assert chat.is_complete({"answer": "yes"}, [], spec)


def test_prompt_lists_every_required_label_attachment_state_and_instructions():
    prompt = chat.build_prompt(
        CRED,
        [{"role": "assistant", "content": "Hi"}, {"role": "user", "content": "It's my RN license"}],
        {"credential_name": "RN license"},
        ["document"],
        company_name="Po Coffee Co",
        instructions="Please use the front side only.",
    )
    for f in CRED["fields"]:
        assert f["label"] in prompt
    assert "document: A clear photo or PDF of the document (required) — UPLOADED" in prompt
    assert "Po Coffee Co" in prompt
    assert "Please use the front side only." in prompt
    assert "Recipient: It's my RN license" in prompt
    assert '"credential_name": <value or null>' in prompt
    assert "Expiry date (field)" in prompt  # still missing
    assert "Credential name (field)" not in prompt  # already known


def test_prompt_trims_long_transcripts_to_the_tail():
    transcript = [{"role": "user", "content": f"msg{i}"} for i in range(100)]
    prompt = chat.build_prompt(CRED, transcript, {}, [])
    assert "msg99" in prompt
    assert "msg0\n" not in prompt


class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, text=None, exc=None):
        self._text = text
        self._exc = exc

    async def generate_content(self, **kwargs):
        if self._exc:
            raise self._exc
        return _FakeResponse(self._text)


class _FakeClient:
    def __init__(self, models):
        self.aio = type("Aio", (), {"models": models})()


def test_next_turn_merges_model_output_and_decides_completion(monkeypatch):
    payload = json.dumps({
        "assistant_message": "Great — when does it expire?",
        "credential_name": "RN license",
        "expires_on": None,
    })
    monkeypatch.setattr(chat, "genai_env_client", lambda: _FakeClient(_FakeModels(text=payload)))
    result = asyncio.run(chat.next_turn([{"role": "user", "content": "my RN license"}], {}, CRED, []))
    assert result["error"] is False
    assert result["assistant_message"] == "Great — when does it expire?"
    assert result["fields"]["credential_name"] == "RN license"
    assert result["complete"] is False

    payload2 = json.dumps({"assistant_message": "All set.", "expires_on": "2027-03"})
    monkeypatch.setattr(chat, "genai_env_client", lambda: _FakeClient(_FakeModels(text=payload2)))
    result2 = asyncio.run(chat.next_turn([], result["fields"], CRED, ["document"]))
    assert result2["complete"] is True
    assert result2["fields"]["credential_name"] == "RN license"


def test_next_turn_never_raises_and_keeps_known_fields_on_failure(monkeypatch):
    monkeypatch.setattr(chat, "genai_env_client", lambda: _FakeClient(_FakeModels(exc=RuntimeError("boom"))))
    known = {"credential_name": "RN license"}
    result = asyncio.run(chat.next_turn([], known, CRED, []))
    assert result["error"] is True
    assert result["fields"]["credential_name"] == "RN license"
    assert result["assistant_message"] == chat.FALLBACK_ERROR_MESSAGE


def test_next_turn_tolerates_garbage_json(monkeypatch):
    monkeypatch.setattr(chat, "genai_env_client", lambda: _FakeClient(_FakeModels(text="not json")))
    result = asyncio.run(chat.next_turn([], {}, CRED, []))
    assert result["error"] is True


@pytest.mark.parametrize("text", ['{"assistant_message": ""}', '{"assistant_message": null}', "[]"])
def test_next_turn_falls_back_to_got_it_on_empty_message(monkeypatch, text):
    monkeypatch.setattr(chat, "genai_env_client", lambda: _FakeClient(_FakeModels(text=text)))
    result = asyncio.run(chat.next_turn([], {}, CRED, []))
    assert result["error"] is False
    assert result["assistant_message"] == "Got it."
