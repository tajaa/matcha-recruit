"""The Studio's Picture Editor on the server (routes/pictures.py,
services/magazine/studio/recipe.py, edits.py, models.py; migration cappemag10).

What each block pins:

  * a recipe keeps known keys only, clamped, rounded and without defaults, the
    same way the Studio does (`fixtures/picture_recipe_cases.json`, which the
    client's test reads: rewrite it with `PICTURE_FIXTURES=write`); its crop
    gives the edited picture's size;
  * an edit prints its source's credit, "(adapted)" for CC BY / BY-SA, "AI
    illustration" for AI;
  * an upload is taken as an edit only when it is that picture edited (its
    size, and where its detail falls, inside what a cut-out keeps);
  * the routes: the source's own pixels for its owner, never cached; an edit
    becomes a new library picture with the source's provenance and the recipe,
    and the source as its parent; the model files only from the manifest, with
    their own bytes.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_studio_pictures.py -q
"""
import hashlib
import io
import json
import os
import random
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from PIL import Image, ImageDraw, ImageOps

from app.cappe.routes import pictures as pictures_mod
from app.cappe.services import media
from app.cappe.services.magazine.studio import edits, models
from app.cappe.services.magazine.studio.recipe import cover_scale, normalize_recipe, output_size
from tests._helpers.routes import route_client
from tests.cappe.test_cappe_magazine_routes import ACCOUNT, ASSET, ASSET_ROW, NOW, SITE, SITE_ROW, Conn, Ctx

FIXTURE = Path(__file__).parent / "fixtures" / "picture_recipe_cases.json"

CASES = [
    ("not a recipe", "nope"),
    ("as it was", {}),
    ("sliders clamped, rounded, defaults dropped", {
        "exposure": 1.23456, "contrast": 250, "highlights": -40.6, "shadows": 0, "whites": "12", "blacks": True,
        "temp": None, "tint": -101, "vibrance": 33.4, "saturation": -0.4, "clarity": 10, "sharpen": -5,
        "vignette": -30, "grain": 140, "fade": 12.5, "sh_hue": 400, "sh_amt": 20, "hi_hue": 30, "hi_amt": 0}),
    ("a look, black and white, unknown keys", {"look": "noir", "bw": True, "hdr": 50, "lut": "x"}),
    ("an unknown look, a truthy bw", {"look": "acid", "bw": "yes"}),
    ("a crop", {"crop": {"x": 0.1, "y": 0.2, "w": 0.5, "h": 0.6, "angle": 3.14159, "turn": 90, "flip_h": True}}),
    ("a crop off the picture is moved back on", {"crop": {"x": 0.9, "y": 0.95, "w": 0.5, "h": 0.3}}),
    ("a crop too small, turned too far, a bad turn", {"crop": {"w": 0.001, "h": 2, "angle": -80, "turn": 45}}),
    ("the whole picture is no crop", {"crop": {"x": 0, "y": 0, "w": 1, "h": 1, "angle": 0, "turn": 0}}),
    ("a flip alone is a crop", {"crop": {"flip_v": True}}),
    ("a cut-out", {"cutout": {"points": [{"x": 0.48, "y": 0.42, "keep": True}, {"x": 0.2, "y": 0.9, "keep": False},
                                         {"x": "a", "y": 0.1}, {"x": 1.5, "y": -1}, "nope"],
                              "feather": 140, "invert": True}}),
    ("a cut-out with nothing kept is none", {"cutout": {"points": [{"x": 0.5, "y": 0.5, "keep": False}]}}),
    ("too many points", {"cutout": {"points": [{"x": k / 40, "y": 0.5} for k in range(40)]}}),
]


