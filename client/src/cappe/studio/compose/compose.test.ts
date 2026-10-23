import { describe, expect, it } from 'vitest'
import { newItem } from '../model/doc'
import type { Doc, Line, Para, TextItem } from '../model/types'
import { compose, composeDoc, tokenize, type Measure } from './compose'

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
})
