/** Rich text: a story's paragraphs as the small document the editor types in
 *  (ProseMirror's JSON, through Tiptap) and the server keeps
 *  (services/magazine/rt.py). `cleanRt` keeps what the server keeps, in the
 *  same shape, so a document typed here compares equal to the saved one;
 *  `rtToMd` is the Markdown the server keeps beside it. Both are pinned by
 *  server/tests/cappe/fixtures/magazine_rt_cases.json, which the server's
 *  tests read too. The server checks everything again. */

export type RtMark = { type: 'link'; attrs: { href: string } } | { type: 'bold' | 'italic' | 'strike' | 'underline' }
export type RtInline = { type: 'text'; text: string; marks?: RtMark[] } | { type: 'hardBreak' }
export type RtBlock =
  | { type: 'paragraph'; content?: RtInline[] }
  | { type: 'heading'; attrs: { level: 2 | 3 }; content?: RtInline[] }
  | { type: 'blockquote'; content: RtBlock[] }
  | { type: 'bulletList'; content: RtItem[] }
  | { type: 'orderedList'; attrs: { start: number }; content: RtItem[] }
export type RtItem = { type: 'listItem'; content: RtBlock[] }
export type RtDoc = { type: 'doc'; content: RtBlock[] }

const BLOCKS = ['paragraph', 'heading', 'blockquote', 'bulletList', 'orderedList', 'listItem']
const MARKS = ['link', 'bold', 'italic', 'strike', 'underline'] as const
const LINK = /^(https?:\/\/|mailto:)/i
const MAX_DEPTH = 6

type Raw = Record<string, unknown>
const obj = (v: unknown): Raw | null => (v && typeof v === 'object' && !Array.isArray(v) ? v as Raw : null)
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : [])

export const emptyRt = (): RtDoc => ({ type: 'doc', content: [{ type: 'paragraph' }] })

/** A link the page may keep: http(s) or mailto, no control characters. */
export function cleanHref(v: unknown): string | null {
  const href = typeof v === 'string' ? v.trim() : ''
  // eslint-disable-next-line no-control-regex -- control characters are what this refuses
  return href && href.length <= 2000 && LINK.test(href) && !/[\u0000-\u001f]/.test(href) ? href : null
}

function marks(raw: unknown): RtMark[] {
  const out: RtMark[] = []
  for (const m of list(raw)) {
    const kind = obj(m)?.type
    if (!MARKS.includes(kind as typeof MARKS[number]) || out.some((x) => x.type === kind)) continue
    if (kind === 'link') {
      const href = cleanHref(obj(obj(m)?.attrs)?.href)
      if (href) out.push({ type: 'link', attrs: { href } })
    } else out.push({ type: kind as 'bold' })
  }
  return out.sort((a, b) => MARKS.indexOf(a.type) - MARKS.indexOf(b.type))
}

class Budget {
  chars: number
  constructor(chars: number) { this.chars = chars }
}

function inline(raw: unknown, budget: Budget, depth = 0): RtInline[] {
  const out: RtInline[] = []
  if (depth > MAX_DEPTH) return out
  for (const n of list(raw)) {
    const node = obj(n)
    if (!node) continue
    if (node.type === 'hardBreak') { out.push({ type: 'hardBreak' }); continue }
    if (node.type === 'text') {
      const text = (typeof node.text === 'string' ? node.text : '').replace(/\r/g, '').slice(0, Math.max(budget.chars, 0))
      if (!text) continue
      budget.chars -= text.length
      const ms = marks(node.marks)
      const last = out[out.length - 1]
      // Neighbours with the same marks are one run.
      if (last?.type === 'text' && JSON.stringify(last.marks ?? null) === JSON.stringify(ms.length ? ms : null)) last.text += text
      else out.push(ms.length ? { type: 'text', text, marks: ms } : { type: 'text', text })
    } else if (Array.isArray(node.content)) out.push(...inline(node.content, budget, depth + 1))
  }
  return out
}

function block(n: unknown, budget: Budget, depth: number): RtBlock[] {
  const node = obj(n)
  if (!node || depth > MAX_DEPTH) return []
  const content = node.content
  switch (node.type) {
    case 'paragraph': {
      const words = inline(content, budget)
      return [words.length ? { type: 'paragraph', content: words } : { type: 'paragraph' }]
    }
    case 'heading': {
      const words = inline(content, budget)
      const level = [3, 4, 5, 6].includes(obj(node.attrs)?.level as number) ? 3 : 2
      return [{ type: 'heading', attrs: { level }, ...(words.length ? { content: words } : {}) }]
    }
    case 'blockquote': {
      const inner = blocks(content, budget, depth + 1, { quote: true })
      return inner.length ? [{ type: 'blockquote', content: inner }] : []
    }
    case 'bulletList': case 'orderedList': {
      const items: RtItem[] = []
      for (const item of list(content)) {
        if (!obj(item)) continue
        const inner = blocks(obj(item)!.content, budget, depth + 1, { item: true })
        if (inner.length) items.push({ type: 'listItem', content: inner })
      }
      if (!items.length) return []
      if (node.type === 'bulletList') return [{ type: 'bulletList', content: items }]
      const start = obj(node.attrs)?.start
      return [{ type: 'orderedList', attrs: { start: Number.isInteger(start) && (start as number) >= 1 && (start as number) <= 9999 ? start as number : 1 }, content: items }]
    }
    default: {
      // A block we don't keep keeps its words, as paragraphs.
      if (list(content).some((c) => BLOCKS.includes(obj(c)?.type as string))) return blocks(content, budget, 1)
      const words = inline(content, budget)
      return words.length ? [{ type: 'paragraph', content: words }] : []
    }
  }
}

