"""Image processing for Cappe uploads and the magazine library (services/media.py).

What each block pins:

  * a stored image carries no EXIF — a phone photo's GPS position never
    reaches the CDN — and is turned the right way up first;
  * the library's responsive sizes: the standard widths below the image's own,
    never an upscale, plus one JPEG for email and link previews;
  * what is refused (not an image, a decompression bomb) and what passes
    through (an animated GIF), and an animated WebP losing its EXIF too;
  * the stored copy is capped at MAX_SIDE;
  * `store_processed` uploads every size and reports them in order.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_media.py -q
"""
import asyncio
import io
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from PIL import Image, ImageCms  # noqa: E402

from app.cappe.services import media  # noqa: E402

GPS_IFD = 0x8825
ORIENTATION = 0x0112


def _exif_with_gps(orientation: int | None = None) -> Image.Exif:
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"
    exif[0x0110] = "Phone 15"
    if orientation:
        exif[ORIENTATION] = orientation
    gps = exif.get_ifd(GPS_IFD)
    gps[1] = "N"
    gps[2] = (37.0, 46.0, 30.0)
    gps[3] = "W"
    gps[4] = (122.0, 25.0, 9.0)
    return exif


def _jpeg(size=(64, 32), *, exif: Image.Exif | None = None, color=(200, 30, 30)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "JPEG", exif=exif.tobytes() if exif else b"")
    return out.getvalue()


def _has_gps(data: bytes) -> bool:
    with Image.open(io.BytesIO(data)) as img:
        return bool(img.getexif().get_ifd(GPS_IFD))


def test_a_jpeg_loses_its_gps_and_every_other_exif_field():
    source = _jpeg(exif=_exif_with_gps())
    assert _has_gps(source)  # the fixture really carries a position

    out = media.process_image(source, "image/jpeg")

    assert out.mime == "image/jpeg"
    assert not _has_gps(out.data)
    with Image.open(io.BytesIO(out.data)) as img:
        assert dict(img.getexif()) == {}
        assert "exif" not in img.info
    assert b"PhoneMaker" not in out.data


def test_the_picture_is_turned_upright_before_the_orientation_tag_is_dropped():
    # Orientation 6: the camera was held sideways; the pixels are 64x32 but
    # the photo is 32 wide and 64 tall.
    out = media.process_image(_jpeg((64, 32), exif=_exif_with_gps(orientation=6)), "image/jpeg")
    assert (out.width, out.height) == (32, 64)
    with Image.open(io.BytesIO(out.data)) as img:
        assert img.size == (32, 64)
        assert ORIENTATION not in img.getexif()


def test_a_webp_loses_its_exif_too():
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "blue").save(buf, "WEBP", exif=_exif_with_gps().tobytes())
    assert _has_gps(buf.getvalue())
    out = media.process_image(buf.getvalue(), "image/webp")
    assert out.mime == "image/webp"
    assert not _has_gps(out.data)


def test_a_png_keeps_its_transparency_and_a_still_gif_becomes_a_png():
    buf = io.BytesIO()
    Image.new("RGBA", (20, 20), (0, 0, 0, 0)).save(buf, "PNG")
    out = media.process_image(buf.getvalue(), "image/png")
    assert out.mime == "image/png"
    with Image.open(io.BytesIO(out.data)) as img:
        assert img.mode == "RGBA"
        assert img.getpixel((0, 0))[3] == 0

    gif = io.BytesIO()
    Image.new("P", (10, 10)).save(gif, "GIF")
    still = media.process_image(gif.getvalue(), "image/gif")
    assert still.mime == "image/png"
    assert still.ext == ".png"


def test_an_animated_gif_is_stored_as_it_came():
    frames = [Image.new("RGB", (10, 10), c).convert("P") for c in ("red", "green", "blue")]
    buf = io.BytesIO()
    frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:], duration=50, loop=0)
    out = media.process_image(buf.getvalue(), "image/gif", derivatives=True)
    assert out.data == buf.getvalue()  # nothing to cut: the frames are the same bytes
    assert out.webp == () and out.share is None


