/** Colours as the design keeps them ('#rrggbb', '#rrggbbaa', or 'accent' for
 *  the magazine's own) and as a picker works with them (hue, saturation,
 *  value, alpha). */

export type Hsva = { h: number; s: number; v: number; a: number }

const HEX = /^#([0-9a-f]{6})([0-9a-f]{2})?$/i

export const isHex = (c: string) => HEX.test(c)

export function parseHex(c: string): { r: number; g: number; b: number; a: number } | null {
  const m = HEX.exec(c)
  if (!m) return null
  const n = parseInt(m[1], 16)
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255, a: m[2] ? parseInt(m[2], 16) / 255 : 1 }
}

const h2 = (n: number) => Math.round(Math.max(0, Math.min(255, n))).toString(16).padStart(2, '0')

export function toHex(r: number, g: number, b: number, a = 1): string {
  return `#${h2(r)}${h2(g)}${h2(b)}${a >= 0.999 ? '' : h2(a * 255)}`
}

export function hexToHsva(c: string): Hsva {
  const p = parseHex(c) ?? { r: 0, g: 0, b: 0, a: 1 }
  const r = p.r / 255, g = p.g / 255, b = p.b / 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min
  let h = 0
  if (d) {
    if (max === r) h = ((g - b) / d) % 6
    else if (max === g) h = (b - r) / d + 2
    else h = (r - g) / d + 4
    h *= 60
    if (h < 0) h += 360
  }
  return { h, s: max ? d / max : 0, v: max, a: p.a }
}

export function hsvaToHex({ h, s, v, a }: Hsva): string {
  const c = v * s, x = c * (1 - Math.abs(((h / 60) % 2) - 1)), m = v - c
  const [r, g, b] = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x] : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x]
  return toHex((r + m) * 255, (g + m) * 255, (b + m) * 255, a)
}

/** What a typed colour means: '#abc', 'abcdef', 'rgb(…)', a name we know. */
export function readColour(text: string): string | null {
  const t = text.trim().toLowerCase()
  if (t === 'accent') return 'accent'
  const short = /^#?([0-9a-f])([0-9a-f])([0-9a-f])$/.exec(t)
  if (short) return `#${short[1]}${short[1]}${short[2]}${short[2]}${short[3]}${short[3]}`
  const long = /^#?([0-9a-f]{6}|[0-9a-f]{8})$/.exec(t)
  if (long) return `#${long[1]}`
  const rgb = /^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+))?\s*\)$/.exec(t)
  if (rgb) return toHex(+rgb[1], +rgb[2], +rgb[3], rgb[4] === undefined ? 1 : +rgb[4])
  const named: Record<string, string> = { white: '#ffffff', black: '#000000', transparent: '#00000000' }
  return named[t] ?? null
}

/** A colour as CSS, for a swatch (the magazine's accent drawn as itself). */
export const swatchCss = (c: string, accent = '#10b981') => (c === 'accent' ? accent : c)

/** A colour with its alpha set (0–1). */
export function withAlpha(c: string, a: number): string {
  const p = parseHex(c)
  return p ? toHex(p.r, p.g, p.b, a) : c
}

export const alphaOf = (c: string) => parseHex(c)?.a ?? 1
