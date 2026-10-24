import { describe, expect, it } from 'vitest'
import { newItem } from '../model/doc'
import type { Doc, Line, Para, TextItem } from '../model/types'
import { compose, composeDoc, room, tokenize, type Measure } from './compose'
import { picturePlace, shapeFromAlpha, subjectRows, threadWraps } from './wrap'

/** Every character is half an em wide; ascent 0.8 em, descent 0.2 em. */
const mono: Measure = {
  width: (c, text) => [...text].length * 0.5 * c.size,
  metrics: (c) => ({ asc: 0.8 * c.size, desc: 0.2 * c.size }),
}

const frame = (over: Partial<TextItem> = {}): TextItem =>
  ({ ...(newItem('text', 'p1', 't1', { x: 0, y: 0, w: 50, h: 100 }) as TextItem), ...over })
const para = (t: string, over: Partial<Para> = {}): Para => ({ runs: [{ t, size: 10 }], ...over })
const text = (p: Para, ln: Line) => p.runs.map((r) => r.t).join('').slice(ln[2], ln[3])

describe('the composer', () => {
  it('breaks greedily at spaces, keeping the spaces between lines', () => {
    const p = para('one two three four')
    const { comp, overset } = compose([p], [frame()], mono) // 10 characters a line
    expect(comp.lines.map((ln) => text(p, ln))).toEqual(['one two', 'three four'])
    expect(comp.lines[0]).toEqual([0, 0, 0, 7, 0, 8, 50, 0]) // the first baseline: its ascent below the top
    expect(comp.lines[1][5]).toBe(20) // auto leading: 120% of 10 pt
    expect(overset).toBe(false)
  })

  it('cuts a word longer than its line, and breaks after a hyphen', () => {
    const p = para('abcdefghijklmnop well-known')
    const lines = compose([p], [frame()], mono).comp.lines.map((ln) => text(p, ln))
    expect(lines).toEqual(['abcdefghij', 'klmnop', 'well-known'])
    const q = para('abcde well-known')
    expect(compose([q], [frame()], mono).comp.lines.map((ln) => text(q, ln))).toEqual(['abcde', 'well-known'])
    const r = para('ab well-known')
    expect(compose([r], [frame()], mono).comp.lines.map((ln) => text(r, ln))).toEqual(['ab well-', 'known'])
  })

  it('breaks at a line break, and an empty line follows a break at the end', () => {
    const p = para('one\ntwo\n')
    const { comp } = compose([p], [frame()], mono)
    expect(comp.lines.map((ln) => [ln[2], ln[3]])).toEqual([[0, 3], [4, 7], [8, 8]])
  })

  it('gives an empty paragraph a line of its type', () => {
    const { comp } = compose([para(''), para('x')], [frame()], mono)
    expect(comp.lines.map((ln) => [ln[1], ln[2], ln[3]])).toEqual([[0, 0, 0], [1, 0, 1]])
  })

  it('justifies all but the last line, and aligns the rest as asked', () => {
    const just = compose([para('one two three four', { align: 'j' })], [frame()], mono).comp.lines
    expect(just.map((ln) => ln[7])).toEqual([3, 0])
    const all = compose([para('one two three four', { align: 'ja' })], [frame()], mono).comp.lines
    expect(all.map((ln) => ln[7])).toEqual([3, 3])
    expect(compose([para('x', { align: 'c' })], [frame()], mono).comp.lines[0][7]).toBe(1)
    expect(compose([para('x', { align: 'r' })], [frame()], mono).comp.lines[0][7]).toBe(2)
  })

  it('indents, and spaces paragraphs (not at the top of a column)', () => {
    const lines = compose([para('aaaa bbbb cccc', { li: 5, fi: 10, ri: 5 }), para('d', { sb: 6 })], [frame()], mono)
      .comp.lines
    expect(lines[0].slice(4, 7)).toEqual([15, 8, 30]) // first line: left + first indent
    expect(lines[1].slice(4, 7)).toEqual([5, 20, 40])
    expect(lines[3][5] - lines[2][5]).toBe(18) // 12 leading + 6 before
    const top = compose([para('d', { sb: 6, lead: 30 })], [frame()], mono).comp.lines
    expect(top[0][5]).toBe(8)
  })

  it('flows through columns and frames, and says when text is left over', () => {
    const p = para('aa bb cc dd ee ff gg hh')
    const frames = [frame({ w: 50, h: 22, cols: 2, gutter: 10 }), frame({ id: 't2', w: 20, h: 10 })]
    const { comp, overset } = compose([p], frames, mono) // 4 characters a column, 2 lines each
    expect(comp.lines.map((ln) => [ln[0], ln[4], text(p, ln)])).toEqual([
      [0, 0, 'aa'], [0, 0, 'bb'], [0, 30, 'cc'], [0, 30, 'dd'], [1, 0, 'ee'],
    ])
    expect(overset).toBe(true)
  })

  it('moves lines down a column, or spreads them', () => {
    const bottom = compose([para('x')], [frame({ valign: 'bottom' })], mono).comp.lines
    expect(bottom[0][5]).toBe(98)
    const center = compose([para('x')], [frame({ valign: 'center' })], mono).comp.lines
    expect(center[0][5]).toBe(53)
    const spread = compose([para('a b c', { lead: 10 })], [frame({ w: 10, valign: 'justify' })], mono).comp.lines
    expect(spread.map((ln) => ln[5])).toEqual([8, 53, 98])
  })

  it('skips a frame too small for any line', () => {
    const { comp, overset } = compose([para('x')], [frame({ h: 5 }), frame({ id: 't2' })], mono)
    expect(comp.lines[0][0]).toBe(1)
    expect(overset).toBe(false)
    expect(compose([para('x')], [frame({ h: 5 })], mono).overset).toBe(true)
  })

  it('measures each run in its own type', () => {
    const toks = tokenize({ runs: [{ t: 'Bo', size: 10 }, { t: 'ld it', size: 20 }] }, mono)
    expect(toks.map((t) => [t.kind, t.s, t.e, t.w])).toEqual([['w', 0, 2, 10], ['w', 2, 4, 20], ['s', 4, 5, 10],
      ['w', 5, 7, 20]])
  })

  it('composes a document, keeping threads whose lines are the same', () => {
    const doc = {
      size: { w: 612, h: 792 }, pages: [{ id: 'p1' }], items: [frame()],
      threads: [{ id: 's1', frames: ['t1'], paras: [para('one two three four')] }],
    } as unknown as Doc
    const first = composeDoc(doc, mono)
    expect(first.doc.threads[0].comp!.lines).toHaveLength(2)
    const again = composeDoc(first.doc, mono)
    expect(again.doc).toBe(first.doc)
    expect(again.overset.size).toBe(0)
  })

  it('sets a drop cap from the first line\'s cap height to its last line\'s baseline, the lines beside it narrowed', () => {
    const p = para('Once upon a time there was a cap that sat beside three lines of words and more', { dc: 3 })
    const capped: Measure = { ...mono, metrics: (c) => ({ asc: 0.8 * c.size, desc: 0.2 * c.size, cap: 0.7 * c.size }) }
    const { comp } = compose([p], [frame({ w: 100 })], capped)
    const size = (2 * 12 + 7) / 0.7 // two leadings and the body's cap height, in cap heights
    expect(comp.caps).toEqual([[0, 1, 0, comp.lines[2][5], Math.round(size * 100) / 100]])
    const capW = 0.5 * size + 3.5 // its width, and a gap of 35% of the body size
    expect(comp.lines.slice(0, 3).map((ln) => ln[4])).toEqual([capW, capW, capW].map((v) => Math.round(v * 100) / 100))
    expect(comp.lines[3][4]).toBe(0) // past the cap: the column's full width
    expect(text(p, comp.lines[0]).startsWith('Once')).toBe(true) // the cap's letter still begins the line's text
  })

  it('leaves out a drop cap that isn\'t asked for, or would take the whole paragraph', () => {
    expect(compose([para('Once upon a time')], [frame()], mono).comp.caps).toBeUndefined()
    expect(compose([para('A', { dc: 2 })], [frame()], mono).comp.caps).toBeUndefined()
    expect(compose([para(' indented', { dc: 2 })], [frame()], mono).comp.caps).toBeUndefined()
  })

  it('moves a column break that would strand a widow or an orphan', () => {
    // 10 characters a line, 3 lines a column: a 4-line paragraph after one line leaves an orphan or a widow.
    const cols = [frame({ w: 110, h: 34, cols: 2, gutter: 10 })]
    const body = 'aaaa bbbb cccc dddd eeee ffff gggg hhhh'
    const plain = compose([para('x'), para(body)], cols, mono).comp.lines
    expect(plain.map((ln) => ln[4])).toEqual([0, 0, 0, 60, 60]) // two lines here, two in the next column
    const widows = compose([para('x'), para(body, { kw: 3 })], cols, mono).comp.lines
    expect(widows.map((ln) => ln[4])).toEqual([0, 0, 60, 60, 60]) // a line goes over so three are together
    const four = [frame({ w: 110, h: 46, cols: 2, gutter: 10 })] // 4 lines a column
    const orphans = compose([para('x'), para('y'), para('z'), para(body, { ko: 2 })], four, mono)
    expect(orphans.comp.lines.slice(3).map((ln) => ln[4])).toEqual([60, 60, 60, 60]) // one line at the foot: it starts over
    // When starting over would leave text with nowhere to go, it stays as it was.
    const full = compose([para('x'), para('y'), para('z'), para(body + ' iiii', { ko: 2 })], four, mono)
    expect(full.overset).toBe(false)
    expect(full.comp.lines[3][4]).toBe(0)
  })

  it('pushes words down so a last line isn\'t one word alone', () => {
    const p = para('aaa bbb ccc ddd eeeee', { runt: 2 })
    const plain = compose([{ ...p, runt: 1 }], [frame()], mono).comp.lines.map((ln) => text(p, ln))
    expect(plain).toEqual(['aaa bbb', 'ccc ddd', 'eeeee'])
    expect(compose([p], [frame()], mono).comp.lines.map((ln) => text(p, ln))).toEqual(['aaa bbb', 'ccc', 'ddd eeeee'])
  })

  it('sets each line in the widest room what it wraps leaves', () => {
    expect(room({ x: 0, w: 100 }, [{ x0: 20, y0: 0, x1: 40, y1: 10 }], 0, 10)).toEqual({ x: 40, w: 60 })
    expect(room({ x: 0, w: 100 }, [{ x0: 60, y0: 0, x1: 120, y1: 10 }], 0, 10)).toEqual({ x: 0, w: 60 })
    expect(room({ x: 0, w: 100 }, [{ x0: 0, y0: 20, x1: 100, y1: 30 }], 0, 10)).toEqual({ x: 0, w: 100 }) // not at this height
    expect(room({ x: 0, w: 100 }, [{ x0: -5, y0: 0, x1: 105, y1: 10 }], 0, 10)).toBeNull()
    const p = para('aaa bbb ccc ddd eee fff ggg hhh')
    const wide = frame({ w: 100, h: 200 })
    const lines = compose([p], [wide], mono, [[{ x0: 0, y0: 0, x1: 50, y1: 25 }]]).comp.lines
    expect(lines[0][4]).toBe(50) // beside the picture: its right half
    expect(lines[0][6]).toBe(50)
    expect(lines.at(-1)![4]).toBe(0) // below it: the whole width again
    const blocked = compose([p], [wide], mono, [[{ x0: 0, y0: 0, x1: 100, y1: 40 }]]).comp.lines
    expect(blocked[0][5] - 8).toBeGreaterThanOrEqual(40) // nothing beside it: set below
  })

  it('wraps a frame\'s box or its picture\'s subject, wherever the crop puts it', () => {
    const shape = { ar: 1, rows: [[0.25, 0.75], [0.4, 0.6]] as [number, number][] }
    const pic = { ...(newItem('image', 'p1', 'i1', { x: 100, y: 100, w: 100, h: 100 })), shape, wrap: { m: 'subject' as const, o: 5 } }
    expect(picturePlace({ w: 100, h: 50, fit: 'fill', fx: 50, fy: 0, zoom: 100 }, 1)).toEqual({ x: 0, y: 0, w: 100, h: 100 })
    expect(picturePlace({ w: 100, h: 50, fit: 'fit', fx: 0, fy: 50, zoom: 200 }, 1)).toEqual({ x: 0, y: -25, w: 100, h: 100 })
    expect(subjectRows(pic as never)).toEqual([{ x0: 25, y0: 0, x1: 75, y1: 50 }, { x0: 40, y0: 50, x1: 60, y1: 100 }])
    const doc = { pages: [{ id: 'p1' }], items: [frame({ x: 0, y: 0, w: 300, h: 300 }), pic], threads: [] } as unknown as Doc
    const got = threadWraps(doc, [doc.items[0] as TextItem])
    expect(got.wraps![0]).toEqual([{ x0: 120, y0: 95, x1: 180, y1: 155 }, { x0: 135, y0: 145, x1: 165, y1: 205 }])
    const boxed = { ...doc, items: [doc.items[0], { ...pic, wrap: { m: 'box', o: 0 } }] } as Doc
    expect(threadWraps(boxed, [doc.items[0] as TextItem]).wraps![0]).toEqual([{ x0: 100, y0: 100, x1: 200, y1: 200 }])
    const away = { ...doc, items: [doc.items[0], { ...pic, page: 'p2' }] } as Doc
    expect(threadWraps(away, [doc.items[0] as TextItem])).toEqual({ wraps: undefined, key: '' })
  })

  it('reads a cut-out\'s subject out of its pixels', () => {
    const w = 4, h = 2, data = new Uint8ClampedArray(w * h * 4)
    data[(0 * w + 1) * 4 + 3] = 255; data[(0 * w + 2) * 4 + 3] = 200 // top row: columns 1 and 2
    data[(1 * w + 3) * 4 + 3] = 100 // bottom row: too faint
    expect(shapeFromAlpha(data, w, h, 2)).toEqual({ ar: 2, rows: [[0.25, 0.75], [1, 0]] })
  })

  it('sets a thread again when a picture it wraps moves', () => {
    const doc = {
      size: { w: 612, h: 792 }, pages: [{ id: 'p1' }],
      items: [frame({ w: 100, h: 200 }), { ...newItem('rect', 'p1', 'r1', { x: 0, y: 0, w: 50, h: 25 }), wrap: { m: 'box', o: 0 } }],
      threads: [{ id: 's1', frames: ['t1'], paras: [para('aaa bbb ccc ddd eee fff')] }],
    } as unknown as Doc
    const first = composeDoc(doc, mono).doc
    expect(first.threads[0].comp!.lines[0][4]).toBe(50)
    const moved = { ...first, items: [first.items[0], { ...first.items[1], x: 500 }] } as Doc
    expect(composeDoc(moved, mono).doc.threads[0].comp!.lines[0][4]).toBe(0)
  })
})