def _gif_with_metadata() -> tuple[bytes, bytes]:
    """A two-frame GIF, and the same GIF carrying a comment, an XMP packet
    with a GPS position, and bytes after its trailer."""
    frames = [Image.new("RGB", (10, 10), c).convert("P") for c in ("red", "green")]
    buf = io.BytesIO()
    frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:], duration=50, loop=0)
    clean = buf.getvalue()
    xmp = b'<x:xmpmeta><exif:GPSLatitude>37,46.5N</exif:GPSLatitude></x:xmpmeta>'
    xmp_ext = b"\x21\xff\x0bXMP DataXMP" + b"".join(
        bytes([len(xmp[i:i + 255])]) + xmp[i:i + 255] for i in range(0, len(xmp), 255)) + b"\x00"
    comment = b"\x21\xfe\x0fshot at home 42\x00"
    first_image = clean.index(b"\x21\xf9")  # the first frame's control block
    dirty = clean[:first_image] + xmp_ext + comment + clean[first_image:] + b"GPS 37.77,-122.41"
    return clean, dirty


def test_an_animated_gif_loses_its_comment_xmp_and_trailing_bytes():
    clean, dirty = _gif_with_metadata()
    out = media.process_image(dirty, "image/gif")
    assert b"GPSLatitude" not in out.data and b"shot at home" not in out.data and b"GPS 37" not in out.data
    assert out.data == clean  # every frame and the loop count kept, byte for byte
    with Image.open(io.BytesIO(out.data)) as img:
        assert img.n_frames == 2 and img.info.get("loop") == 0


def test_a_truncated_gif_is_refused_rather_than_stored_as_is():
    clean, _ = _gif_with_metadata()
    with pytest.raises(media.ImageRejected):
        media._gif_without_metadata(clean[:-6])


def test_an_animated_png_is_stored_as_the_webp_it_became():
    frames = [Image.new("RGBA", (12, 12), c) for c in ("red", "blue")]
    buf = io.BytesIO()
    frames[0].save(buf, "PNG", save_all=True, append_images=frames[1:], duration=80)
    out = media.process_image(buf.getvalue(), "image/png")
    assert (out.mime, out.ext) == ("image/webp", ".webp")
    with Image.open(io.BytesIO(out.data)) as img:
        assert img.format == "WEBP" and img.n_frames == 2


def test_an_animation_too_large_to_decode_is_refused(monkeypatch):
    frames = [Image.new("RGB", (20, 20), c) for c in ("red", "green", "blue")]
    buf = io.BytesIO()
    frames[0].save(buf, "WEBP", save_all=True, append_images=frames[1:], duration=80)
    monkeypatch.setattr(media, "MAX_ANIMATED_PIXELS", 20 * 20 * 3 - 1)
    with pytest.raises(media.ImageRejected, match="animation is too large"):
        media.process_image(buf.getvalue(), "image/webp")


def test_an_animated_webp_is_written_again_without_its_exif():
    frames = [Image.new("RGB", (12, 12), c) for c in ("red", "green")]
    buf = io.BytesIO()
    frames[0].save(buf, "WEBP", save_all=True, append_images=frames[1:], duration=80,
                   exif=_exif_with_gps().tobytes())
    out = media.process_image(buf.getvalue(), "image/webp")
    assert out.mime == "image/webp"
    with Image.open(io.BytesIO(out.data)) as img:
        assert getattr(img, "n_frames", 1) == 2
        assert not img.getexif().get_ifd(GPS_IFD)


def test_responsive_sizes_never_upscale():
    assert media.variant_widths(3000) == (480, 960, 1440, 2048)
    assert media.variant_widths(1000) == (480, 960, 1000)
    assert media.variant_widths(960) == (480, 960)
    assert media.variant_widths(300) == (300,)


def test_derivatives_are_webp_at_each_width_plus_one_share_jpeg():
    out = media.process_image(_jpeg((1600, 900)), "image/jpeg", derivatives=True)
    assert [v.width for v in out.webp] == [480, 960, 1440, 1600]
    for variant in out.webp:
        with Image.open(io.BytesIO(variant.data)) as img:
            assert img.format == "WEBP"
            assert img.width == variant.width
            assert img.height == round(900 * variant.width / 1600)
    assert out.share.width == 1200 and out.share.mime == "image/jpeg"


def test_the_share_copy_of_a_transparent_png_is_flattened_on_white():
    buf = io.BytesIO()
    Image.new("RGBA", (50, 50), (0, 0, 0, 0)).save(buf, "PNG")
    out = media.process_image(buf.getvalue(), "image/png", derivatives=True)
    with Image.open(io.BytesIO(out.share.data)) as img:
        assert img.mode == "RGB"
        assert img.getpixel((0, 0)) == (255, 255, 255)
    assert out.share.width == 50


