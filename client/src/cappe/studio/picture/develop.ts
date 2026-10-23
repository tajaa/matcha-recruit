// What a recipe does to each pixel, twice: as the fragment shader the Picture
// Editor draws with (gl.ts), and as `developPixel`, the same arithmetic in
// TypeScript, which the tests hold the shader to. Change one, change both.
//
// Order: sharpen (on the source), white balance and exposure in linear light,
// then in display values the tone (shadows, highlights, whites, blacks),
// contrast, clarity, saturation and vibrance, black and white, split toning,
// fade, vignette, grain; last the cut-out's alpha.
//
// Geometry: an output pixel is found in the source by undoing the crop, the
// straightening (about the frame's centre, grown by `coverScale` so no edge
// shows), the flips and the quarter turn.

import { WHOLE, coverScale, turned, type Crop, type Recipe } from './recipe'

export type Pt = { x: number; y: number }

/** Where output point (u, v) — fractions of the output, top-left origin —
 *  comes from in the source, as fractions of the source. */
export function sourceUv(u: number, v: number, srcW: number, srcH: number, crop: Crop = WHOLE): Pt {
  const [tw, th] = turned(srcW, srcH, crop.turn)
  let x = (crop.x + u * crop.w) * tw
  let y = (crop.y + v * crop.h) * th
  if (crop.angle) {
    const a = (crop.angle * Math.PI) / 180, c = Math.cos(a), s = Math.sin(a)
    const k = coverScale(tw, th, crop.angle)
    const dx = (x - tw / 2) / k, dy = (y - th / 2) / k
    x = tw / 2 + dx * c + dy * s
    y = th / 2 - dx * s + dy * c
  }
  if (crop.flip_h) x = tw - x
  if (crop.flip_v) y = th - y
  let sx = x, sy = y
  if (crop.turn === 90) { sx = y; sy = srcH - x }
  else if (crop.turn === 180) { sx = srcW - x; sy = srcH - y }
  else if (crop.turn === 270) { sx = srcW - y; sy = x }
  return { x: sx / srcW, y: sy / srcH }
}

/** Where source point (fractions) lands in the output (the inverse of
 *  `sourceUv`): for drawing a cut-out's points on the picture shown. */
export function outputUv(sx: number, sy: number, srcW: number, srcH: number, crop: Crop = WHOLE): Pt {
  const [tw, th] = turned(srcW, srcH, crop.turn)
  let x = sx * srcW, y = sy * srcH
  if (crop.turn === 90) { const t = x; x = srcH - y; y = t }
  else if (crop.turn === 180) { x = srcW - x; y = srcH - y }
  else if (crop.turn === 270) { const t = x; x = y; y = srcW - t }
  if (crop.flip_h) x = tw - x
  if (crop.flip_v) y = th - y
  if (crop.angle) {
    const a = (crop.angle * Math.PI) / 180, c = Math.cos(a), s = Math.sin(a)
    const k = coverScale(tw, th, crop.angle)
    const dx = x - tw / 2, dy = y - th / 2
    x = tw / 2 + (dx * c - dy * s) * k
    y = th / 2 + (dx * s + dy * c) * k
  }
  return { x: (x / tw - crop.x) / crop.w, y: (y / th - crop.y) / crop.h }
}

// ── colour ───────────────────────────────────────────────────────────────────

type RGB = [number, number, number]

const toLinear = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
const toDisplay = (c: number) => (c <= 0.0031308 ? c * 12.92 : 1.055 * c ** (1 / 2.4) - 0.055)
const luma = (c: RGB) => 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
const smoothstep = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)))
  return t * t * (3 - 2 * t)
}
const clamp01 = (x: number) => Math.min(1, Math.max(0, x))

/** A hue (degrees) at full saturation, as display RGB. */
export function hueRgb(h: number): RGB {
  const f = (n: number) => {
    const k = (n + h / 30) % 12
    return 0.5 - 0.5 * Math.max(-1, Math.min(k - 3, 9 - k, 1))
  }
  return [f(0), f(8), f(4)]
}

/** The grain's noise at an output pixel: deterministic, in [-0.5, 0.5). */
export function grainNoise(px: number, py: number): number {
  let x = (px * 0.1031) % 1, y = (py * 0.1031) % 1, z = (px * 0.1031) % 1
  const d = x * (y + 33.33) + y * (z + 33.33) + z * (x + 33.33)
  x += d; y += d; z += d
  return (((x + y) * z) % 1) - 0.5
}

/** One pixel developed: `c` the source's display RGB (0–1), `uv` where it is
 *  in the output (0–1, for the vignette), `px` its pixel (for the grain).
 *  Sharpening and clarity need neighbours and are the shader's alone. */
