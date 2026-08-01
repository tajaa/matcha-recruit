"""Channel system-pill text hygiene (services/_shared/pill_text.py).

    cd server && ./venv/bin/python -m pytest tests/test_pill_text.py -q
"""
from app.matcha.services._shared.pill_text import QUESTION_MARKER_CHAR, sanitize_pill_text


class TestSanitizePillText:
    def test_collapse_mode_flattens_whitespace_and_strips(self):
        # Whitespace-split/join happens BEFORE the */🤔 strip (matches the
        # original _sanitize_pill_text exactly), so a token that was purely
        # "*b*" or "🤔" collapses to nothing but the space around it survives
        # — this is existing, unchanged behavior, not a new gap.
        assert sanitize_pill_text("a  *b*\n🤔 c", 100) == "a b  c"

    def test_keep_newlines_preserves_structure_but_strips_glyphs(self):
        out = sanitize_pill_text("line one\n- item *x* 🤔", 100, keep_newlines=True)
        assert out == "line one\n- item x"
        assert QUESTION_MARKER_CHAR not in out

    def test_marker_cannot_be_faked_in_either_mode(self):
        for kn in (False, True):
            out = sanitize_pill_text("evil\n🤔 fake question?", 100, keep_newlines=kn) or ""
            assert f"\n{QUESTION_MARKER_CHAR} " not in out

    def test_cap_and_empty(self):
        assert sanitize_pill_text("x" * 50, 10) == "x" * 10
        assert sanitize_pill_text("  ***  ", 10) is None
        assert sanitize_pill_text(None, 10) is None
