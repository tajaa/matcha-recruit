// Paper texture for /home-v2, as a background-style helper — not a fixed
// full-viewport overlay. Two things forced this shape:
//
// 1. `/textures/asfalt-light.png` (what pages/home/PageChrome.tsx:GrainOverlay
//    uses) is a 466x349 asphalt photo. Tiled at any visible opacity it reads
//    as mottled blotches, not paper; at an opacity low enough to hide the
//    blotches it's imperceptible. This uses inline fractal noise (SVG
//    feTurbulence) instead — fine, uniform, genuinely grain-shaped, no raster
//    asset or extra request.
// 2. A `fixed inset-0` blend-mode overlay forces the compositor to re-blend
//    the whole viewport every frame, including over the type, which muddies
//    text that should stay crisp. `paperSurface()` instead returns background
//    layers for one element at a time — the page root, the hero band, the
//    nav bar — so text painted on top of them stays untouched.

function noiseUrl({
  size,
  frequency,
  octaves,
  alpha,
}: {
  size: number;
  frequency: number;
  octaves: number;
  alpha: number;
}): string {
  const svg =
    `<svg xmlns='http://www.w3.org/2000/svg' width='${size}' height='${size}'>` +
    `<filter id='n'>` +
    `<feTurbulence type='fractalNoise' baseFrequency='${frequency}' numOctaves='${octaves}' stitchTiles='stitch'/>` +
    `<feColorMatrix type='saturate' values='0'/>` +
    `<feComponentTransfer><feFuncA type='linear' slope='${alpha}'/></feComponentTransfer>` +
    `</filter>` +
    `<rect width='100%' height='100%' filter='url(#n)'/></svg>`;
  return "data:image/svg+xml;utf8," + encodeURIComponent(svg);
}

// Fine tooth — the fibre-level grain. baseFrequency 0.4 lands clumps around
// 2.5px, which survives retina averaging (0.75, tried first, produced ~1.3px
// noise that flattened to nothing on screen).
const TOOTH_URL = noiseUrl({ size: 300, frequency: 0.4, octaves: 4, alpha: 0.9 });

// Coarse mottle — slow stock variation layered under the tooth. This is the
// thing that actually reads as "paper" rather than "a noise filter": real
// stock has both fine grain and broad density variation.
const MOTTLE_URL = noiseUrl({ size: 900, frequency: 0.012, octaves: 2, alpha: 0.9 });

/**
 * Background style for a paper-textured surface. `overlay` blend (not
 * `multiply`) is what makes the grain show on BOTH a light ground (cream) and
 * a dark one (the hero's matcha band) — multiply can only darken, so its
 * effect all but disappears on an already-dark fill.
 */
export function paperSurface(color: string): React.CSSProperties {
  return {
    backgroundColor: color,
    backgroundImage: `url("${TOOTH_URL}"), url("${MOTTLE_URL}")`,
    backgroundSize: "300px 300px, 900px 900px",
    backgroundBlendMode: "overlay, overlay",
  };
}

/** Same tooth + mottle layers, to stack ABOVE another background-image (e.g.
 * the hero band's density gradient) rather than starting from a flat color. */
export function paperLayers(): { backgroundImage: string; backgroundSize: string } {
  return {
    backgroundImage: `url("${TOOTH_URL}"), url("${MOTTLE_URL}")`,
    backgroundSize: "300px 300px, 900px 900px",
  };
}
