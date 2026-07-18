import type { LocationRow } from './types'

export function locationLabel(loc: LocationRow): string {
  const name = (loc.name || '').trim()
  const place = [loc.city, loc.state].filter(Boolean).join(', ')
  if (name && place) return `${name} — ${place}`
  return name || place || loc.id.slice(0, 8)
}

// Mirrors the server's WCAG auto-contrast pick (ir_report_poster._text_on) so the
// live preview shows the same title/footer color the PDF will use.
export function relLum(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
export function contrastRatio(a: string, b: string): number {
  const la = relLum(a), lb = relLum(b)
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
}
export function textOn(primary: string): string {
  return contrastRatio(primary, '#0c1f16') >= contrastRatio(primary, '#ffffff') ? '#0c1f16' : '#ffffff'
}
