"""Regression test for the ER Copilot document-excerpt builder.

A single PDF containing multiple interviews used to be truncated with a
head+tail slice (text[:1000] + "..." + text[-1000:]), which silently deleted
the middle interview. _build_document_excerpts uses linear truncation under a
generous budget, so every section survives.
"""

from app.matcha.routes.er_copilot import (
    ER_DOC_PER_DOC_CHAR_CAP,
    _build_document_excerpts,
)


def _three_interview_doc() -> str:
    block = "x" * 1500  # each section comfortably exceeds the old 2000-char total
    return (
        f"=== INTERVIEW 1 ===\n{block}\n"
        f"=== INTERVIEW 2 ===\n{block}\n"
        f"=== INTERVIEW 3 ===\n{block}\n"
    )


def test_all_interviews_survive_truncation():
    rows = [
        {
            "filename": "interviews.pdf",
            "document_type": "transcript",
            "scrubbed_text": _three_interview_doc(),
        }
    ]
    out = _build_document_excerpts(rows, text_key="scrubbed_text")

    # The old head+tail slice would drop the middle interview.
    assert "INTERVIEW 1" in out
    assert "INTERVIEW 2" in out
    assert "INTERVIEW 3" in out


def test_skips_empty_and_null_text():
    rows = [
        {"filename": "a.txt", "document_type": "transcript", "scrubbed_text": None},
        {"filename": "b.txt", "document_type": "transcript", "scrubbed_text": "   "},
        {"filename": "c.txt", "document_type": "transcript", "scrubbed_text": "real content"},
    ]
    out = _build_document_excerpts(rows, text_key="scrubbed_text")

    assert "c.txt" in out and "real content" in out
    assert "a.txt" not in out
    assert "b.txt" not in out


def test_null_document_type_falls_back_to_other():
    rows = [{"filename": "a.txt", "document_type": None, "scrubbed_text": "hello"}]
    out = _build_document_excerpts(rows, text_key="scrubbed_text")

    assert "(other)" in out


def test_per_doc_cap_marks_truncation():
    rows = [
        {
            "filename": "big.txt",
            "document_type": "transcript",
            "scrubbed_text": "y" * (ER_DOC_PER_DOC_CHAR_CAP + 5000),
        }
    ]
    out = _build_document_excerpts(rows, text_key="scrubbed_text")

    assert f"[truncated after {ER_DOC_PER_DOC_CHAR_CAP} chars]" in out


def test_total_cap_omits_later_docs():
    big = "z" * ER_DOC_PER_DOC_CHAR_CAP
    rows = [
        {"filename": f"doc{i}.txt", "document_type": "transcript", "scrubbed_text": big}
        for i in range(8)  # 8 * 100k = 800k > 600k total cap
    ]
    out = _build_document_excerpts(rows, text_key="scrubbed_text")

    assert "[omitted, prompt size cap reached]" in out
