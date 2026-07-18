import type { PlaceholderInfo } from './types'

/** Extract [bracketed] placeholders with surrounding context for friendly labels */
export function extractPlaceholders(html: string): PlaceholderInfo[] {
  const text = html.replace(/<[^>]+>/g, '').replace(/\n/g, ' ')
  const results: PlaceholderInfo[] = []
  const seen = new Set<string>()
  const regex = /\[([^\]]+)\]/g
  let match
  while ((match = regex.exec(text)) !== null) {
    if (seen.has(match[0])) continue
    seen.add(match[0])
    // Grab surrounding words for context
    const before = text.slice(Math.max(0, match.index - 40), match.index).trim().split(/\s+/).slice(-4).join(' ')
    const after = text.slice(match.index + match[0].length, match.index + match[0].length + 40).trim().split(/\s+/).slice(0, 4).join(' ')
    const name = match[1]
    // Build a contextual label
    let label = name
    if (before || after) {
      label = `${before} ___${name}___ ${after}`.trim()
    }
    results.push({ placeholder: match[0], label })
  }
  return results
}
