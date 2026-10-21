/** Markdown formatting for the editor's toolbar. Each takes the text and the
 *  selection and returns the new text and what to select after, so the writer
 *  can keep typing. Only what the server renders (services/magazine/richtext:
 *  bold, italic, links, h2/h3, quotes, lists). */

export type MdFormat = 'bold' | 'italic' | 'h2' | 'h3' | 'quote' | 'bullets' | 'numbers' | 'link'
export type MdEdit = { value: string; start: number; end: number }

const WRAP: Partial<Record<MdFormat, [string, string, string]>> = {
  bold: ['**', '**', 'bold words'],
  italic: ['*', '*', 'italic words'],
}

const PREFIX: Partial<Record<MdFormat, string>> = { h2: '## ', h3: '### ', quote: '> ', bullets: '- ' }

const LINE_MARK = /^(#{1,6} |> |- |\* |\d+\. )/

export function formatMarkdown(value: string, start: number, end: number, kind: MdFormat): MdEdit {
  const wrap = WRAP[kind]
  if (wrap) {
    const [open, close, placeholder] = wrap
    const picked = value.slice(start, end)
    // Already wrapped: take the marks off.
    if (picked && value.slice(start - open.length, start) === open && value.slice(end, end + close.length) === close
      && !(open === '*' && value.slice(start - 2, start) === '**')) {
      return { value: value.slice(0, start - open.length) + picked + value.slice(end + close.length), start: start - open.length, end: end - open.length }
    }
    const words = picked || placeholder
    return { value: value.slice(0, start) + open + words + close + value.slice(end), start: start + open.length, end: start + open.length + words.length }
  }
  if (kind === 'link') {
    const words = value.slice(start, end) || 'link words'
    const inserted = `[${words}](https://)`
    const urlAt = start + words.length + 3
    return { value: value.slice(0, start) + inserted + value.slice(end), start: urlAt, end: urlAt + 'https://'.length }
  }
  // A line format: every line the selection touches.
  const from = value.lastIndexOf('\n', start - 1) + 1
  const nl = value.indexOf('\n', end > start && value[end - 1] === '\n' ? end - 1 : end)
  const to = nl === -1 ? value.length : nl
  const lines = value.slice(from, to).split('\n')
  const mark = (i: number) => (kind === 'numbers' ? `${i + 1}. ` : PREFIX[kind]!)
  const has = lines.every((l, i) => (kind === 'numbers' ? /^\d+\. /.test(l) : l.startsWith(mark(i))))
  const out = lines.map((l, i) => (has ? l.replace(LINE_MARK, '') : mark(i) + l.replace(LINE_MARK, ''))).join('\n')
  return { value: value.slice(0, from) + out + value.slice(to), start: from, end: from + out.length }
}

/** The format a keyboard shortcut asks for: ⌘B, ⌘I, ⌘K. */
export function shortcutFormat(e: { key: string; metaKey: boolean; ctrlKey: boolean; shiftKey: boolean; altKey: boolean }): MdFormat | null {
  if (!(e.metaKey || e.ctrlKey) || e.shiftKey || e.altKey) return null
  const k = e.key.toLowerCase()
  return k === 'b' ? 'bold' : k === 'i' ? 'italic' : k === 'k' ? 'link' : null
}
