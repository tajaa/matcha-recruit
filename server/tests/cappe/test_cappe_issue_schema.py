"""An issue's cover and contents as stored (services/magazine/issue_schema.py)."""
import copy
import os
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test")

from app.cappe.services.magazine import issue_schema as schema  # noqa: E402
from app.cappe.services.magazine.issue_schema import IssueError, normalize_contents, normalize_cover  # noqa: E402

VOCAB = Path(__file__).resolve().parents[3] / "client/src/cappe/magazine/issues/coverVocab.ts"


def test_an_empty_cover_is_the_classic_starting_point():
    cover = normalize_cover(None)
    assert cover["template"] == "classic" and cover["background"] == "#1b1916" and cover["lines"] == []
    assert cover["photo"] == {"asset_id": None, "focal": {"x": 50, "y": 50}, "zoom": 100, "filter": "none"}
    assert cover["masthead"]["case"] == "upper" and cover["masthead"]["weight"] == "black"
    assert cover["issue_line"]["text"] == "" and cover["issue_line"]["hidden"] is False
    assert cover["credit"] == {"corner": "br", "tone": "light"}


def test_values_are_clamped_and_unknown_keys_dropped():
    asset = uuid4()
    cover = normalize_cover({
        "template": "nope", "background": "red", "junk": 1,
        "photo": {"asset_id": str(asset), "focal": {"x": 140, "y": -3}, "zoom": 900, "filter": "glow", "url": "x"},
        "scrim": {"kind": "sideways", "strength": 400},
        "masthead": {"x": 99, "y": 120, "w": 3, "size": 99, "color": "#ABCDEF", "align": "justify", "font": "comic"},
        "lines": [{"text": "  A line  ", "x": "12.36", "size": "nan", "weight": "thin", "case": "lower",
                   "tracking": "huge", "box": "outline", "box_color": "accent", "color": "accent", "onclick": "x"}],
        "credit": {"corner": "middle", "tone": "loud"},
    })
    assert "junk" not in cover and cover["template"] == "classic" and cover["background"] == "#1b1916"
    assert cover["photo"] == {"asset_id": str(asset), "focal": {"x": 100, "y": 0}, "zoom": 250, "filter": "none"}
    assert cover["scrim"] == {"kind": "none", "strength": 90}
    mast = cover["masthead"]
    # The box is at least 10% wide and never runs off the right edge.
    assert mast["w"] == 10.0 and mast["x"] == 90.0 and mast["y"] == 100.0 and mast["size"] == 30.0
    assert mast["color"] == "#abcdef" and mast["align"] == "center" and mast["font"] == "heading"
    line = cover["lines"][0]
    assert line["text"] == "A line" and line["x"] == 12.4 and line["size"] == 6.0
    assert (line["weight"], line["case"], line["tracking"], line["box"]) == ("bold", "asis", "normal", "none")
    assert line["color"] == "accent" and line["box_color"] == "accent" and "onclick" not in line
    assert cover["credit"] == {"corner": "br", "tone": "light"}


def test_numbers_round_half_up_to_one_decimal():
    assert schema._num(4.25, 0, 100, 0) == 4.3 and schema._num(4.24, 0, 100, 0) == 4.2
    assert schema._num(None, 0, 100, 7) == 7 and schema._num(float("nan"), 0, 100, 7) == 7


def test_lines_are_capped_and_empty_ones_dropped():
    lines = [{"text": f"Line {i}"} for i in range(12)] + [{"text": "  ", "sub": ""}, "junk"]
    cover = normalize_cover({"lines": [{"text": ""}, *lines]})
    assert [ln["text"] for ln in cover["lines"]] == [f"Line {i}" for i in range(schema.MAX_LINES)]
    assert normalize_cover({"lines": [{"sub": "Only a sub"}]})["lines"][0]["text"] == ""
    assert len(normalize_cover({"lines": [{"text": "x" * 400, "sub": "y" * 400}]})["lines"][0]["text"]) == 140


def test_a_cover_line_links_only_to_a_story_in_the_issue():
    inside, outside = str(uuid4()), str(uuid4())
    raw = {"lines": [{"text": "In", "post_id": inside}, {"text": "Out", "post_id": outside}, {"text": "Bad", "post_id": "x"}]}
    cover = normalize_cover(raw, story_ids={inside})
    assert [ln["post_id"] for ln in cover["lines"]] == [inside, None, None]
    # Without the issue's stories the links are kept as given (well formed only).
    assert [ln["post_id"] for ln in normalize_cover(raw)["lines"]] == [inside, outside, None]


def test_the_cover_picture_must_be_a_library_id():
    with pytest.raises(IssueError, match="library"):
        normalize_cover({"photo": {"asset_id": "https://example.com/a.jpg"}})
    assert schema.cover_asset_ids(normalize_cover({})) == []
    asset = str(uuid4())
    assert schema.cover_asset_ids(normalize_cover({"photo": {"asset_id": asset}})) == [asset]


