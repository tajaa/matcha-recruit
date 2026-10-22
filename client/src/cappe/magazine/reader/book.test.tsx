import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import BookFrame from './BookFrame'
import { FLICK, LINK_PREFIX, POLL_MS, followedLink, prepareFrame, wireBook, type BookState } from './book'

const link = vi.hoisted(() => ({ value: null as string | null }))
vi.mock('./book', async (importOriginal) => {
  const real = await importOriginal<typeof import('./book')>()
  return { ...real, followedLink: (w: Window | null | undefined) => link.value ?? real.followedLink(w) }
})

const BOOK = '<div class="mz-reader" data-mz-book><button class="mz-turn" data-mz-prev hidden></button>'
  + '<div class="mz-spread"><div class="mz-book"><div class="mz-pages"><article>Words '
  + '<a href="/stories/next-one">Next story</a> <a href="https://example.com/x">elsewhere</a> <a href="#top">top</a>'
  + '</article><i class="mz-end"></i></div></div></div><button class="mz-turn" data-mz-next hidden></button><p data-mz-folio></p></div>'

/** A book page in a document of its own, `spreadW` wide with `totalW` of pages. */
function sizeBook(doc: Document, spreadW: number, totalW: number) {
  const book = doc.querySelector('.mz-book') as HTMLElement
  Object.defineProperty(book, 'clientWidth', { configurable: true, get: () => spreadW })
  Object.defineProperty(book, 'scrollWidth', { configurable: true, get: () => totalW })
  let left = 0
  Object.defineProperty(book, 'scrollLeft', { get: () => left, set: (v: number) => { left = v } })
  Object.defineProperty(book, 'scrollTo', { value: undefined })
  return {
    book,
    resize: (w: number, total: number) => {
      Object.defineProperty(book, 'clientWidth', { configurable: true, get: () => w })
      Object.defineProperty(book, 'scrollWidth', { configurable: true, get: () => total })
    },
  }
}

function frameDoc(spreadW: number, totalW: number) {
  const frame = document.createElement('iframe')
  document.body.appendChild(frame)
  const doc = frame.contentDocument!
  doc.body.innerHTML = BOOK
  return { doc, ...sizeBook(doc, spreadW, totalW) }
}

const settle = () => act(() => { vi.advanceTimersByTime(POLL_MS * 4) })

afterEach(() => { vi.useRealTimers(); link.value = null })

describe('wireBook', () => {
  it('opens on a spread, turns, counts pages and marks the cover', () => {
    vi.useFakeTimers()
    const { doc, book } = frameDoc(800, 2400)
    const seen: BookState[] = []
    const ctl = wireBook(doc, { start: 1, onState: (s) => seen.push(s) })!
    expect(book.scrollLeft).toBe(800)
    expect(ctl.state()).toEqual({ spread: 1, spreads: 3, folio: 'Page 2 of 3' })
    ctl.turn(1)
    expect(book.scrollLeft).toBe(1600)
    ctl.turn(1)
    expect(book.scrollLeft).toBe(1600)
    ctl.go(0)
    expect(doc.querySelector('[data-mz-book]')!.getAttribute('data-mz-at')).toBe('0')
    expect(seen.map((s) => s.spread)).toEqual([1, 2, 0])
    ctl.dispose()
  })

  it('settles a swipe: past a flick it turns, short of one it springs back, past half it lands nearest', () => {
    vi.useFakeTimers()
    const { doc, book } = frameDoc(800, 2400)
    const ctl = wireBook(doc)!
    book.scrollLeft = 800 * (FLICK + 0.04)
    settle()
    expect(book.scrollLeft).toBe(800)
    book.scrollLeft = 800 - 800 * (FLICK - 0.03)
    settle()
    expect(book.scrollLeft).toBe(800)
    book.scrollLeft = 2000
    settle()
    expect(book.scrollLeft).toBe(1600)
    expect(ctl.state().spread).toBe(2)
    ctl.dispose()
    book.scrollLeft = 1700
    settle()
    expect(book.scrollLeft).toBe(1700)
  })

  it('ends the pages on a whole spread, and counts only the pages printed', () => {
    const { doc } = frameDoc(800, 2000)
    const ctl = wireBook(doc)!
    expect((doc.querySelector('.mz-end') as HTMLElement).style.left).toBe('2399px')
    expect(ctl.state()).toEqual({ spread: 0, spreads: 3, folio: 'Page 1 of 3' })
    ctl.dispose()
  })

  it('keeps its place when the page changes size', () => {
    vi.useFakeTimers()
    const { doc, book, resize } = frameDoc(800, 2400)
    const ctl = wireBook(doc, { start: 2 })!
    resize(400, 2400)
    settle()
    expect(book.scrollLeft).toBe(800)
    ctl.dispose()
  })

  it('is nothing on a page that is not a book', () => {
    expect(wireBook(document.implementation.createHTMLDocument('front'))).toBeNull()
    expect(wireBook(null)).toBeNull()
    const { doc } = frameDoc(800, 800)
    const ctl = wireBook(doc)!
    expect(ctl.state()).toEqual({ spread: 0, spreads: 1, folio: '' })
    ctl.dispose()
  })
})