def test_the_stored_copy_is_capped_at_max_side():
    out = media.process_image(_jpeg((4000, 100)), "image/jpeg")
    assert out.width == media.MAX_SIDE
    assert out.height == 80


def test_a_colour_profile_is_converted_to_srgb_and_not_kept():
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 120, 200)).save(buf, "JPEG", icc_profile=profile)
    out = media.process_image(buf.getvalue(), "image/jpeg")
    with Image.open(io.BytesIO(out.data)) as img:
        assert "icc_profile" not in img.info


def test_an_unreadable_profile_leaves_the_pixels_alone():
    img = Image.new("RGB", (4, 4), "red")
    img.info["icc_profile"] = b"not a profile"
    assert media._to_srgb(img, "RGB") is None
    out = media._clean(img)
    assert out.getpixel((0, 0)) == (255, 0, 0) and "icc_profile" not in out.info


def test_a_cmyk_picture_goes_through_its_own_profile_before_becoming_rgb(monkeypatch):
    # The profile describes CMYK pixels: it has to see them as CMYK, not after
    # a naive convert("RGB") (which it would refuse, keeping shifted colours).
    seen = {}

    def profile_to_profile(img, src, dst, outputMode):
        seen.update(mode=img.mode, out=outputMode)
        return Image.new(outputMode, img.size, (1, 2, 3))

    monkeypatch.setattr(ImageCms, "ImageCmsProfile", lambda f: object())
    monkeypatch.setattr(ImageCms, "profileToProfile", profile_to_profile)
    img = Image.new("CMYK", (4, 4), (0, 255, 255, 0))
    img.info["icc_profile"] = b"a CMYK press profile"
    out = media._clean(img)
    assert seen == {"mode": "CMYK", "out": "RGB"}
    assert out.mode == "RGB" and out.getpixel((0, 0)) == (1, 2, 3)


def test_bytes_that_are_not_an_image_are_refused():
    with pytest.raises(media.ImageRejected):
        media.process_image(b"GIF89a but not really", "image/gif")


def test_a_decompression_bomb_is_refused(monkeypatch):
    monkeypatch.setattr(media, "MAX_PIXELS", 100)
    with pytest.raises(media.ImageRejected, match="too large"):
        media.process_image(_jpeg((20, 20)), "image/jpeg")


def test_filename_keeps_the_stem_and_takes_the_stored_extension():
    assert media.filename_for("holiday.HEIC.gif", ".png") == "holiday.HEIC.png"
    assert media.filename_for("../../etc/passwd", ".jpg") == "passwd.jpg"
    assert media.filename_for(None, ".webp") == "image.webp"


class FakeStorage:
    def __init__(self):
        self.calls = []

    async def upload_file(self, *, file_bytes, filename, prefix, content_type):
        self.calls.append((filename, prefix, content_type, len(file_bytes)))
        return f"https://cdn.example.test/{prefix}/{len(self.calls)}-{filename}"


def test_store_processed_uploads_every_size_and_reports_them_in_order(monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr(media, "get_storage", lambda: storage)
    image = media.process_image(_jpeg((1000, 500)), "image/jpeg", derivatives=True)

    stored = asyncio.run(media.store_processed(image, prefix="cappe/library", filename="Beach day.jpg"))

    assert stored.url == "https://cdn.example.test/cappe/library/1-Beach day.jpg"
    assert (stored.width, stored.height, stored.mime) == (1000, 500, "image/jpeg")
    assert stored.bytes == len(image.data)
    assert stored.variants["webp"] == [
        {"w": 480, "url": "https://cdn.example.test/cappe/library/2-w480.webp"},
        {"w": 960, "url": "https://cdn.example.test/cappe/library/3-w960.webp"},
        {"w": 1000, "url": "https://cdn.example.test/cappe/library/4-w1000.webp"},
    ]
    assert stored.variants["share"] == {"w": 1000, "url": "https://cdn.example.test/cappe/library/5-share.jpg"}
    assert {c[2] for c in storage.calls[1:4]} == {"image/webp"}


def test_store_processed_without_sizes_uploads_one_file(monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr(media, "get_storage", lambda: storage)
    stored = asyncio.run(media.store_processed(media.process_image(_jpeg(), "image/jpeg"), prefix="cappe"))
    assert len(storage.calls) == 1
    assert stored.variants == {}
    assert storage.calls[0][0] == "image.jpg"
