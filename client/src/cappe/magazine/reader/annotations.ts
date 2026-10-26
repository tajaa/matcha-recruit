import type { ReaderAnnotation, ReaderQuote } from './annotationTypes'

/** No listeners inside a script-less iframe: Safari won't deliver them. */
export function readerRoot(doc: Document): HTMLElement | null {
  return doc.querySelector('[data-lyt-strip], article.mz-story, .mz-story, article')
}

function index(root: HTMLElement) {
  const walker = root.ownerDocument.createTreeWalker(root, 4 /* SHOW_TEXT */)
  const nodes: { node: Text; start: number; end: number }[] = []
  let text = '', node: Node | null
  while ((node = walker.nextNode())) {
    if (node.parentElement?.closest('script,style,noscript')) continue
    const start = text.length
    text += node.textContent || ''
    nodes.push({ node: node as Text, start, end: text.length })
  }
  return { text, nodes }
}

/** Context disambiguates repeated phrases. Ambiguous or deleted words stay
 * in the notebook, without painting a different passage after publication. */
export function locateQuote(text: string, q: ReaderQuote): number | null {
  const context = (at: number) => (!q.prefix || text.slice(Math.max(0, at - q.prefix.length), at) === q.prefix)
    && (!q.suffix || text.slice(at + q.exact.length, at + q.exact.length + q.suffix.length) === q.suffix)
  if (text.slice(q.start, q.start + q.exact.length) === q.exact && context(q.start)) return q.start
  let at = text.indexOf(q.exact), contextual: number | null = null
  let contextCount = 0
  while (at >= 0) {
    if (context(at)) { contextCount++; contextual = at }
    at = text.indexOf(q.exact, at + 1)
  }
  return contextCount === 1 ? contextual : null
}

export function selectedQuote(doc: Document): ReaderQuote | null {
  const root = readerRoot(doc), sel = doc.getSelection()
  if (!root || !sel || sel.isCollapsed || !sel.rangeCount) return null
  const range = sel.getRangeAt(0)
  if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return null
  const exact = range.toString()
  if (!exact.trim() || Array.from(exact).length > 2000) return null
  const before = doc.createRange()
  before.selectNodeContents(root)
  before.setEnd(range.startContainer, range.startOffset)
  const start = before.toString().length, { text } = index(root)
  if (text.slice(start, start + exact.length) !== exact) return null
  // Whole characters in context even when an emoji straddles the boundary.
  return { exact, start, prefix: Array.from(text.slice(0, start)).slice(-32).join(''),
    suffix: Array.from(text.slice(start + exact.length)).slice(0, 32).join('') }
}

/** Paint by splitting text nodes only. Inline marks preserve the publisher's
 * layout, including composed Studio spans; no HTML from a note is inserted. */
export function paintAnnotations(doc: Document, annotations: ReaderAnnotation[]): Set<string> {
  const root = readerRoot(doc), found = new Set<string>()
  if (!root) return found
  root.querySelectorAll('[data-reader-note]').forEach((el) => el.replaceWith(...el.childNodes))
  root.normalize()
  const { text, nodes } = index(root)
  const ranges = annotations.flatMap((a) => {
    if (!a.quote) return []
    const start = locateQuote(text, a.quote)
    if (start === null) return []
    found.add(a.id)
    return [{ start, end: start + a.quote.exact.length, annotation: a }]
  })
  for (const { node, start, end } of nodes) {
    const hits = ranges.filter((r) => r.start < end && r.end > start)
    if (!hits.length) continue
    const cuts = [...new Set([0, end - start, ...hits.flatMap((r) => [Math.max(0, r.start - start), Math.min(end - start, r.end - start)])])].sort((a, b) => b - a)
    for (let i = 0; i < cuts.length - 1; i++) {
      const hi = cuts[i], lo = cuts[i + 1]
      const active = hits.filter((r) => r.start < start + hi && r.end > start + lo)
      const piece = lo ? node.splitText(lo) : node
      if (!active.length) continue
      let child: Node = piece
      for (const { annotation: a } of active) {
        const mark = doc.createElement('span')
        mark.setAttribute('data-reader-note', a.id)
        mark.style.cssText = a.kind === 'underline'
          ? 'text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:3px'
          : `background:rgba(250,204,21,${a.kind === 'comment' ? '.22' : '.45'});box-decoration-break:clone`
        child.parentNode?.insertBefore(mark, child)
        mark.appendChild(child)
        child = mark
      }
    }
  }
  return found
}

export function pageAt(doc: Document): number {
  const strip = doc.querySelector<HTMLElement>('[data-lyt-strip]')
  if (strip) {
    const left = strip.getBoundingClientRect().left
    const pages = Array.from(strip.querySelectorAll<HTMLElement>('.lyt-paper'))
    const visible = pages.find((p) => p.getBoundingClientRect().right > left + 2)
    return Number(visible?.getAttribute('data-lyt-n')) || 1
  }
  const book = doc.querySelector<HTMLElement>('.mz-book'), pages = doc.querySelector<HTMLElement>('.mz-pages')
  const per = pages && doc.defaultView ? parseInt(doc.defaultView.getComputedStyle(pages).columnCount, 10) || 1 : 1
  return book ? Math.round(book.scrollLeft / (book.clientWidth || 1)) * per + 1 : 1
}

/** A selected passage can start on the right page of a desktop spread. */
export function selectionPageAt(doc: Document): number {
  const sel = doc.getSelection()
  if (!sel?.rangeCount) return pageAt(doc)
  const range = sel.getRangeAt(0), node = range.startContainer
  const element = node.nodeType === 1 ? node as Element : node.parentElement
  const paper = element?.closest('.lyt-page, .lyt-paper')
  if (paper) return Number(paper.getAttribute('data-lyt-page') || paper.getAttribute('data-lyt-n')) || pageAt(doc)
  const book = doc.querySelector<HTMLElement>('.mz-book'), pages = doc.querySelector<HTMLElement>('.mz-pages')
  const rect = Array.from(range.getClientRects?.() ?? []).find((r) => r.height > 0)
  if (!book || !pages || !rect || !doc.defaultView) return pageAt(doc)
  const per = parseInt(doc.defaultView.getComputedStyle(pages).columnCount, 10) || 1
  const pad = parseFloat(doc.defaultView.getComputedStyle(book).paddingLeft) || 0
  return Math.max(1, Math.floor((rect.left - book.getBoundingClientRect().left + book.scrollLeft - pad + 2)
    / ((book.clientWidth || 1) / per)) + 1)
}

/** Jump to quoted text when available; page comments use their printed page.
 * BookFrame's own polling settles the book and updates its normal controls. */
export function jumpToAnnotation(doc: Document, a: ReaderAnnotation) {
  const marker = doc.querySelector<HTMLElement>(`[data-reader-note="${a.id}"]`)
  if (marker) { marker.scrollIntoView?.({ block: 'center', inline: 'center' }); return }
  const strip = doc.querySelector<HTMLElement>('[data-lyt-strip]')
  if (strip) {
    strip.querySelector<HTMLElement>(`.lyt-paper[data-lyt-n="${a.page}"]`)?.scrollIntoView?.({ block: 'nearest', inline: 'start' })
    return
  }
  const book = doc.querySelector<HTMLElement>('.mz-book'), pages = doc.querySelector<HTMLElement>('.mz-pages')
  const per = pages && doc.defaultView ? parseInt(doc.defaultView.getComputedStyle(pages).columnCount, 10) || 1 : 1
  if (book) book.scrollLeft = Math.floor((a.page - 1) / per) * book.clientWidth
}
