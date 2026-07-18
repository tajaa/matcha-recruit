// Curated theme presets for the Cappe site editor. Applying one writes the
// site's `theme_config` (consumed by the server renderer's `_tokens`), instantly
// re-skinning the published site — fonts, palette, corner radius, hero/nav style.
//
// Premium presets are flagged so the editor can badge them; today everyone can
// apply (we gate/charge later). `swatch` drives the card preview only.

export type CappeThemePreset = {
  id: string
  name: string
  blurb: string
  premium: boolean
  swatch: { bg: string; surface: string; brand: string; text: string }
  font: string
  // Written verbatim into theme_config (plus { preset: id } for selection).
  config: Record<string, unknown>
}

// Curated heading/body font pairings for the quick theme tweaks.
export const FONT_PAIRINGS: { id: string; label: string; heading: string; body: string }[] = [
  { id: 'inter', label: 'Inter / Inter', heading: 'Inter', body: 'Inter' },
  { id: 'fraunces', label: 'Fraunces / Inter', heading: 'Fraunces', body: 'Inter' },
  { id: 'playfair', label: 'Playfair / Inter', heading: 'Playfair Display', body: 'Inter' },
  { id: 'sora', label: 'Sora / Inter', heading: 'Sora', body: 'Inter' },
  { id: 'space', label: 'Space Grotesk / Inter', heading: 'Space Grotesk', body: 'Inter' },
  { id: 'lora', label: 'Lora / Lora', heading: 'Lora', body: 'Lora' },
  { id: 'syne', label: 'Syne / Manrope', heading: 'Syne', body: 'Manrope' },
  { id: 'unbounded', label: 'Unbounded / DM Sans', heading: 'Unbounded', body: 'DM Sans' },
  { id: 'bricolage', label: 'Bricolage / Work Sans', heading: 'Bricolage Grotesque', body: 'Work Sans' },
  { id: 'dmserif', label: 'DM Serif / DM Sans', heading: 'DM Serif Display', body: 'DM Sans' },
  { id: 'cormorant', label: 'Cormorant / Public Sans', heading: 'Cormorant Garamond', body: 'Public Sans' },
  { id: 'bodoni', label: 'Bodoni Moda / Spectral', heading: 'Bodoni Moda', body: 'Spectral' },
  { id: 'bebas', label: 'Bebas Neue / Hanken Grotesk', heading: 'Bebas Neue', body: 'Hanken Grotesk' },
  { id: 'jakarta', label: 'Plus Jakarta / Plus Jakarta', heading: 'Plus Jakarta Sans', body: 'Plus Jakarta Sans' },
  { id: 'marcellus', label: 'Marcellus / Libre Franklin', heading: 'Marcellus', body: 'Libre Franklin' },
  { id: 'instrument', label: 'Instrument Serif / Inter', heading: 'Instrument Serif', body: 'Inter' },
]

// Granular font catalog for the premium designer (independent heading/body),
// powering the searchable CappeFontPicker. All are Google-Fonts-hosted (fetched
// on demand by the renderer's _gfonts_link); serif members are mirrored into
// render.py's `_SERIF` for correct fallbacks. `body: true` = also reads well as
// body copy (so it surfaces in the Body-font picker).
export type FontCat = 'Sans' | 'Serif' | 'Display' | 'Mono' | 'Handwriting'
export type FontDef = { name: string; cat: FontCat; body?: boolean }