export function developPixel(c: RGB, r: Recipe, uv: Pt, px: Pt): RGB {
  const v = (k: keyof Recipe) => ((r[k] as number | undefined) ?? 0) / 100
  // White balance and exposure, in linear light.
  let lin: RGB = [toLinear(c[0]), toLinear(c[1]), toLinear(c[2])]
  const t = v('temp'), n = v('tint')
  lin = [lin[0] * (1 + 0.25 * t + 0.05 * n), lin[1] * (1 - 0.18 * n), lin[2] * (1 - 0.25 * t + 0.05 * n)]
  const ev = 2 ** (r.exposure ?? 0)
  let d: RGB = lin.map((x) => toDisplay(Math.min(16, Math.max(0, x * ev)))) as RGB
  // Tone, by how light the pixel is.
  const L = luma(d)
  const sh = v('shadows'), hi = v('highlights'), wh = v('whites'), bl = v('blacks')
  const dl = 2 * sh * L * (1 - L) ** 2 + 2 * hi * L * L * (1 - L) + 0.25 * wh * L ** 3 + 0.15 * bl * (1 - L) ** 3
  d = d.map((x) => x + dl) as RGB
  const ct = v('contrast')
  d = d.map((x) => 0.5 + (x - 0.5) * (1 + 0.75 * ct)) as RGB
  // Colour.
  let g = luma(d)
  const sat = v('saturation')
  d = d.map((x) => g + (x - g) * (1 + sat)) as RGB
  const vib = v('vibrance')
  const spread = Math.max(...d) - Math.min(...d)
  d = d.map((x) => g + (x - g) * (1 + vib * (1 - Math.min(1, spread * 1.5)))) as RGB
  if (r.bw) {
    const m = 0.3 * d[0] + 0.59 * d[1] + 0.11 * d[2]
    d = [m, m, m]
  }
  g = luma(d)
  const shAmt = v('sh_amt'), hiAmt = v('hi_amt')
  if (shAmt || hiAmt) {
    const hs = hueRgb(r.sh_hue ?? 0), hh = hueRgb(r.hi_hue ?? 0)
    const ws = (1 - smoothstep(0, 0.6, g)) * shAmt * 0.3, wh2 = smoothstep(0.4, 1, g) * hiAmt * 0.3
    d = d.map((x, i) => x + (hs[i] - 0.5) * ws + (hh[i] - 0.5) * wh2) as RGB
  }
  const fade = v('fade')
  d = d.map((x) => 0.1 * fade + x * (1 - 0.16 * fade)) as RGB
  // Vignette, from the output's middle to its corners.
  const vg = v('vignette')
  if (vg) {
    const dist = Math.hypot(uv.x - 0.5, uv.y - 0.5) / Math.SQRT1_2
    const f = smoothstep(0.35, 1, dist)
    d = d.map((x) => (vg < 0 ? x * (1 + vg * 0.85 * f) : x + (1 - x) * vg * 0.7 * f)) as RGB
  }
  const gr = v('grain')
  if (gr) {
    const nz = grainNoise(px.x, px.y) * gr * 0.18 * (1 - 0.5 * clamp01(g))
    d = d.map((x) => x + nz) as RGB
  }
  return d.map(clamp01) as RGB
}

// ── the shader ───────────────────────────────────────────────────────────────

export const VERTEX = `#version 300 es
in vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
`

