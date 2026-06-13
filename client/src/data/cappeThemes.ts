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
      heroStyle: 'split', navStyle: 'simple',
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
      heroStyle: 'centered', navStyle: 'centered',
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
      heroStyle: 'centered', navStyle: 'simple',
      colors: { bg: '#fff8f3', surface: '#ffeee3', text: '#2a1d18', muted: '#7a6258', border: '#f6ddcd', brand: '#f0603a', brandText: '#ffffff', accent: '#f0603a' },
    },
  },
]
