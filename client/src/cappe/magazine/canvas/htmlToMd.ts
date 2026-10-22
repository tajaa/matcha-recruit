/** Words typed on the page with the toolbar (HTML, from the frame) as the
 *  constrained Markdown a story stores and the server renders
 *  (services/magazine/richtext.py): paragraphs, bold, italic, links, h2, h3,
 *  quotes and lists, nothing else. The HTML is parsed, never run, and any
 *  other tag keeps only its words. Characters Markdown would read as
 *  formatting are escaped, so what was typed is what is shown.
 *  server/tests/cappe/fixtures/magazine_md_cases.json pins the conversions:
 *  canvas.test.ts checks HTML → Markdown, the server's
 *  test_cappe_magazine_canvas.py checks Markdown → the HTML it renders. */

const BLOCKS = new Set(['P', 'DIV', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'BLOCKQUOTE', 'UL', 'OL', 'LI', 'SECTION', 'ARTICLE'])
const LINK = /^(https?:\/\/|mailto:)/i
const URL_ESCAPES: Record<string, string> = { '(': '%28', ')': '%29' }

/** Markdown's own characters in typed words, made literal. */
export function escapeMd(text: string): string {
  return text.replace(/([\\`*_[\]])/g, '\\$1')
}

/** What would start a heading, a quote or a list at the start of a line. */
function escapeLineStart(line: string): string {
  return line
    .replace(/^(\s*)(#{1,6})(\s|$)/, '$1\\$2$3')
    .replace(/^(\s*)>/, '$1\\>')
    .replace(/^(\s*)([-+])(\s)/, '$1\\$2$3')
    .replace(/^(\s*)(\d+)\.(\s)/, '$1$2\\.$3')
}

const space = (s: string) => s.replace(/\u00a0/g, ' ')

/** Marks around words, with the spaces at either end kept outside them
 *  (`**word **` would not read as bold). */
function wrap(inner: string, mark: string): string {
  const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(inner)!
  return m[2] ? `${m[1]}${mark}${m[2]}${mark}${m[3]}` : inner
}

function inline(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) return escapeMd(space(node.nodeValue || '').replace(/[\r\n]+/g, ' '))
  if (node.nodeType !== Node.ELEMENT_NODE) return ''
  const el = node as Element
  const inner = () => Array.from(el.childNodes).map(inline).join('')
  switch (el.tagName) {
    case 'BR': return '  \n'
    case 'SCRIPT': case 'STYLE': case 'TEMPLATE': return ''
    case 'B': case 'STRONG': return wrap(inner(), '**')
    case 'I': case 'EM': return wrap(inner(), '*')
    case 'A': {
      const href = (el.getAttribute('href') || '').trim()
      const words = inner()
      return LINK.test(href) && words.trim() ? `[${words}](${href.replace(/[()\s]/g, (c) => URL_ESCAPES[c] || '%20')})` : words
    }
    default: return inner()
  }
}

/** A paragraph's lines, each made safe at its start and stripped of the line
 *  break a field ends with. */
function lines(md: string): string {
  return md.replace(/( {2}\n)+$/, '').split('\n').map((l) => escapeLineStart(l)).join('\n').trim()
}

function blocks(parent: Node): string[] {
  const out: string[] = []
  let run: Node[] = []
  const flush = () => {
    const text = lines(run.map(inline).join(''))
    if (text) out.push(text)
    run = []
  }
  for (const node of Array.from(parent.childNodes)) {
    const el = node.nodeType === Node.ELEMENT_NODE ? (node as Element) : null
    if (!el || !BLOCKS.has(el.tagName)) { run.push(node); continue }
    flush()
    switch (el.tagName) {
      case 'H1': case 'H2': { const t = lines(inline(el)); if (t) out.push(`## ${t.replace(/\n/g, ' ')}`); break }
      case 'H3': case 'H4': case 'H5': case 'H6': { const t = lines(inline(el)); if (t) out.push(`### ${t.replace(/\n/g, ' ')}`); break }
      case 'BLOCKQUOTE': {
        const inner = blocks(el)
        if (inner.length) out.push(inner.join('\n\n').split('\n').map((l) => (l ? `> ${l}` : '>')).join('\n'))
        break
      }
      case 'UL': case 'OL': {
        const md = list(el)
        if (md) out.push(md)
        break
      }
      default: out.push(...blocks(el))
    }
  }
  flush()
  return out
}

/** A list's own (unescaped) start: a nested list among an item's blocks. */
const LIST_START = /^(- |\d+\. )/
const indent = (md: string) => md.split('\n').map((l) => (l ? `    ${l}` : l)).join('\n')

/** A list, nesting and all: an item's later blocks are indented four spaces
 *  under it (a nested list right after its first line, a paragraph after a
 *  blank line), as Python-Markdown (richtext.render_md) reads them. A list
 *  WebKit puts beside an item rather than in it belongs to that item. */
function list(el: Element): string {
  const items: string[][] = []
  for (const child of Array.from(el.children)) {
    if (child.tagName === 'LI') items.push(blocks(child))
    else if (child.tagName === 'UL' || child.tagName === 'OL') {
      const nested = list(child)
      if (!nested) continue
      if (items.length) items[items.length - 1].push(nested)
      else items.push([nested])
    }
  }
  const kept = items.filter((parts) => parts.length)
  // An item with a paragraph after its first: the items are set apart by a
  // blank line (else the next one reads as part of that paragraph).
  const loose = kept.some((parts) => parts.slice(1).some((p) => !LIST_START.test(p)))
  return kept.map((parts, i) => {
    const [first, ...rest] = parts
    const head = `${el.tagName === 'OL' ? `${i + 1}.` : '-'} ${first.replace(/\n/g, '\n    ')}`
    return head + rest.map((p) => (LIST_START.test(p) ? `\n${indent(p)}` : `\n\n${indent(p)}`)).join('')
  }).join(loose ? '\n\n' : '\n')
}

/** The Markdown for a rich field's HTML ("" when nothing is in it). */
export function htmlToMd(html: string): string {
  const doc = new DOMParser().parseFromString(`<body>${html}</body>`, 'text/html')
  return blocks(doc.body).join('\n\n')
}
