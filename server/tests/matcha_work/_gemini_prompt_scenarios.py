"""Gemini prompt scenarios shared by the golden generator and the test."""
import hashlib
import json
from datetime import date as _real_date


class FixedDate:
    @staticmethod
    def today():
        return _real_date(2026, 10, 11)


def scenarios():
    slides = [{"title": "Intro", "bullets": ["a"]}, {"title": "Plan", "bullets": ["b", "c"]}]
    long_history = []
    for i in range(25):
        long_history.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"message {i}"})
    long_history[-1] = {"role": "user", "content": "latest question",
                        "image_parts": [(b"\x89PNG-bytes", "image/png")]}
    return {
        "plain": dict(messages=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "Hello!"},
                                {"role": "user", "content": "what is FLSA?"}],
                      current_state={}, company_context="COMPANY CTX"),
        "summary_dyn_hr": dict(messages=[{"role": "user", "content": "write him up"}], current_state={},
                               company_context="CTX2", context_summary="Earlier: we discussed Bob.",
                               dynamic_context="=== NODE ===\nnode data\n\n=== RELEVANT REGULATIONS ===\nrag",
                               hr_pilot_mode=True),
        "offer": dict(messages=[{"role": "user", "content": "draft an offer"}],
                      current_state={"skill": "offer_letter", "candidate_name": "Ana", "salary": 120000},
                      company_context="CTX3"),
        "slide": dict(messages=[{"role": "user", "content": "make slide 2 punchier"}],
                      current_state={"skill": "presentation", "slides": slides}, company_context="",
                      slide_index=1),
        "recruiting": dict(messages=[{"role": "user", "content": "update the posting"}],
                           current_state={"skill": "project", "posting": {"finalized": True},
                                          "candidates": [{"name": "x"}, {"name": "y"}]},
                           company_context="CTX4"),
        "blog": dict(messages=[{"role": "user", "content": "draft the intro"}], current_state={},
                     company_context="CTX5", blog_mode_state='{"title": "T"}', context_summary="S",
                     dynamic_context="DYN"),
        "long_window": dict(messages=long_history, current_state={}, company_context="CTX6"),
    }


def fingerprint(out):
    static, dynamic, contents, valid_fields, skill = out
    parts = []
    for c in contents:
        for p in c.parts:
            if p.text is not None:
                parts.append((c.role, "text", p.text))
            elif p.inline_data is not None:
                parts.append((c.role, p.inline_data.mime_type, hashlib.sha256(p.inline_data.data).hexdigest()))
    blob = json.dumps([static, dynamic, parts, list(valid_fields), skill], ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()
