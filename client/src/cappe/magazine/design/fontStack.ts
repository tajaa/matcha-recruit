import { FONTS, type FontCategory } from './fonts'

/** What a face falls back to while it loads, or if it can't (as fonts.py). */
const GENERIC: Record<FontCategory, string> = {
  serif: "Georgia, 'Times New Roman', serif",
  sans: "system-ui, -apple-system, 'Segoe UI', sans-serif",
  display: 'system-ui, -apple-system, sans-serif',
  mono: 'ui-monospace, Menlo, monospace',
  handwriting: 'cursive',
}

/** The magazine's own pair (its masthead style), what text is set in until
 *  the writer picks a face. */
export const ROLES: Record<string, string> = { heading: 'var(--mz-h)', body: 'var(--mz-b)' }

export const FONT_BY_NAME = new Map(FONTS.map((f) => [f.name, f]))

export function fontStack(name: string): string {
  if (ROLES[name]) return ROLES[name]
  return `'${name}', ${GENERIC[FONT_BY_NAME.get(name)?.cat ?? 'sans']}`
}

const ALL_WEIGHTS = [100, 200, 300, 400, 500, 600, 700, 800, 900]

/** The weights a face has (the magazine's own pair: any, as its face allows). */
export const weightsOf = (name: string) => FONT_BY_NAME.get(name)?.w ?? ALL_WEIGHTS

/** The nearest weight a face has; ties go to the heavier (as fonts.py). */
export function nearestWeight(name: string, weight: number): number {
  return weightsOf(name).reduce((best, w) => {
    const d = Math.abs(w - weight), bd = Math.abs(best - weight)
    return d < bd || (d === bd && w > best) ? w : best
  })
}

export const hasItalic = (name: string, weight: number) => !!ROLES[name] || (FONT_BY_NAME.get(name)?.i ?? []).includes(weight)

/** The stylesheet that loads a face's regular style and the weights asked
 *  for (as fonts.fonts_links), for the editor to load a face once picked. */
export function fontHref(name: string, styles: { weight: number; italic: boolean }[]): string | null {
  const f = FONT_BY_NAME.get(name)
  if (!f) return null
  const set = new Set(['0,400'])
  for (const s of styles) {
    if (f.w.includes(s.weight)) set.add(`0,${s.weight}`)
    if (s.italic && f.i.includes(s.weight)) set.add(`1,${s.weight}`)
  }
  const spec = [...set].map((x) => x.split(',').map(Number)).sort((a, b) => a[0] - b[0] || a[1] - b[1]).map((x) => x.join(',')).join(';')
  return `https://fonts.googleapis.com/css2?family=${encodeURIComponent(name)}:ital,wght@${spec}&display=swap`
}
