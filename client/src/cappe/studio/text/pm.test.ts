import { describe, expect, it } from 'vitest'
import type { Para } from '../model/types'
import { attrsOf, emptyAttrsOf, fromPM, locOf, markFor, posOf, toPM } from './pm'

const paras: Para[] = [
  { runs: [{ t: 'Gem of ', size: 30 }, { t: 'the Bay', size: 30, wt: 700 }], role: 'h1' },
  { runs: [{ t: '', size: 14, it: true }], sb: 6 },
  { runs: [{ t: 'Low tide\nat the pier' }], align: 'j' },
]

describe('the editor’s document', () => {
  it('round-trips paragraphs, their type, an empty one’s type and line breaks', () => {
    const doc = toPM(paras)
    expect(doc.childCount).toBe(3)
    expect(emptyAttrsOf(doc.child(1))).toEqual({ size: 14, it: true })
    expect(fromPM(doc)).toEqual(paras)
  })

  it('stores only what differs from the default', () => {
    expect(markFor({ wt: 400, it: false, u: false })).toEqual([])
    expect(attrsOf(markFor({ wt: 700 }))).toEqual({ wt: 700 })
    expect(fromPM(toPM([{ runs: [{ t: 'x', wt: 400 }], align: 'l' }]))).toEqual([{ runs: [{ t: 'x' }] }])
  })

  it('maps places to positions and back, clamped to the text', () => {
    const doc = toPM(paras)
    for (const [p, o] of [[0, 0], [0, 14], [1, 0], [2, 5]] as const) expect(locOf(doc, posOf(doc, p, o))).toEqual([p, o])
    expect(locOf(doc, posOf(doc, 0, 99))).toEqual([0, 14])
    expect(locOf(doc, posOf(doc, 9, 0))).toEqual([2, 0])
    expect(locOf(doc, doc.content.size + 5)).toEqual([2, 20])
  })
})
