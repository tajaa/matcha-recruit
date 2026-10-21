/** Page turning for a story shown in one of our script-less frames (the
 *  editor's preview and "View as a reader": `sandbox="allow-same-origin"`, so
 *  the page's own `book.js` can't run, but we can reach its document).
 *
 *  Keep in step with server/app/cappe/services/render/assets/book.js, which
 *  does the same on the live site: a spread is the book's width; arrows, the
 *  ←/→/Page keys and a settled swipe turn it; the page count follows. */
export type BookControl = { dispose: () => void }

/** `start` is the spread to open on; `onTurn` hears each spread shown. */
export function wireBook(doc: Document | null | undefined, start = 0, onTurn?: (spread: number) => void): BookControl | null {
  const win = doc?.defaultView
  const box = doc?.querySelector('[data-mz-book]')
  const book = box?.querySelector<HTMLElement>('.mz-book')
  const pages = box?.querySelector<HTMLElement>('.mz-pages')
  const prev = box?.querySelector<HTMLButtonElement>('[data-mz-prev]')
  const next = box?.querySelector<HTMLButtonElement>('[data-mz-next]')
  const folio = box?.querySelector<HTMLElement>('[data-mz-folio]')
  if (!doc || !win || !book || !pages || !prev || !next || !folio) return null

  const width = () => book.clientWidth || 1
  const perSpread = () => Math.max(1, parseInt(win.getComputedStyle(pages).columnCount, 10) || 1)
  const spreads = () => Math.max(1, Math.round(book.scrollWidth / width()))
  const at = () => Math.min(spreads() - 1, Math.round(book.scrollLeft / width()))
  const show = () => {
    const i = at(), n = spreads(), per = perSpread(), total = n * per
    const first = i * per + 1, last = Math.min(total, first + per - 1)
    prev.hidden = i <= 0
    next.hidden = i >= n - 1
    folio.textContent = n > 1 ? `${first === last ? `Page ${first}` : `Pages ${first}–${last}`} of ${total}` : ''
    onTurn?.(i)
  }
  const go = (i: number) => {
    const to = Math.max(0, Math.min(spreads() - 1, i)) * width()
    if (typeof book.scrollTo === 'function') book.scrollTo({ left: to, behavior: 'smooth' })
    else book.scrollLeft = to
    show()
  }
  const onPrev = () => go(at() - 1)
  const onNext = () => go(at() + 1)
  const onKey = (e: KeyboardEvent) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return
    if (e.key === 'ArrowRight' || e.key === 'PageDown') { e.preventDefault(); onNext() }
    else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); onPrev() }
  }
  let settle: ReturnType<typeof setTimeout> | undefined
  const onScroll = () => {
    show()
    clearTimeout(settle)
    settle = setTimeout(() => { if (Math.abs(book.scrollLeft - at() * width()) > 2) go(at()) }, 140)
  }
  prev.addEventListener('click', onPrev)
  next.addEventListener('click', onNext)
  doc.addEventListener('keydown', onKey)
  book.addEventListener('scroll', onScroll, { passive: true })
  book.scrollLeft = Math.min(start, spreads() - 1) * width()
  show()
  return {
    dispose: () => {
      clearTimeout(settle)
      prev.removeEventListener('click', onPrev)
      next.removeEventListener('click', onNext)
      doc.removeEventListener('keydown', onKey)
      book.removeEventListener('scroll', onScroll)
    },
  }
}
