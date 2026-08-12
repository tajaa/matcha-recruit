"""Release-artwork validation."""

from dataclasses import dataclass
from io import BytesIO
from typing import Literal

from PIL import Image, ImageOps


MIN_DIM = 3000
MAX_DIM = 6000
MAX_BYTES = 20 * 2**20


class ArtworkError(ValueError):
    """A user-facing artwork validation error."""


@dataclass(frozen=True)
class ArtworkMeta:
    width: int
    height: int
    format: Literal["jpeg", "png"]


def validate_artwork(data: bytes) -> ArtworkMeta:
    if len(data) > MAX_BYTES:
        raise ArtworkError("Artwork must be 20 MB or smaller.")
    try:
        image = Image.open(BytesIO(data))
        image_format = image.format
        image = ImageOps.exif_transpose(image)
        image.load()
    except Exception as exc:
        raise ArtworkError("Artwork must be a readable JPEG or PNG file.") from exc
    if image_format not in {"JPEG", "PNG"}:
        raise ArtworkError("Artwork must be a JPEG or PNG file.")
    if image.mode != "RGB":
        if image.mode == "CMYK":
            raise ArtworkError("Convert CMYK artwork to RGB before uploading.")
        raise ArtworkError("Artwork must be RGB with no alpha channel.")
    if image.width != image.height:
        raise ArtworkError("Artwork must be square.")
    if image.width < MIN_DIM:
        raise ArtworkError("Artwork must be at least 3000 x 3000 pixels.")
    if image.width > MAX_DIM:
        raise ArtworkError("Artwork must be no larger than 6000 x 6000 pixels.")
    return ArtworkMeta(image.width, image.height, "jpeg" if image_format == "JPEG" else "png")