def test_recipes_are_cleaned_as_the_studio_cleans_them():
    got = [{"name": name, "raw": raw, "clean": normalize_recipe(raw)} for name, raw in CASES]
    if os.environ.get("PICTURE_FIXTURES") == "write":
        FIXTURE.write_text(json.dumps(got, indent=1) + "\n")
    want = json.loads(FIXTURE.read_text())
    assert [(c["name"], c["clean"]) for c in got] == [(c["name"], c["clean"]) for c in want]
    by = {c["name"]: c["clean"] for c in got}
    assert by["as it was"] == {} and by["not a recipe"] == {}
    assert by["sliders clamped, rounded, defaults dropped"]["exposure"] == 1.23
    assert by["a crop off the picture is moved back on"]["crop"]["x"] == 0.5
    assert len(by["too many points"]["cutout"]["points"]) == 32
    assert normalize_recipe({"temp": float("nan"), "tint": float("inf")}) == {}


def test_a_crop_sets_the_edits_size():
    assert output_size(3000, 2000, {}) == (3000, 2000)
    assert output_size(3000, 2000, normalize_recipe({"crop": {"w": 0.5, "h": 0.25}})) == (1500, 500)
    assert output_size(3000, 2000, normalize_recipe({"crop": {"turn": 90, "w": 0.5, "h": 0.5}})) == (1000, 1500)
    assert cover_scale(100, 100, 0) == 1 and round(cover_scale(100, 100, 45), 4) == round(2 ** 0.5, 4)


@pytest.mark.parametrize("source, credit", [
    ({"credit_line": "Photo: Ana Ruiz", "license": "by"}, "Photo: Ana Ruiz (adapted)"),
    ({"credit_line": "Ana Ruiz / CC BY-SA 4.0", "license": "by-sa"}, "Ana Ruiz / CC BY-SA 4.0 (adapted)"),
    ({"credit_line": "Ana Ruiz (adapted)", "license": "by"}, "Ana Ruiz (adapted)"),
    ({"credit_line": "NASA", "license": "pdm"}, "NASA"),
    ({"credit_line": "Haley", "license": "own"}, "Haley"),
    ({"credit_line": "Mine", "license": "ai", "ai_generated": True}, "AI illustration"),
    ({"credit_line": None, "license": "by"}, None),
])
def test_an_edit_prints_its_sources_credit(source, credit):
    assert edits.credit_for(source) == credit


# ── is it the picture? ───────────────────────────────────────────────────────

def _picture(seed=0, size=(400, 300)) -> Image.Image:
    img = Image.new("RGB", size, (200, 120, 40))
    d = ImageDraw.Draw(img)
    for k in range(6):
        x = (k * 67 + seed * 131) % size[0]
        d.rectangle((x, 20 + k * 30, x + 50 + seed * 7, 120 + k * 25), fill=(20 + k * 30, 30, 90))
    d.ellipse((150 + seed * 40, 60, 260 + seed * 40, 260), fill=(250, 250, 230))
    return img


def _bytes(img: Image.Image, fmt="PNG") -> bytes:
    out = io.BytesIO()
    img.save(out, fmt)
    return out.getvalue()


def test_an_edit_of_the_picture_is_taken_and_another_picture_isnt():
    src = _bytes(_picture())
    # A look (black and white, more contrast), and a crop of the left half turned a quarter.
    noir = ImageOps.autocontrast(ImageOps.grayscale(_picture()), cutoff=5)
    assert edits.looks_like(src, _bytes(noir), {})
    turned = _picture().rotate(-90, expand=True).crop((0, 0, 300, 200))
    assert edits.looks_like(src, _bytes(turned), normalize_recipe({"crop": {"turn": 90, "w": 1, "h": 0.5}}))
    straightened = edits._reference(_picture(), normalize_recipe({"crop": {"angle": 8}}), (400, 300))
    assert edits.looks_like(src, _bytes(straightened.convert("RGB")), normalize_recipe({"crop": {"angle": 8}}))
    assert not edits.looks_like(src, _bytes(_picture(seed=3)), {})  # another picture
    assert not edits.looks_like(src, _bytes(ImageOps.invert(_picture())), {})  # its negative isn't an edit we make