export const FRAGMENT = `#version 300 es
precision highp float;
uniform sampler2D uSrc;
uniform sampler2D uMask;
uniform vec2 uOut;      // the output's size, px
uniform vec2 uSrcSize;  // the source's size, px
uniform vec4 uCrop;     // x, y, w, h: fractions of the turned picture
uniform vec2 uTurned;   // the turned picture's size, px
uniform float uAngle;   // straightening, radians (clockwise)
uniform float uScale;   // coverScale
uniform int uTurn;      // 0, 90, 180, 270
uniform vec2 uFlip;     // 1 when flipped across that axis
uniform float uAdjust;  // 0: "before" (geometry only)
uniform float uExposure, uContrast, uHighlights, uShadows, uWhites, uBlacks;
uniform float uTemp, uTint, uVibrance, uSaturation, uClarity, uSharpen, uVignette, uGrain, uFade;
uniform float uBw, uShAmt, uHiAmt;
uniform vec3 uShRgb, uHiRgb;
uniform float uMaskOn, uFeather, uInvert;
out vec4 outColor;

float toLinear(float c) { return c <= 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4); }
float toDisplay(float c) { return c <= 0.0031308 ? c * 12.92 : 1.055 * pow(c, 1.0 / 2.4) - 0.055; }
float luma(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }
float grainNoise(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z) - 0.5;
}

vec2 sourceUv(vec2 uv) {
  vec2 p = (uCrop.xy + uv * uCrop.zw) * uTurned;
  if (uAngle != 0.0) {
    float c = cos(uAngle), s = sin(uAngle);
    vec2 d = (p - uTurned * 0.5) / uScale;
    p = uTurned * 0.5 + vec2(d.x * c + d.y * s, -d.x * s + d.y * c);
  }
  if (uFlip.x > 0.5) p.x = uTurned.x - p.x;
  if (uFlip.y > 0.5) p.y = uTurned.y - p.y;
  vec2 q = p;
  if (uTurn == 90) q = vec2(p.y, uSrcSize.y - p.x);
  else if (uTurn == 180) q = uSrcSize - p;
  else if (uTurn == 270) q = vec2(uSrcSize.x - p.y, p.x);
  return q / uSrcSize;
}

void main() {
  vec2 uv = vec2(gl_FragCoord.x / uOut.x, 1.0 - gl_FragCoord.y / uOut.y);
  vec2 st = clamp(sourceUv(uv), vec2(0.0), vec2(1.0));
  vec3 c = texture(uSrc, st).rgb;
  float alpha = 1.0;
  if (uMaskOn > 0.5) {
    alpha = textureLod(uMask, st, uFeather).r;
    if (uInvert > 0.5) alpha = 1.0 - alpha;
  }
  if (uAdjust < 0.5) { outColor = vec4(c * alpha, alpha); return; }

  if (uSharpen > 0.0) {
    vec2 px = 1.0 / uSrcSize;
    vec3 n = texture(uSrc, st + vec2(px.x, 0.0)).rgb + texture(uSrc, st - vec2(px.x, 0.0)).rgb
           + texture(uSrc, st + vec2(0.0, px.y)).rgb + texture(uSrc, st - vec2(0.0, px.y)).rgb;
    c = clamp(c + uSharpen * 1.5 * (c - n * 0.25), 0.0, 1.0);
  }
  vec3 lin = vec3(toLinear(c.r), toLinear(c.g), toLinear(c.b));
  lin *= vec3(1.0 + 0.25 * uTemp + 0.05 * uTint, 1.0 - 0.18 * uTint, 1.0 - 0.25 * uTemp + 0.05 * uTint);
  lin = clamp(lin * exp2(uExposure), 0.0, 16.0);
  vec3 d = vec3(toDisplay(lin.r), toDisplay(lin.g), toDisplay(lin.b));

  float L = luma(d);
  float dl = 2.0 * uShadows * L * (1.0 - L) * (1.0 - L) + 2.0 * uHighlights * L * L * (1.0 - L)
           + 0.25 * uWhites * L * L * L + 0.15 * uBlacks * (1.0 - L) * (1.0 - L) * (1.0 - L);
  d += dl;
  d = 0.5 + (d - 0.5) * (1.0 + 0.75 * uContrast);
  if (uClarity != 0.0) {
    float Lb = luma(textureLod(uSrc, st, 4.0).rgb);
    float Ls = luma(c);
    d += uClarity * 0.6 * (Ls - Lb) * (1.0 - pow(2.0 * clamp(L, 0.0, 1.0) - 1.0, 2.0));
  }

  float g = luma(d);
  d = g + (d - g) * (1.0 + uSaturation);
  float spread = max(d.r, max(d.g, d.b)) - min(d.r, min(d.g, d.b));
  d = g + (d - g) * (1.0 + uVibrance * (1.0 - min(1.0, spread * 1.5)));
  if (uBw > 0.5) d = vec3(dot(d, vec3(0.3, 0.59, 0.11)));
  g = luma(d);
  if (uShAmt > 0.0 || uHiAmt > 0.0) {
    float ws = (1.0 - smoothstep(0.0, 0.6, g)) * uShAmt * 0.3;
    float wh = smoothstep(0.4, 1.0, g) * uHiAmt * 0.3;
    d += (uShRgb - 0.5) * ws + (uHiRgb - 0.5) * wh;
  }
  d = 0.1 * uFade + d * (1.0 - 0.16 * uFade);
  if (uVignette != 0.0) {
    float f = smoothstep(0.35, 1.0, length(uv - 0.5) / 0.70710678);
    d = uVignette < 0.0 ? d * (1.0 + uVignette * 0.85 * f) : d + (1.0 - d) * uVignette * 0.7 * f;
  }
  if (uGrain > 0.0) d += grainNoise(floor(gl_FragCoord.xy)) * uGrain * 0.18 * (1.0 - 0.5 * clamp(g, 0.0, 1.0));
  d = clamp(d, 0.0, 1.0);
  outColor = vec4(d * alpha, alpha);
}
`
