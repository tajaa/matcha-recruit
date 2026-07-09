// Curated Google Fonts for the newsletter body. Keep the `value` slugs in
// sync with FONT_STACKS in server/app/core/services/newsletter_service.py —
// the backend validates against that exact set (font is a constrained enum,
// not free text, since it's interpolated into the sent email's HTML).
export type FontOption = {
  value: string
  label: string
  category: 'sans' | 'serif'
  cssFamily: string
  googleParam: string
}

export const FONT_OPTIONS: FontOption[] = [
  { value: 'inter', label: 'Inter', category: 'sans', cssFamily: "'Inter',-apple-system,system-ui,sans-serif", googleParam: 'Inter:wght@400;500;600;700' },
  { value: 'ibm_plex_sans', label: 'IBM Plex Sans', category: 'sans', cssFamily: "'IBM Plex Sans',-apple-system,system-ui,sans-serif", googleParam: 'IBM+Plex+Sans:wght@400;500;600;700' },
  { value: 'poppins', label: 'Poppins', category: 'sans', cssFamily: "'Poppins',-apple-system,system-ui,sans-serif", googleParam: 'Poppins:wght@400;500;600;700' },
  { value: 'space_grotesk', label: 'Space Grotesk', category: 'sans', cssFamily: "'Space Grotesk',-apple-system,system-ui,sans-serif", googleParam: 'Space+Grotesk:wght@400;500;600;700' },
  { value: 'dm_sans', label: 'DM Sans', category: 'sans', cssFamily: "'DM Sans',-apple-system,system-ui,sans-serif", googleParam: 'DM+Sans:wght@400;500;600;700' },
  { value: 'lora', label: 'Lora', category: 'serif', cssFamily: "'Lora',Georgia,'Times New Roman',serif", googleParam: 'Lora:wght@400;500;600;700' },
  { value: 'playfair_display', label: 'Playfair Display', category: 'serif', cssFamily: "'Playfair Display',Georgia,'Times New Roman',serif", googleParam: 'Playfair+Display:wght@400;600;700' },
  { value: 'source_serif', label: 'Source Serif 4', category: 'serif', cssFamily: "'Source Serif 4',Georgia,'Times New Roman',serif", googleParam: 'Source+Serif+4:wght@400;500;600;700' },
]

export const DEFAULT_FONT = 'inter'

// Single combined stylesheet URL for every curated font — injected once so
// the picker itself can render each option in its real typeface.
export const FONT_PICKER_STYLESHEET_HREF =
  `https://fonts.googleapis.com/css2?${FONT_OPTIONS.map((f) => `family=${f.googleParam}`).join('&')}&display=swap`

export function fontCssFamily(value: string): string {
  return FONT_OPTIONS.find((f) => f.value === value)?.cssFamily ?? FONT_OPTIONS[0].cssFamily
}