export const FONT_CATALOG: FontDef[] = [
  // ── Sans ──────────────────────────────────────────────────────────────
  { name: 'Inter', cat: 'Sans', body: true },
  { name: 'Manrope', cat: 'Sans', body: true },
  { name: 'DM Sans', cat: 'Sans', body: true },
  { name: 'Work Sans', cat: 'Sans', body: true },
  { name: 'Mulish', cat: 'Sans', body: true },
  { name: 'Public Sans', cat: 'Sans', body: true },
  { name: 'Hanken Grotesk', cat: 'Sans', body: true },
  { name: 'Libre Franklin', cat: 'Sans', body: true },
  { name: 'Plus Jakarta Sans', cat: 'Sans', body: true },
  { name: 'Figtree', cat: 'Sans', body: true },
  { name: 'Onest', cat: 'Sans', body: true },
  { name: 'Albert Sans', cat: 'Sans', body: true },
  { name: 'Be Vietnam Pro', cat: 'Sans', body: true },
  { name: 'Epilogue', cat: 'Sans', body: true },
  { name: 'Lexend', cat: 'Sans', body: true },
  { name: 'Urbanist', cat: 'Sans', body: true },
  { name: 'Instrument Sans', cat: 'Sans', body: true },
  { name: 'Schibsted Grotesk', cat: 'Sans', body: true },
  { name: 'Sora', cat: 'Sans' },
  { name: 'Space Grotesk', cat: 'Sans' },
  { name: 'Outfit', cat: 'Sans' },
  { name: 'Archivo', cat: 'Sans' },
  { name: 'Familjen Grotesk', cat: 'Sans' },
  { name: 'Red Hat Display', cat: 'Sans' },
  // ── Serif ─────────────────────────────────────────────────────────────
  { name: 'Lora', cat: 'Serif', body: true },
  { name: 'Spectral', cat: 'Serif', body: true },
  { name: 'Newsreader', cat: 'Serif', body: true },
  { name: 'PT Serif', cat: 'Serif', body: true },
  { name: 'Source Serif 4', cat: 'Serif', body: true },
  { name: 'EB Garamond', cat: 'Serif', body: true },
  { name: 'Crimson Pro', cat: 'Serif', body: true },
  { name: 'Bitter', cat: 'Serif', body: true },
  { name: 'Frank Ruhl Libre', cat: 'Serif', body: true },
  { name: 'Fraunces', cat: 'Serif' },
  { name: 'Playfair Display', cat: 'Serif' },
  { name: 'Cormorant Garamond', cat: 'Serif' },
  { name: 'Libre Baskerville', cat: 'Serif' },
  { name: 'DM Serif Display', cat: 'Serif' },
  { name: 'Instrument Serif', cat: 'Serif' },
  { name: 'Bodoni Moda', cat: 'Serif' },
  { name: 'Marcellus', cat: 'Serif' },
  { name: 'Gloock', cat: 'Serif' },
  // ── Display ───────────────────────────────────────────────────────────
  { name: 'Syne', cat: 'Display' },
  { name: 'Unbounded', cat: 'Display' },
  { name: 'Bricolage Grotesque', cat: 'Display' },
  { name: 'Anton', cat: 'Display' },
  { name: 'Bebas Neue', cat: 'Display' },
  { name: 'Archivo Black', cat: 'Display' },
  { name: 'Big Shoulders Display', cat: 'Display' },
  { name: 'Caprasimo', cat: 'Display' },
  // ── Mono ──────────────────────────────────────────────────────────────
  { name: 'JetBrains Mono', cat: 'Mono', body: true },
  { name: 'Space Mono', cat: 'Mono' },
  { name: 'IBM Plex Mono', cat: 'Mono', body: true },
  { name: 'DM Mono', cat: 'Mono' },
  // ── Handwriting ───────────────────────────────────────────────────────
  { name: 'Caveat', cat: 'Handwriting' },
  { name: 'Dancing Script', cat: 'Handwriting' },
  { name: 'Pacifico', cat: 'Handwriting' },
  { name: 'Satisfy', cat: 'Handwriting' },
]

export const FONT_CATEGORY: Record<string, FontCat> =
  Object.fromEntries(FONT_CATALOG.map((f) => [f.name, f.cat]))
export const HEADING_FONTS: string[] = FONT_CATALOG.map((f) => f.name)
export const BODY_FONTS: string[] = FONT_CATALOG.filter((f) => f.body).map((f) => f.name)

export const RADII: { value: string; label: string }[] = [
  { value: 'none', label: 'Sharp' }, { value: 'sm', label: 'Small' },
  { value: 'md', label: 'Medium' }, { value: 'lg', label: 'Large' },
  { value: 'xl', label: 'XL' }, { value: '2xl', label: 'Rounded' },
]

