/** Page turning for a story shown in one of our script-less frames (the
 *  editor's preview, "View as a reader", a reader's dashboard:
 *  `sandbox="allow-same-origin"`, so the page's own `book.js` can't run).
 *
 *  Nothing here listens inside the frame. Safari never calls a listener that
 *  the page outside adds to a sandboxed, script-less document (Chrome and
 *  Firefox do), so the arrows, keys and page count live outside
 *  (`BookFrame.tsx`). This reads and scrolls the frame's pages, and watches
 *  them for a swipe to settle.
 *
 *  Keep in step with server/app/cappe/services/render/assets/book.js, which
 *  does the same on the live site: a spread is the book's width; a swipe that
 *  stops part-way turns to the page it was heading for once it has gone
 *  FLICK of a spread, else springs back; `data-mz-at` marks the spread (0 is
 *  the matte cover, no gloss). */
export type BookState = { spread: number; spreads: number; folio: string }
export type BookControl = {
  turn: (delta: number) => void
  go: (spread: number) => void
  state: () => BookState
  dispose: () => void
}

export const FLICK = 0.06
/** How often the pages are looked at: a scroll in the frame can't tell us. */
export const POLL_MS = 80
/** Measure the pages again every this many looks (about a second). */
const REFIT_TICKS = 12

/** `start` is the spread to open on; `onState` hears each change of spread
 *  or page count. Null for a page that isn't a book (a front page). */
export function wireBook(doc: Document | null | undefined, { start = 0, onState }: {
  start?: number
  onState?: (state: BookState) => void
} = {}): BookControl | null {
  const win = doc?.defaultView
  const box = doc?.querySelector<HTMLElement>('[data-mz-book]')
  const book = box?.querySelector<HTMLElement>('.mz-book')
  const pages = box?.querySelector<HTMLElement>('.mz-pages')
  if (!doc || !win || !box || !book || !pages) return null

  const end = box.querySelector<HTMLElement>('.mz-end')
  const width = () => book.clientWidth || 1
  const perSpread = () => Math.max(1, parseInt(win.getComputedStyle(pages).columnCount, 10) || 1)
  // A browser never counts the space after the last column, so the pages are
  // measured and `.mz-end` moved to make them end on a whole spread; `count`
  // is the pages actually printed.
  let spreads = 1, count = 1
  const story = pages.firstElementChild
  // Where the last column ends, from the story's own column pieces (measuring
  // changes nothing, so the reader's place never moves).
  const extent = () => {
    const box = book.getBoundingClientRect()
    let x = 0
    for (const r of Array.from(story?.getClientRects() ?? [])) x = Math.max(x, r.right - box.left + book.scrollLeft)
    return x || book.scrollWidth
  }
  const fit = () => {
    const w = width(), per = perSpread(), pad = parseFloat(win.getComputedStyle(book).paddingLeft) || 0, x = extent()
    spreads = Math.max(1, Math.ceil((x - 1) / w))
    count = Math.max(1, Math.min(spreads * per, Math.round((x + pad) / (w / per))))
    if (end) end.style.left = `${spreads * w - pad - 1}px`
  }
  const clamp = (i: number) => Math.max(0, Math.min(spreads - 1, i))
  const at = () => clamp(Math.round(book.scrollLeft / width()))
  const state = (): BookState => {
    const i = at(), per = perSpread()
    const first = i * per + 1, last = Math.min(count, first + per - 1)
    return { spread: i, spreads, folio: spreads > 1 ? `${first === last ? `Page ${first}` : `Pages ${first}–${last}`} of ${count}` : '' }
  }

  fit()
  let cur = clamp(start), lastLeft = -1, still = 0, lastWidth = width(), told = '', ticks = 0
  const emit = () => {
    const s = state()
    box.setAttribute('data-mz-at', String(s.spread))
    const key = `${s.spread}|${s.spreads}|${s.folio}`
    if (key !== told) { told = key; onState?.(s) }
  }
  const go = (i: number) => {
    cur = clamp(i)
    const to = cur * width()
    if (Math.abs(book.scrollLeft - to) > 2) {
      if (typeof book.scrollTo === 'function') book.scrollTo({ left: to, behavior: 'smooth' })
      else book.scrollLeft = to
    }
    emit()
  }
  // Where the pages came to rest: on a spread (a turn we made ends there),
  // or part-way through a swipe, to settle.
  const rest = () => {
    const w = width(), off = book.scrollLeft - cur * w
    if (Math.abs(off) <= 2) { emit(); return }
    go(Math.abs(off) >= w / 2 ? Math.round(book.scrollLeft / w) : Math.abs(off) > w * FLICK ? cur + Math.sign(off) : cur)
  }
  const tick = () => {
    const w = width()
    // The page changed size, or (every so often) pictures and fonts arrived.
    if (w !== lastWidth || ++ticks % REFIT_TICKS === 0) {
      const moved = w !== lastWidth
      lastWidth = w
      fit()
      if (moved) { cur = clamp(cur); book.scrollLeft = cur * w; lastLeft = book.scrollLeft }
      emit()
      if (moved) return
    }
    const left = book.scrollLeft
    if (left !== lastLeft) { lastLeft = left; still = 0; emit(); return }
    if (++still === 2) rest()
  }

  book.scrollLeft = cur * width()
  lastLeft = book.scrollLeft
  emit()
  const timer = setInterval(tick, POLL_MS)
  return { turn: (delta) => go(cur + delta), go, state, dispose: () => clearInterval(timer) }
}

/** Where a link in the frame goes: a blank page whose fragment names it.
 *  Following it fires the frame's `load` (which Safari does deliver to the
 *  page outside), and `followedLink` reads it back. */
export const LINK_PREFIX = 'about:blank#mz-link='

/** Ready a frame's page to be driven from outside: its own arrows and page
 *  count hidden, and every link pointed where it should go. Without `follow`
 *  the page's own links do nothing. `openExternal`: web and mail links open
 *  in a new tab (the frame then needs `allow-popups`). */
export function prepareFrame(doc: Document | null | undefined, { follow, openExternal = false }: {
  follow: boolean
  openExternal?: boolean
}): void {
  if (!doc?.head) return
  const style = doc.createElement('style')
  style.textContent = '.mz-turn,[data-mz-folio]{display:none!important}'
  doc.head.appendChild(style)
  doc.querySelectorAll('a[href]').forEach((a) => {
    const href = a.getAttribute('href') || ''
    if (/^(https?:|mailto:)/i.test(href)) {
      if (openExternal) { a.setAttribute('target', '_blank'); a.setAttribute('rel', 'noopener noreferrer') }
      else a.removeAttribute('href')
    } else if (follow && href.startsWith('/')) {
      a.setAttribute('href', LINK_PREFIX + encodeURIComponent(href))
      a.removeAttribute('target')
    } else {
      a.removeAttribute('href')
    }
  })
}

/** The link a frame just followed (its path on the magazine, like
 *  `/stories/low-tide`), or null when it is showing a page. */
export function followedLink(win: Window | null | undefined): string | null {
  let href = ''
  try {
    href = win?.location.href ?? ''
  } catch {
    return null
  }
  if (!href.startsWith(LINK_PREFIX)) return null
  try {
    return decodeURIComponent(href.slice(LINK_PREFIX.length))
  } catch {
    return null
  }
}
