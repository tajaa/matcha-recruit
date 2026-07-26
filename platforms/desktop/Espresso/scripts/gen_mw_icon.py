#!/usr/bin/env python3
"""Generate the Werk "MW" monogram app icon — dark cool-charcoal MW on a
light-gray gradient squircle (the platinum brand identity).

Outputs app_icon_1024.png + app_icon_512.png into the AppIcon.appiconset.
Re-run after tweaking colors/geometry. Pure Pillow, uses the system
SF Rounded variable font.
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ICONSET = (
    "/Users/finch/Documents/github/matcha/desktop/Werk/"
    "Matcha/Resources/Assets.xcassets/AppIcon.appiconset"
)
FONT_PATH = "/System/Library/Fonts/SFNSRounded.ttf"

# Platinum palette (matches Color+Extensions.swift)
GRAD_TOP = (247, 248, 251)     # #F7F8FB platinumRadialCenter
GRAD_BOT = (208, 212, 221)     # ~#D0D4DD a touch darker than the edge for depth
MW_DARK = (33, 36, 43)         # ~#21242B between accent and accentDark


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def render(size: int) -> Image.Image:
    S = size
    pad = round(S * 0.092)          # transparent margin (Apple grid ~824/1024)
    box = (pad, pad, S - pad, S - pad)
    radius = round((box[2] - box[0]) * 0.2237)  # macOS squircle-ish corner

    # 1. Vertical gradient tile.
    grad = Image.new("RGB", (S, S), GRAD_TOP)
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        gd.line([(0, y), (S, y)], fill=lerp(GRAD_TOP, GRAD_BOT, y / S))

    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=radius, fill=255)

    # 2. Soft drop shadow under the tile for native depth.
    canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        box, radius=radius, fill=(0, 0, 0, 70)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(S * 0.018))
    canvas.alpha_composite(shadow, (0, round(S * 0.012)))

    # 3. The gradient tile, masked to the squircle.
    tile = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    tile.paste(grad, (0, 0), mask)
    canvas.alpha_composite(tile)

    # 4. Hairline top highlight on the tile edge.
    ImageDraw.Draw(canvas).rounded_rectangle(
        box, radius=radius, outline=(255, 255, 255, 150), width=max(1, S // 340)
    )

    # 5. The "MW" monogram, centered, bold SF Rounded.
    font = ImageFont.truetype(FONT_PATH, round(S * 0.34))
    try:
        font.set_variation_by_name("Bold")
    except Exception:
        try:
            font.set_variation_by_name("Heavy")
        except Exception:
            pass

    draw = ImageDraw.Draw(canvas)
    text = "MW"
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    tx = (S - (r - l)) / 2 - l
    ty = (S - (b - t)) / 2 - t
    draw.text((tx, ty), text, font=font, fill=MW_DARK + (255,))

    return canvas


def main():
    icon = render(1024)
    icon.save(f"{ICONSET}/app_icon_1024.png")
    icon.resize((512, 512), Image.LANCZOS).save(f"{ICONSET}/app_icon_512.png")
    print("wrote app_icon_1024.png + app_icon_512.png ->", ICONSET)


if __name__ == "__main__":
    main()
