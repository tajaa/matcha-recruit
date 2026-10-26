import { beforeEach, describe, expect, it } from 'vitest'
import { jumpToAnnotation, locateQuote, pageAt, paintAnnotations, selectedQuote, selectionPageAt } from './annotations'
import type { ReaderAnnotation, ReaderQuote } from './annotationTypes'
const q = (exact: string, start = 0, prefix = '', suffix = ''): ReaderQuote => ({ exact, start, prefix, suffix })
const note = (quote: ReaderQuote, kind: ReaderAnnotation['kind'] = 'highlight', id = 'a'): ReaderAnnotation =>
  ({ id, kind, quote, view: 'pages', page: 1, text: '' })
beforeEach(() => { document.body.innerHTML = '<article class="mz-story"><p>Hello <b>🌍 world</b>, hello.</p></article>' })
describe('quote anchors', () => {
  it('uses UTF-16 across formatted text', () => {
    const p = document.querySelector('p')!, text = p.querySelector('b')!.firstChild!
    const range = document.createRange()
    range.setStart(p.firstChild!, 3); range.setEnd(text, 4)
    document.getSelection()!.removeAllRanges(); document.getSelection()!.addRange(range)
    expect(selectedQuote(document)).toEqual(q('lo 🌍 w', 3, 'Hel', 'orld, hello.'))
  })
  it('rejects selections outside the story and over the limit', () => {
    const range = document.createRange()
    document.body.append('outside'); range.selectNodeContents(document.body.lastChild!)
    document.getSelection()!.removeAllRanges(); document.getSelection()!.addRange(range)
    expect(selectedQuote(document)).toBeNull()
    document.querySelector('p')!.textContent = 'x'.repeat(2001)
    range.selectNodeContents(document.querySelector('p')!)
    document.getSelection()!.removeAllRanges(); document.getSelection()!.addRange(range)
    expect(selectedQuote(document)).toBeNull()
  })
  it('relocates after edits and disambiguates repeated words by context', () => {
    expect(locateQuote('new before coast after', q('coast', 7, 'before ', ' after'))).toBe(11)
    expect(locateQuote('one coast two coast', q('coast', 0, 'two '))).toBe(14)
    expect(locateQuote('coast and coast', q('coast', 1))).toBeNull()
    expect(locateQuote('gone', q('coast'))).toBeNull()
  })
})
describe('painting', () => {
  it('paints overlapping marks without changing text or formatting, and removes them', () => {
    const before = document.querySelector('article')!.textContent
    const all = [note(q('Hello 🌍 world')), note(q('🌍 world', 6), 'underline', 'b')]
    expect(paintAnnotations(document, all)).toEqual(new Set(['a', 'b']))
    expect(document.querySelector('article')!.textContent).toBe(before)
    expect(document.querySelector('b [data-reader-note="b"]')!.getAttribute('style')).toContain('underline')
    paintAnnotations(document, all)
    expect(document.querySelector('article')!.textContent).toBe(before)
    paintAnnotations(document, [])
    expect(document.querySelector('[data-reader-note]')).toBeNull()
    expect(document.querySelector('b')!.textContent).toBe('🌍 world')
  })
  it('keeps stale quotes out of the page and supports selected comments', () => {
    expect(paintAnnotations(document, [note(q('deleted'))])).toEqual(new Set())
    paintAnnotations(document, [note(q('Hello'), 'comment')])
    expect(document.querySelector('[data-reader-note]')!.getAttribute('style')).toContain('background')
  })
  it('paints disjoint portions of one node exactly', () => {
    document.querySelector('article')!.textContent = '0123456789'
    paintAnnotations(document, [note(q('12', 1)), note(q('678', 6), 'underline', 'b')])
    expect(Array.from(document.querySelectorAll('[data-reader-note]'), (el) => el.textContent)).toEqual(['12', '678'])
  })
  it('locates a Studio selection on its actual printed page', () => {
    document.body.innerHTML = '<div data-lyt-strip><div class="lyt-paper" data-lyt-n="2"></div><article class="lyt-page" data-lyt-page="2"><p>Coast</p></article></div>'
    const range = document.createRange(); range.selectNodeContents(document.querySelector('p')!)
    document.getSelection()!.removeAllRanges(); document.getSelection()!.addRange(range)
    expect(selectionPageAt(document)).toBe(2)
  })
  it('reads classic book pages and jumps to a page comment', () => {
    document.body.innerHTML = '<div class="mz-book"><div class="mz-pages" style="column-count:2"></div></div>'
    const book = document.querySelector<HTMLElement>('.mz-book')!
    Object.defineProperty(book, 'clientWidth', { value: 800 }); book.scrollLeft = 1600
    expect(pageAt(document)).toBe(5)
    jumpToAnnotation(document, { ...note(q('')), quote: null, page: 3 })
    expect(book.scrollLeft).toBe(800)
  })
})
