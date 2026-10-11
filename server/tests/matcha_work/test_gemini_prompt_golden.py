"""The Gemini skill-engine prompt is frozen while the Claude path is reshaped
around it.

`_build_prompt_and_contents` was refactored into shared parts so the Claude
layout (`_claude_thread.py`) can arrange the same pieces for prompt caching.
Gemini must not notice: these fingerprints were taken from the code before
the refactor, over the system prompt halves, the windowed contents, the
valid update fields and the inferred skill.

    cd server && ./venv/bin/python -m pytest tests/matcha_work/test_gemini_prompt_golden.py -q

A deliberate change to a Gemini prompt updates the hash it changes, in the
same commit, with the reason.
"""
import pytest

from app.config import load_settings
from app.matcha.services.matcha_work.matcha_work_ai import GeminiProvider, provider as provider_module
from tests.matcha_work import _gemini_prompt_scenarios as scenarios

GOLDEN = {
    "plain": "8de2e5dc00f2d28f2643caf1b7577cfddefb23100e2f4f3d761c42aec4318357",
    "summary_dyn_hr": "cc1c94deb8c752ee72178ffdc15dd1731e808aa850389a740d9177357ece3921",
    "offer": "8b6529d8b456b905a3ddc638fc490dd98dce2447966c4000f8f62e3130ee0474",
    "slide": "0f430e0ec5fafffaae080abe07978f92bc28319a8e9607df61c6a2f60143572e",
    "recruiting": "2100118526fa6338e1755acbb86f4bda4b9ccd88e643800f817710f2f2452f46",
    "blog": "8961a68551b3c2b0c81fef8a871caf14f12cfbc38c3925f28b91fc979e3eb523",
    "long_window": "e268bd6438c2b1a1600654b3c3362e63152c9cd2422705781e9134b5fc95ff09",
}


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_gemini_prompt_is_byte_identical_to_before_the_claude_rework(name, monkeypatch):
    load_settings()
    monkeypatch.setattr(provider_module, "date", scenarios.FixedDate)
    provider = GeminiProvider.__new__(GeminiProvider)
    out = provider._build_prompt_and_contents(**scenarios.scenarios()[name])
    assert scenarios.fingerprint(out) == GOLDEN[name]