/** Readable text color (black/white) for a given hex background. */
export function contrastText(hex: string): string {
  const m = /^#?([0-9a-f]{6})$/i.exec((hex || '').trim())
  if (!m) return '#ffffff'
  const n = parseInt(m[1], 16)
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255
  // Relative luminance (sRGB approximation).
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return lum > 0.6 ? '#10120a' : '#ffffff'
}

export const CAPPE_THEMES: CappeThemePreset[] = [
  {
    id: 'clean',
    name: 'Clean',
    blurb: 'Bright, modern, neutral. A safe default that reads well anywhere.',
    premium: false,
    swatch: { bg: '#ffffff', surface: '#f6f7f9', brand: '#10b981', text: '#16181d' },
    font: 'Inter',
    config: { mode: 'light', fonts: { heading: 'Inter', body: 'Inter' }, radius: 'lg', heroStyle: 'centered', navStyle: 'simple' },
  },
  {
    id: 'minimal',
    name: 'Minimal',
    blurb: 'Near-black accents, tight corners. Quiet, confident, gallery-like.',
    premium: false,
    swatch: { bg: '#ffffff', surface: '#f4f4f5', brand: '#18181b', text: '#18181b' },
    font: 'Inter',
    config: {
      mode: 'light', fonts: { heading: 'Inter', body: 'Inter' }, radius: 'sm',
      heroStyle: 'minimal', navStyle: 'simple',
      colors: { brand: '#18181b', brandText: '#ffffff', accent: '#18181b' },
    },
  },
  {
    id: 'noir',
    name: 'Noir',
    blurb: 'Dark mode with an electric lime pop. Great for creators & studios.',
    premium: false,
    swatch: { bg: '#0b0b0f', surface: '#15151d', brand: '#a3e635', text: '#f5f6f7' },
    font: 'Inter',
    config: { mode: 'dark', fonts: { heading: 'Inter', body: 'Inter' }, radius: 'lg', heroStyle: 'centered', navStyle: 'centered' },
  },
  {
    id: 'editorial',
    name: 'Editorial',
    blurb: 'Fraunces serif headlines over clean body text. Warm and premium.',
    premium: true,
    swatch: { bg: '#fdfbf7', surface: '#f3eee4', brand: '#b4532a', text: '#1c1a17' },
    font: 'Fraunces',
    config: {
      mode: 'light', fonts: { heading: 'Fraunces', body: 'Inter' }, radius: 'md',
      heroStyle: 'split', navStyle: 'simple', premium: true,
      colors: { bg: '#fdfbf7', surface: '#f3eee4', text: '#1c1a17', muted: '#6b5f50', border: '#e6ddcd', brand: '#b4532a', brandText: '#ffffff', accent: '#b4532a' },
    },
  },
  {
    id: 'studio',
    name: 'Studio',
    blurb: 'Playfair display on deep charcoal with a gold accent. Luxe & moody.',
    premium: true,
    swatch: { bg: '#111014', surface: '#1c1a22', brand: '#d4af37', text: '#f7f5f0' },
    font: 'Playfair Display',
    config: {
      mode: 'dark', fonts: { heading: 'Playfair Display', body: 'Inter' }, radius: 'md',
      heroStyle: 'centered', navStyle: 'centered', premium: true,
      colors: { bg: '#111014', surface: '#1c1a22', text: '#f7f5f0', muted: '#a89f93', border: '#2c2933', brand: '#d4af37', brandText: '#111014', accent: '#d4af37' },
    },
  },
  {
    id: 'sunset',
    name: 'Sunset',
    blurb: 'Soft cream canvas, coral brand, generous rounding. Friendly & fresh.',
    premium: true,
    swatch: { bg: '#fff8f3', surface: '#ffeee3', brand: '#f0603a', text: '#2a1d18' },
    font: 'Sora',
    config: {
      mode: 'light', fonts: { heading: 'Sora', body: 'Inter' }, radius: '2xl',
      heroStyle: 'centered', navStyle: 'simple', premium: true,
      colors: { bg: '#fff8f3', surface: '#ffeee3', text: '#2a1d18', muted: '#7a6258', border: '#f6ddcd', brand: '#f0603a', brandText: '#ffffff', accent: '#f0603a' },
    },
  },
]