def test_a_picture_shown_almost_opaque_is_still_compared():
    src = _bytes(_picture())

    def faded(img):
        img = img.convert("RGBA")
        img.putalpha(249)  # 97.6% opaque: no pixel reaches the cut-out's "kept"
        return _bytes(img)

    assert not edits.looks_like(src, faded(_picture(seed=3)), {})
    assert edits.looks_like(src, faded(_picture()), {})
    # One opaque pixel doesn't make the rest of it a sliver.
    other = _picture(seed=3).convert("RGBA")
    other.putalpha(249)
    other.putpixel((5, 5), (0, 0, 0, 255))
    assert not edits.looks_like(src, _bytes(other), {})


def test_straightening_a_long_thin_picture_is_compared_at_its_own_small_size():
    # Grown to cover its box, this 3200×1 picture turned 45° would be 7 million
    # pixels by 2,263: the reference is drawn at the size compared instead.
    thin = Image.new("L", (3200, 1), 128)
    recipe = normalize_recipe({"crop": {"angle": 45}})
    ref = edits._reference(thin, recipe, (256, 1))
    assert ref.size == (256, 1)


def test_the_reference_is_the_studios_turn_flip_straighten_and_crop():
    # Drawn by one affine map, it matches the picture actually turned, grown
    # and cut (the old way) on an ordinary picture.
    pic = _picture()
    for crop in ({"angle": 12, "x": 0.1, "y": 0.2, "w": 0.6, "h": 0.5}, {"angle": -30, "turn": 90, "flip_h": True},
                 {"angle": 5, "turn": 270, "flip_v": True, "x": 0.3, "w": 0.5}):
        recipe = normalize_recipe({"crop": crop})
        c = recipe["crop"]
        img = ImageOps.exif_transpose(pic).convert("L")
        img = img.rotate(-c["turn"], expand=True) if c["turn"] else img
        img = ImageOps.mirror(img) if c["flip_h"] else img
        img = ImageOps.flip(img) if c["flip_v"] else img
        w, h = img.size
        k = cover_scale(w, h, c["angle"])
        img = img.resize((round(w * k), round(h * k))).rotate(-c["angle"], resample=Image.BILINEAR)
        dx, dy = (img.width - w) / 2, (img.height - h) / 2
        img = img.crop((dx, dy, dx + w, dy + h))
        img = img.crop((c["x"] * w, c["y"] * h, (c["x"] + c["w"]) * w, (c["y"] + c["h"]) * h)).resize((120, 90))
        got = edits._reference(pic, recipe, (120, 90))
        a, b = list(img.tobytes()), list(got.tobytes())
        ma, mb = sum(a) / len(a), sum(b) / len(b)
        cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        assert cov / (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5 > 0.95, crop


def test_a_cut_out_is_compared_where_it_is_kept():
    keep = _picture().convert("RGBA")
    mask = Image.new("L", keep.size, 0)
    ImageDraw.Draw(mask).rectangle((100, 0, 300, 300), fill=255)
    keep.putalpha(mask)
    recipe = normalize_recipe({"cutout": {"points": [{"x": 0.5, "y": 0.5}]}})
    assert edits.looks_like(_bytes(_picture()), _bytes(keep), recipe)
    other = _picture(seed=3).convert("RGBA")
    other.putalpha(mask)
    assert not edits.looks_like(_bytes(_picture()), _bytes(other), recipe)
    # An inverted cut-out keeps the rest, and is compared there.
    inverted = normalize_recipe({"cutout": {"points": [{"x": 0.5, "y": 0.5}], "invert": True}})
    hole = ImageOps.invert(mask)
    rest, other_rest = _picture().convert("RGBA"), _picture(seed=3).convert("RGBA")
    rest.putalpha(hole)
    other_rest.putalpha(hole)
    assert edits.looks_like(_bytes(_picture()), _bytes(rest), inverted)
    assert not edits.looks_like(_bytes(_picture()), _bytes(other_rest), inverted)
    # Nothing visible to borrow a credit for (flat, all cut away): taken.
    assert edits.looks_like(_bytes(_picture()), _bytes(Image.new("RGB", (400, 300), "white")), {})
    assert edits.looks_like(_bytes(_picture()), _bytes(Image.new("RGBA", (400, 300))), recipe)


def _tower(seed=0, tower=True) -> Image.Image:
    """A textured sunset with a thin, windowed tower up the middle."""
    rnd = random.Random(seed)
    img = Image.new("RGB", (400, 600), (240, 150, 60))
    d = ImageDraw.Draw(img)
    for _ in range(400):
        x, y, r, c = rnd.randrange(400), rnd.randrange(600), rnd.randrange(3, 14), rnd.randrange(40, 250)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(c, c // 2 + 40, 60))
    if tower:
        d.rectangle((185, 120, 215, 560), fill=(170, 160, 150))
        for k in range(30):
            y = 130 + k * 14
            d.rectangle((190, y, 196, y + 6), fill=(30, 30, 40))
            d.rectangle((204, y + 4, 210, y + 10), fill=(60, 50, 40))
    return img


def _cut(img: Image.Image, box) -> Image.Image:
    """Cut out as a browser saves it: transparent pixels are black."""
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rectangle(box, fill=255)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img.convert("RGBA"), mask=mask)
    return out


def test_a_thin_cut_out_with_a_look_and_a_crop_is_taken():
    # The Campanile case: a look, the tower cut out of its sky, cropped 4:5.
    # Compared small and whole, the tower was a few cells darkened by the
    # transparent black around it, and a real edit was refused.
    recipe = normalize_recipe({"crop": {"y": 0.0833, "h": 0.8333}, "cutout": {"points": [{"x": 0.5, "y": 0.5}]}})
    graded = _tower().point(lambda v: round(255 * (v / 255) ** 0.6))
    edit = _cut(graded, (185, 120, 215, 560)).crop((0, 50, 400, 550))
    assert edits.looks_like(_bytes(_tower()), _bytes(edit), recipe)
    # Another sunset, cut the same way, isn't it.
    forged = _cut(_tower(seed=7, tower=False), (185, 120, 215, 560)).crop((0, 50, 400, 550))
    assert not edits.looks_like(_bytes(_tower()), _bytes(forged), recipe)


def test_the_size_must_be_the_recipes():
    src = {"width": 400, "height": 300}
    assert edits.size_matches(src, 400, 300, {}) and edits.size_matches(src, 402, 299, {})
    assert not edits.size_matches(src, 410, 300, {})
    assert edits.size_matches(src, 150, 200, normalize_recipe({"crop": {"turn": 270, "w": 0.5, "h": 0.5}}))
    assert edits.size_matches({"width": None, "height": None}, 9, 9, {})


# ── routes ───────────────────────────────────────────────────────────────────

SOURCE = {**ASSET_ROW, "width": 400, "height": 300, "mime": "image/png", "title": "Low tide", "license": "by",
          "credit_line": "Photo: Ana Ruiz", "source": "openverse", "source_id": "ov-1", "creator": "Ana Ruiz",
          "rights_attested_at": NOW, "parent_asset_id": None, "recipe": None, "adapted": False}


def _client(monkeypatch, conn, *, original: bytes = b"", stored=None):
    monkeypatch.setattr(pictures_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(pictures_mod, "check_rate_limit", AsyncMock())
    storage = AsyncMock()
    storage.download_file.return_value = original
    monkeypatch.setattr(pictures_mod, "get_storage", lambda: storage)
    monkeypatch.setattr(pictures_mod.media, "store_processed", AsyncMock(return_value=stored or media.StoredImage(
        url="https://cdn.example.test/e.png", mime="image/png", width=400, height=300, bytes=10, variants={})))
    return route_client(pictures_mod.router, overrides={pictures_mod.require_cappe_account: ACCOUNT})


def _conn(source=SOURCE, inserted=None):
    return Conn(fetchrow={"FROM cappe_sites": SITE_ROW, "FROM cappe_assets WHERE id = $1": source,
                          "INSERT INTO cappe_assets": inserted or {**SOURCE, "id": uuid4(), "kind": "edit"}})


def test_the_owner_gets_the_pictures_own_pixels_never_cached(monkeypatch):
    with _client(monkeypatch, _conn(), original=b"PNG BYTES") as client:
        res = client.get(f"/sites/{SITE}/assets/{ASSET}/pixels")
    assert res.status_code == 200 and res.content == b"PNG BYTES"
    assert res.headers["content-type"] == "image/png" and res.headers["cache-control"] == "private, no-store"
    with _client(monkeypatch, _conn(source=None)) as client:
        assert client.get(f"/sites/{SITE}/assets/{uuid4()}/pixels").status_code == 404


def test_pixels_that_cant_be_read_say_so(monkeypatch):
    with _client(monkeypatch, _conn()) as client:
        pictures_mod.get_storage().download_file.side_effect = RuntimeError("S3 down")
        assert client.get(f"/sites/{SITE}/assets/{ASSET}/pixels").status_code == 502


def _post(client, data: bytes, recipe=None, mime="image/png"):
    return client.post(f"/sites/{SITE}/assets/{ASSET}/edit", files={"file": ("e.png", data, mime)},
                       data={"recipe": json.dumps(recipe or {}) if not isinstance(recipe, str) else recipe})


def test_an_edit_becomes_a_new_library_picture(monkeypatch):
    conn = _conn()
    noir = ImageOps.grayscale(_picture()).convert("RGB")
    with _client(monkeypatch, conn, original=_bytes(_picture())) as client:
        res = _post(client, _bytes(noir), {"look": "noir", "bw": True, "contrast": 40, "bogus": 1})
    assert res.status_code == 201, res.text
    assert res.json()["kind"] == "edit"
    args = conn.args_for("INSERT INTO cappe_assets")
    sql = conn.sql_for("fetchrow")[-1]
    assert "'edit'" in sql and "adapted" in sql
    assert args[2] == "https://cdn.example.test/e.png"
    assert args[3:6] == ("openverse", "ov-1", SOURCE["source_url"])
    assert args[6] == "Low tide (edited)" and args[7] == "Ana Ruiz" and args[9] == "by"
    assert args[13] == "Photo: Ana Ruiz (adapted)"  # its credit
    assert args[23] == ASSET  # the source is its parent
    assert json.loads(args[24]) == {"look": "noir", "bw": True, "contrast": 40}


def _animated(*frames) -> bytes:
    out = io.BytesIO()
    frames[0].save(out, "PNG", save_all=True, append_images=list(frames[1:]))
    return out.getvalue()


@pytest.mark.parametrize("data, recipe, mime, code, says", [
    (b"", "{not json", "image/png", 422, "isn't JSON"),
    (b"GIF89a", {}, "image/gif", 400, "Unsupported"),
    ("small", {}, "image/png", 422, "isn't that picture"),
    ("other", {}, "image/png", 422, "isn't that picture"),
    # The source first and another picture after: only one frame is compared.
    ("animated", {}, "image/png", 400, "one still image"),
    ("huge", {}, "image/png", 400, "too large"),
])
def test_an_upload_that_isnt_the_picture_edited_is_refused(monkeypatch, data, recipe, mime, code, says):
    conn = _conn()
    body = {"small": _bytes(_picture().resize((200, 150))), "other": _bytes(_picture(seed=3)),
            "animated": _animated(_picture(), _picture(seed=3)),
            "huge": _bytes(Image.new("L", (10_000, 8_000)))}.get(data, data)
    with _client(monkeypatch, conn, original=_bytes(_picture())) as client:
        res = _post(client, body, recipe, mime)
    assert res.status_code == code and says in res.text
    assert not any("INSERT INTO cappe_assets" in s for s in conn.sql_for("fetchrow"))


def test_an_old_source_without_its_size_is_measured_before_it_is_compared(monkeypatch):
    # Its row has no size: the source's own header gives it, so the edit is
    # still held to the recipe's size, and a huge source is refused undecoded.
    old = {**SOURCE, "width": None, "height": None}
    with _client(monkeypatch, _conn(source=old), original=_bytes(_picture())) as client:
        assert _post(client, _bytes(_picture().resize((200, 150)))).status_code == 422
    with _client(monkeypatch, _conn(source=old), original=_bytes(Image.new("L", (10_000, 8_000)))) as client:
        res = _post(client, _bytes(_picture()))
    assert res.status_code == 400 and "too large" in res.text


def test_an_edit_needs_the_owners_picture(monkeypatch):
    with _client(monkeypatch, _conn(source=None)) as client:
        assert _post(client, _bytes(_picture())).status_code == 404


def test_not_a_picture(monkeypatch):
    monkeypatch.setattr(pictures_mod.upload_guard, "verify_upload", lambda data, ct, allowed: ct)
    with _client(monkeypatch, _conn(), original=_bytes(_picture())) as client:
        assert _post(client, b"\x89PNG not really").status_code == 400


# ── models ───────────────────────────────────────────────────────────────────

MODEL = b"onnx bytes"
MODEL_SHA = hashlib.sha256(MODEL).hexdigest()


@pytest.fixture
def one_model(monkeypatch, tmp_path):
    (tmp_path / f"{MODEL_SHA}.onnx").write_bytes(MODEL)
    (tmp_path / f"{'b' * 64}.onnx").write_bytes(b"other bytes")
    monkeypatch.setenv("CAPPE_MODELS_DIR", str(tmp_path))
    files = {"encoder": {"path": "e.onnx", "sha": MODEL_SHA, "bytes": len(MODEL)},
             "decoder": {"path": "d.onnx", "sha": "b" * 64, "bytes": 11}}
    monkeypatch.setattr(models, "manifest", lambda: {"models": {"segment": {"files": files}}})
    monkeypatch.setattr(models, "_cache", {})
    storage = AsyncMock()
    storage.get_key.return_value = None
    monkeypatch.setattr(models, "get_storage", lambda: storage)
    return storage


def test_a_model_is_served_from_the_manifest_with_its_own_bytes(one_model, monkeypatch):
    with route_client(pictures_mod.router, overrides={pictures_mod.require_cappe_account: ACCOUNT}) as client:
        res = client.get(f"/studio/models/{MODEL_SHA}.onnx")
        assert res.status_code == 200 and res.content == MODEL
        assert res.headers["cache-control"] == "private, max-age=31536000, immutable"
        assert client.get(f"/studio/models/{'c' * 64}.onnx").status_code == 404  # not in the manifest
        assert client.get(f"/studio/models/{'b' * 64}.onnx").status_code == 404  # not its sha's bytes
        assert client.get("/studio/models/manifest.json").json()["models"]["segment"]["files"]["encoder"]["sha"] == MODEL_SHA
        monkeypatch.delenv("CAPPE_MODELS_DIR")
        monkeypatch.setattr(models, "_cache", {})
        assert client.get(f"/studio/models/{MODEL_SHA}.onnx").status_code == 404  # not uploaded
        one_model.get_key.return_value = MODEL
        assert client.get(f"/studio/models/{MODEL_SHA}.onnx").status_code == 200  # from storage
    assert one_model.get_key.call_args.args[0] == f"cappe/models/{MODEL_SHA}.onnx"


def test_the_committed_manifest_pins_a_licence_and_revision():
    models.manifest.cache_clear()
    seg = models.manifest()["models"]["segment"]
    assert seg["licence"] == "Apache-2.0" and len(seg["revision"]) == 40
    assert {f["sha"] for f in seg["files"].values()} == {
        "cce23c7b2e5d4f330932738fb67ba518e04b0d99ccdd1cccd22a7da4e01f2971",
        "cb90b279f549d2cab7fd6e20c38522438c65d84bdcca3d2a764cff7d857fdce2"}
    assert models.by_sha("cce23c7b2e5d4f330932738fb67ba518e04b0d99ccdd1cccd22a7da4e01f2971")["bytes"] == 8882165