def test_a_cover_too_large_to_store_is_refused(monkeypatch):
    monkeypatch.setattr(schema, "MAX_COVER_BYTES", 500)
    with pytest.raises(IssueError, match="too much"):
        normalize_cover({"lines": [{"text": "A" * 140, "sub": "B" * 200}]})


def test_contents_defaults_and_flags():
    assert normalize_contents(None) == {"v": 1, "layout": "list", "heading": "In this issue", "show_numbers": True,
                                        "show_pictures": True, "show_deks": True, "show_bylines": False,
                                        "accent": "accent"}
    contents = normalize_contents({"layout": "grid", "heading": "", "show_numbers": 0, "show_bylines": "yes",
                                   "accent": "#00FF00", "junk": 1})
    assert contents["layout"] == "grid" and contents["heading"] == "" and contents["show_numbers"] is False
    assert contents["show_bylines"] is True and contents["accent"] == "#00ff00" and "junk" not in contents
    assert normalize_contents({"layout": "magazine"})["layout"] == "list"


def test_sections_and_contents_lines_are_trimmed_or_none():
    assert schema.section_name("  Features ") == "Features" and schema.section_name("  ") is None
    assert schema.section_name("x" * 90) == "x" * 40
    assert schema.contents_line(None) is None and len(schema.contents_line("y" * 300)) == 200


def test_the_issue_line_says_the_number_and_month_unless_written():
    cover = normalize_cover({})
    assert schema.issue_line_text(cover, 3, datetime(2026, 10, 21)) == "No. 3 · October 2026"
    assert schema.issue_line_text({**cover, "issue_line": {"text": "Autumn"}}, 3, None) == "Autumn"
    now = datetime.now()
    assert schema.issue_line_text(cover, 1, None).endswith(f"{now.year}")


def test_each_template_is_a_whole_cover_with_its_slots_inside_the_artboard():
    assert set(schema.TEMPLATES) == set(schema.TEMPLATE_COVERS) == {"classic", "headline", "minimal", "boxed", "poster"}
    for key, cover in schema.TEMPLATE_COVERS.items():
        assert cover["template"] == key and cover["lines"], key
        for ln in cover["lines"]:
            assert ln["text"] == "" and 0 <= ln["x"] and ln["x"] + ln["w"] <= 100 and 0 <= ln["y"] <= 100
        # With words in its slots, a template is stored exactly as it is offered.
        filled = copy.deepcopy(cover)
        for ln in filled["lines"]:
            ln["text"] = "Words"
        assert normalize_cover(filled) == filled, key


def test_a_new_cover_fits_the_magazines_name_on_one_line():
    short, long = schema.starter_cover("classic", "Vogue"), schema.starter_cover("classic", "The Machine")
    assert short["masthead"]["size"] == 16.0  # the template's own size
    assert long["masthead"]["size"] == pytest.approx(92 / (11 * schema.MASTHEAD_EM), abs=0.1)
    assert schema.starter_cover("poster", "x" * 200)["masthead"]["size"] == schema.MIN_SIZE
    assert short["lines"] == [{**schema.TEMPLATE_COVERS["classic"]["lines"][0], "text": "Your cover line"}]
    assert schema.starter_cover("nope")["template"] == "classic"


def _ts_list(name: str) -> list[str]:
    match = re.search(rf"export const {name}\s*=\s*\[([^\]]*)\]", VOCAB.read_text())
    assert match, name
    return re.findall(r"'([^']+)'", match.group(1))


def _ts_number(name: str) -> float:
    match = re.search(rf"export const {name}\s*=\s*([0-9.]+)", VOCAB.read_text())
    assert match, name
    return float(match.group(1))


def test_the_editor_offers_exactly_these_choices():
    """client/src/cappe/magazine/issues/coverVocab.ts mirrors these lists."""
    for ts, values in (("FILTERS", schema.FILTERS), ("SCRIMS", schema.SCRIMS), ("ALIGNS", schema.ALIGNS),
                       ("WEIGHTS", schema.WEIGHTS), ("CASES", schema.CASES), ("TRACKINGS", schema.TRACKINGS),
                       ("FONTS", schema.FONTS), ("BOXES", schema.BOXES), ("CREDIT_CORNERS", schema.CREDIT_CORNERS),
                       ("TONES", schema.TONES), ("CONTENTS_LAYOUTS", schema.CONTENTS_LAYOUTS)):
        assert _ts_list(ts) == list(values), ts
    for ts, value in (("MAX_LINES", schema.MAX_LINES), ("MAX_STORIES", schema.MAX_STORIES),
                      ("MIN_SIZE", schema.MIN_SIZE), ("MAX_SIZE", schema.MAX_SIZE), ("MIN_WIDTH", schema.MIN_WIDTH),
                      ("ZOOM_MIN", schema.ZOOM_MIN), ("ZOOM_MAX", schema.ZOOM_MAX),
                      ("MASTHEAD_EM", schema.MASTHEAD_EM)):
        assert _ts_number(ts) == value, ts
