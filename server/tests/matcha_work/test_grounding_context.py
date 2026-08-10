"""Pure-function tests for the Prop grounding-context assembler (no DB/Gemini).

    cd server && ./venv/bin/python -m pytest tests/matcha_work/test_grounding_context.py -q
"""

from app.matcha.services.matcha_work.element_repo_service import (
    assemble_context,
    query_terms,
    rank_relevant_files,
)


def test_includes_small_files_whole():
    files = [("a.py", "print(1)"), ("b/c.py", "x = 2")]
    text, manifest = assemble_context(files, char_budget=10_000)
    assert "=== FILE: a.py ===" in text
    assert "print(1)" in text
    assert "=== FILE: b/c.py ===" in text
    assert manifest["included"] == ["a.py", "b/c.py"]
    assert manifest["truncated"] == []
    assert manifest["omitted"] == []


def test_truncates_when_over_budget():
    big = "x" * 5000
    text, manifest = assemble_context([("big.py", big)], char_budget=1000)
    assert "…(truncated)…" in text
    assert manifest["truncated"] == ["big.py"]
    assert len(text) <= 1100  # roughly within budget + header/footer slack


def test_omits_files_once_budget_exhausted():
    files = [("first.py", "y" * 900), ("second.py", "z" * 900)]
    text, manifest = assemble_context(files, char_budget=1000)
    # first consumes the budget; second has no meaningful room left
    assert "first.py" in (manifest["included"] + manifest["truncated"])
    assert manifest["omitted"] == ["second.py"]
    assert "=== FILE: second.py ===" not in text


def test_empty():
    text, manifest = assemble_context([], char_budget=1000)
    assert text == ""
    assert manifest == {"included": [], "truncated": [], "omitted": []}


def test_query_terms_removes_filler_and_adds_singulars():
    terms = query_terms("Add capability for sellers to edit existing products")
    assert "seller" in terms
    assert "product" in terms
    assert "existing" not in terms


def test_repo_retrieval_prioritizes_matching_paths():
    files = [
        ("docs/product-notes.md", "general notes"),
        ("server/app/products/routes.py", "def update_product(): pass"),
        ("server/app/users/routes.py", "a product appears once"),
    ]
    ranked = rank_relevant_files(files, "let sellers edit products")
    assert ranked[0][0] == "server/app/products/routes.py"