describe('prepareFrame and followedLink', () => {
  it('hides the page’s own controls and points its links out of the frame', () => {
    const { doc } = frameDoc(800, 800)
    prepareFrame(doc, { follow: true, openExternal: true })
    expect(doc.head.textContent).toContain('.mz-turn,[data-mz-folio]{display:none!important}')
    const [story, web, top] = Array.from(doc.querySelectorAll('a'))
    expect(story.getAttribute('href')).toBe(`${LINK_PREFIX}%2Fstories%2Fnext-one`)
    expect([web.getAttribute('target'), web.getAttribute('rel')]).toEqual(['_blank', 'noopener noreferrer'])
    expect(top.hasAttribute('href')).toBe(false)
  })

  it('leaves links dead when nothing follows them', () => {
    const { doc } = frameDoc(800, 800)
    prepareFrame(doc, { follow: false })
    expect(Array.from(doc.querySelectorAll('a')).map((a) => a.hasAttribute('href'))).toEqual([false, false, false])
    prepareFrame(null, { follow: true })
  })

  it('reads back a followed link', () => {
    const at = (href: string) => ({ location: { href } }) as unknown as Window
    expect(followedLink(at(`${LINK_PREFIX}%2Fstories%2Fx`))).toBe('/stories/x')
    expect(followedLink(at('about:srcdoc'))).toBeNull()
    expect(followedLink(at(`${LINK_PREFIX}%E0%A4%A`))).toBeNull()
    expect(followedLink({ get location(): Location { throw new Error('cross-origin') } } as unknown as Window)).toBeNull()
    expect(followedLink(null)).toBeNull()
  })
})

describe('BookFrame', () => {
  function load() {
    const frame = screen.getByTitle('Story') as HTMLIFrameElement
    const doc = frame.contentDocument!
    doc.body.innerHTML = BOOK
    const sized = sizeBook(doc, 800, 2400)
    fireEvent.load(frame)
    return { frame, doc, ...sized }
  }

  it('turns the pages from outside the frame, by its arrows and the keys', () => {
    vi.useFakeTimers()
    render(<BookFrame html="<p>page</p>" title="Story" keys />)
    expect(screen.getByTitle('Story').getAttribute('sandbox')).toBe('allow-same-origin')
    const { book } = load()
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    expect(book.scrollLeft).toBe(800)
    expect(screen.getByText('Page 2 of 3')).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'ArrowRight' })
    expect(book.scrollLeft).toBe(1600)
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled()
    fireEvent.keyDown(window, { key: 'ArrowLeft', metaKey: true })
    expect(book.scrollLeft).toBe(1600)
    fireEvent.click(screen.getByRole('button', { name: 'Previous page' }))
    expect(book.scrollLeft).toBe(800)
  })

  it('leaves the keys alone without `keys`, and while typing', () => {
    render(<><input aria-label="Title" /><BookFrame html="<p>page</p>" title="Story" /></>)
    const { book } = load()
    fireEvent.keyDown(window, { key: 'ArrowRight' })
    fireEvent.keyDown(screen.getByLabelText('Title'), { key: 'ArrowRight' })
    expect(book.scrollLeft).toBe(0)
  })

  it('hands a followed link back and puts the page back', () => {
    const onLink = vi.fn()
    render(<BookFrame html="<p>page</p>" title="Story" onLink={onLink} openExternal />)
    expect(screen.getByTitle('Story').getAttribute('sandbox')).toBe('allow-same-origin allow-popups allow-popups-to-escape-sandbox')
    const { frame } = load()
    link.value = '/stories/next-one'
    fireEvent.load(frame)
    expect(onLink).toHaveBeenCalledWith('/stories/next-one')
    expect(screen.getByTitle('Story')).not.toBe(frame)
  })

  it('opens a new preview on the spread being read', () => {
    vi.useFakeTimers()
    const { rerender } = render(<BookFrame html="<p>one</p>" title="Story" keepPlace />)
    const first = load()
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    rerender(<BookFrame html="<p>two</p>" title="Story" keepPlace />)
    const second = load()
    expect(second.book.scrollLeft).toBe(800)
    expect(first.book).not.toBe(second.book)
  })
})
