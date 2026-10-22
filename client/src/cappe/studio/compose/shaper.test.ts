// @vitest-environment node
import { describe, expect, it } from 'vitest'
import fontData from './testdata/source-serif-4-ascii.ttf?inline'
import type { Face } from '../model/types'
import { Shaper, loadHarfBuzz } from './shaper'

// Source Serif 4 Regular as the Studio builds it, cut to ASCII (OFL, testdata/OFL.txt).
const bytes = Uint8Array.from(atob(fontData.split(',')[1]), (c) => c.charCodeAt(0))
const face: Face = { family: 'Source Serif 4', weight: 400, italic: false, sha: 'test', bytes: bytes.length, upm: 1000,
  asc: 1036, desc: -335, cap: 0, x: 0, features: [] }
const buffer = () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer

describe('the shaper', () => {
  it('measures with HarfBuzz: kerning, tracking after every character', async () => {
    const shaper = new Shaper(await loadHarfBuzz())
    shaper.add(face, buffer())
    shaper.add(face, buffer()) // once
    expect(shaper.has('test')).toBe(true)
    const av = shaper.width(face, 'AV', 10)
    expect(av).toBeLessThan(shaper.width(face, 'A', 10) + shaper.width(face, 'V', 10)) // kerned
    expect(shaper.width(face, 'AV', 10, 100)).toBeCloseTo(av + 2, 5)
    expect(shaper.width(face, '', 10)).toBe(0)
    expect(shaper.em('test', 'Hello')).toBe(shaper.em('test', 'Hello')) // cached
    expect(Shaper.metrics(face, 10)).toEqual({ asc: 10.36, desc: 3.35 })
  })

  it('hands text the face lacks to the browser', async () => {
    const seen: string[] = []
    const shaper = new Shaper(await loadHarfBuzz(), (text, _face, size) => { seen.push(text); return size })
    shaper.add(face, buffer())
    expect(shaper.covers('test', 'plain words')).toBe(true)
    expect(shaper.covers('test', '日本')).toBe(false)
    expect(shaper.covers('nope', 'x')).toBe(false)
    expect(shaper.width(face, '日本', 12)).toBe(12)
    expect(seen).toEqual(['日本'])
    expect(shaper.em('unloaded', 'abcd')).toBe(2)
  })
})
