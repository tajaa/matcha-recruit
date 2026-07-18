import { FONT_PAIRINGS } from '../../../data/cappeThemes'

export const themeObj = (v: unknown): Record<string, unknown> =>
  v && typeof v === 'object' && !Array.isArray(v) ? { ...(v as Record<string, unknown>) } : {}
export const themeColors = (t: Record<string, unknown>): Record<string, string> =>
  (t.colors && typeof t.colors === 'object' ? { ...(t.colors as Record<string, string>) } : {})
export const themeFonts = (t: Record<string, unknown>): { heading?: string; body?: string } =>
  (t.fonts && typeof t.fonts === 'object' ? { ...(t.fonts as Record<string, string>) } : {})
// Match a font pairing id from a theme's current fonts (for the select value).
export const fontPairId = (t: Record<string, unknown>): string => {
  const f = themeFonts(t)
  return FONT_PAIRINGS.find((p) => p.heading === (f.heading || 'Inter') && p.body === (f.body || 'Inter'))?.id || 'inter'
}
