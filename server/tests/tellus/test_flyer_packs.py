"""Cross-surface parity checks for the Tell-Us designer asset packs."""
import json
import pathlib
import re

from app.tellus.services.flyer_ai import catalog, palettes


ROOT = pathlib.Path(__file__).resolve().parents[3]
WEB = ROOT / "client" / "tellus" / "public" / "designer"
IOS = ROOT / "platforms" / "ios" / "TellUs" / "Resources" / "FlyerDesigner"
TOKEN_KEYS = set(catalog.PALETTE_TOKENS)
HEX = re.compile(r"^#[0-9a-fA-F]{3,6}$")


def _load(path: pathlib.Path):
    return json.loads(path.read_text())


def test_every_template_index_entry_has_a_file():
    for root in (WEB, IOS):
        for entry in _load(root / "templates" / "index.json"):
            assert (root / "templates" / entry["file"]).is_file()


def test_ios_and_web_template_packs_match():
    web_index = _load(WEB / "templates" / "index.json")
    ios_index = _load(IOS / "templates" / "index.json")
    assert web_index == ios_index
    for entry in web_index:
        assert _load(WEB / "templates" / entry["file"]) == _load(IOS / "templates" / entry["file"])


def test_themed_templates_declare_known_palette_and_only_tokens():
    for entry in _load(WEB / "templates" / "index.json"):
        if entry["theme"] is None:
            continue
        design = _load(WEB / "templates" / entry["file"])
        assert set(design["palette"]) == TOKEN_KEYS
        assert design["palette"] in [preset.colors for preset in palettes.PALETTES]
        for layer in design["layers"]:
            for key in ("fill", "stroke", "fg", "bg"):
                if key in layer:
                    assert not HEX.match(layer[key])


def test_every_template_layer_is_inside_the_artboard():
    for entry in _load(WEB / "templates" / "index.json"):
        if entry["theme"] is None:
            continue
        design = _load(WEB / "templates" / entry["file"])
        width, height = design["artboard"]["w"], design["artboard"]["h"]
        for layer in design["layers"]:
            layer_width = layer.get("size", layer.get("width", 0))
            layer_height = layer.get("size", layer.get("height", 0))
            assert 0 <= layer["x"] <= width
            assert 0 <= layer["y"] <= height
            assert layer["x"] + layer_width <= width
            assert layer["y"] + layer_height <= height


def test_template_stickers_are_in_the_catalog():
    for entry in _load(WEB / "templates" / "index.json"):
        design = _load(WEB / "templates" / entry["file"])
        assert all(
            (layer["assetId"] if layer["assetId"].endswith(".svg") else f'{layer["assetId"]}.svg') in catalog.STICKER_IDS
            for layer in design["layers"] if layer["type"] == "sticker"
        )


def test_palette_ink_paper_contrast_is_legible():
    for preset in palettes.PALETTES:
        assert catalog.contrast_ratio(preset.colors["ink"], preset.colors["paper"]) >= 4.5