function blocks(raw: unknown, budget: Budget, depth: number, where: { quote?: boolean; item?: boolean } = {}): RtBlock[] {
  const out: RtBlock[] = []
  for (const n of list(raw)) {
    for (let b of block(n, budget, depth)) {
      // A list item opens with a paragraph; a quote holds no headings.
      if (where.item && !out.length && b.type !== 'paragraph') out.push({ type: 'paragraph' })
      if (where.quote && b.type === 'heading') b = b.content ? { type: 'paragraph', content: b.content } : { type: 'paragraph' }
      out.push(b)
    }
  }
  return out
}

/** The document as the server will keep it, or null when `raw` isn't one. */
export function cleanRt(raw: unknown, maxChars = 20_000): RtDoc | null {
  const d = obj(raw)
  if (!d || d.type !== 'doc') return null
  const content = blocks(d.content, new Budget(maxChars), 0)
  return { type: 'doc', content: content.length ? content : [{ type: 'paragraph' }] }
}

/** The words alone, a space between blocks. */
export function rtText(doc: RtDoc | null | undefined): string {
  const walk = (nodes: unknown[]): string[] => nodes.flatMap((n) => {
    const node = obj(n)
    if (!node) return []
    if (node.type === 'text') return [String(node.text ?? '')]
    if (node.type === 'hardBreak') return [' ']
    const inner = walk(list(node.content)).join('')
    return BLOCKS.includes(node.type as string) ? [inner, ' '] : [inner]
  })
  return doc ? walk(doc.content).join('').replace(/\s+/g, ' ').trim() : ''
}

// ── Markdown (as rt.py's rt_to_md) ──────────────────────────────────────────

const escMd = (s: string) => s.replace(/\u00a0/g, ' ').replace(/([\\`*_[\]])/g, '\\$1')

function escLineStart(line: string): string {
  return line
    .replace(/^(\s*)(#{1,6})(\s|$)/, '$1\\$2$3')
    .replace(/^(\s*)>/, '$1\\>')
    .replace(/^(\s*)([-+])(\s)/, '$1\\$2$3')
    .replace(/^(\s*)(\d+)\.(\s)/, '$1$2\\.$3')
}

function wrap(inner: string, mark: string): string {
  const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(inner)
  return m && m[2] ? `${m[1]}${mark}${m[2]}${mark}${m[3]}` : inner
}

function mdInline(nodes: RtInline[]): string {
  const out = nodes.map((n) => {
    if (n.type === 'hardBreak') return '  \n'
    let md = escMd(n.text.replace(/\n/g, ' '))
    const kinds = (n.marks ?? []).map((m) => m.type)
    if (kinds.includes('italic')) md = wrap(md, '*')
    if (kinds.includes('bold')) md = wrap(md, '**')
    const link = n.marks?.find((m) => m.type === 'link') as Extract<RtMark, { type: 'link' }> | undefined
    if (link && md.trim()) {
      md = `[${md}](${link.attrs.href.replace(/\(/g, '%28').replace(/\)/g, '%29').replace(/ /g, '%20')})`
    }
    return md
  })
  return out.join('').trimEnd().split('\n').map(escLineStart).join('\n').trim()
}

function mdBlock(b: RtBlock): string {
  switch (b.type) {
    case 'paragraph': return mdInline(b.content ?? [])
    case 'heading': {
      const words = mdInline(b.content ?? []).replace(/\n/g, ' ')
      return words ? `${'#'.repeat(b.attrs.level)} ${words}` : ''
    }
    case 'blockquote': {
      const inner = b.content.map(mdBlock).filter(Boolean).join('\n\n')
      return inner ? inner.split('\n').map((l) => (l ? `> ${l}` : '>')).join('\n') : ''
    }
    default: {
      const start = b.type === 'orderedList' ? b.attrs.start : 1
      return b.content.flatMap((item, i) => {
        const words = item.content.map((c) => mdBlock(c).replace(/\n/g, ' ')).filter(Boolean).join(' ').trim()
        return words ? [b.type === 'orderedList' ? `${start + i}. ${words}` : `- ${words}`] : []
      }).join('\n')
    }
  }
}

/** The Markdown the server keeps beside a document (emails, feeds, word
 *  counts, the iOS app). Underline and strike-through have none. */
export function rtToMd(doc: RtDoc | null | undefined): string {
  return doc ? doc.content.map(mdBlock).filter(Boolean).join('\n\n') : ''
}

/** What a rich field changes to: its document and the Markdown kept beside
 *  it, within the field's length. */
export function richPatch(doc: unknown, max: number): { rt: RtDoc; md: string } {
  const rt = cleanRt(doc, max) ?? emptyRt()
  return { rt, md: rtToMd(rt).slice(0, max) }
}
