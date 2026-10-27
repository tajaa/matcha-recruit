import { describe, expect, it, vi } from 'vitest'
import { newItem } from '../../model/doc'
import type { Doc, Item } from '../../model/types'
import { DEFAULT_VIEW, type State } from '../../store/store'
import { cropFor, inlinePage, scaleFor, sourceFor } from './snapshot'

const doc = (items: Item[] = []): Doc => ({
  v: 1, size: { w: 600, h: 800 }, facing: false, margins: { t: 50, b: 50, i: 50, o: 50 }, cols: { n: 1, g: 12 },
  baseline: { start: 50, step: 12 }, grid: { step: 12 }, bleed: 9, units: 'pt', paper: '#fafaf0',
  pages: [{ id: 'p1' }, { id: 'p2' }], guides: [], items, threads: [], paywall_page: null,
})
const rect = (id: string, page: string, x: number, y: number, w: number, h: number) => newItem('rect', page, id, { x, y, w, h }) as Item
const state = (d: Doc, selection: string[] = [], page = 0) => ({
  doc: d, selection, page, editing: null, tool: 'select', view: { ...DEFAULT_VIEW }, assets: {},
} as unknown as State)

describe('what is drawn', () => {
  it('the selection on its page, with room around it', () => {
    const s = state(doc([rect('a', 'p2', 100, 200, 200, 100), rect('b', 'p2', 350, 250, 100, 100)]), ['a', 'b'])
    const pad = 0.08 * 350
    expect(cropFor(s)).toEqual({ page: 1, x: 100 - pad, y: 200 - pad, w: 350 + 2 * pad, h: 150 + 2 * pad })
  })

  it('a tiny selection with what is around it, kept inside the page', () => {
    const c = cropFor(state(doc([rect('a', 'p1', 0, 790, 20, 10)]), ['a']))
    expect(c).toMatchObject({ page: 0, x: 0 })
    expect(c.y + c.h).toBe(800)
    expect(c.h).toBeGreaterThan(60) // clipped at the foot, never past it
    expect(cropFor(state(doc([rect('a', 'p1', 300, 300, 10, 10)]), ['a'])).w).toBe(160)
  })

  it('the page in view when nothing is selected, or what is selected is gone', () => {
    expect(cropFor(state(doc(), [], 1))).toEqual({ page: 1, x: 0, y: 0, w: 600, h: 800 })
    expect(cropFor(state(doc(), ['gone'], 1)).page).toBe(1)
  })

  it('at most 1,280 px on its longest side, and no more than three times its size', () => {
    expect(scaleFor({ page: 0, x: 0, y: 0, w: 600, h: 800 })).toBe(1.6)
    expect(scaleFor({ page: 0, x: 0, y: 0, w: 100, h: 50 })).toBe(3)
  })

  it('picks the smallest picture file wide enough, else the biggest, else the original', () => {
    const set = 'https://cdn.example.test/a-400.webp 400w, https://cdn.example.test/a-1600.webp 1600w, https://cdn.example.test/a-800.webp 800w'
    expect(sourceFor(set, '/a.jpg', 700)).toBe('https://cdn.example.test/a-800.webp')
    expect(sourceFor(set, '/a.jpg', 5000)).toBe('https://cdn.example.test/a-1600.webp')
    expect(sourceFor(null, '/a.jpg', 700)).toBe('/a.jpg')
  })
})

describe('inlining what the page loads', () => {
  const html = '<div class="lyt-item" style="left:1px"><img src="/p.jpg" srcset="/p-800.webp 800w" sizes="10vw" loading="lazy" class="lyt-pic" style="width:100%"/></div>'
    + '<div class="lyt-item lyt-g" style="background:#000;mask:url(/api/cappe/public/graphics/g1.svg) center/contain no-repeat"></div>'
    + '<img src="https://cdn.example.test/gone.jpg" style="width:10px"/>'
    + '<span style="font-family:\'f-aaaaaaaaaaaaaaaa\'">Words</span>'
  const css = "@font-face{font-family:'f-aaaaaaaaaaaaaaaa';src:url(/api/cappe/public/fonts/aaaaaaaaaaaaaaaa11.ttf) format('truetype')}"
    + "@font-face{font-family:'f-bbbbbbbbbbbbbbbb';src:url(/api/cappe/public/fonts/bbbbbbbbbbbbbbbb22.ttf) format('truetype')}"

  it('puts pictures, graphics and the page’s own faces in as data, and leaves an unreachable picture grey', async () => {
    const picture = vi.fn(async (url: string, want: number) => {
      if (url.includes('gone')) throw new Error('cors')
      return `data:image/jpeg;base64,${url.length}x${want}`
    })
    const file = vi.fn(async (url: string, type: string) => `data:${type};base64,${url.slice(-6)}`)
    const out = await inlinePage(doc(), { page: 0, x: 100, y: 50, w: 200, h: 100 }, 2, html, css, { picture, file })
    expect(picture).toHaveBeenCalledWith('/p-800.webp', 1200) // the page is 1,200 px wide at this scale
    expect(out).toContain('src="data:image/jpeg;base64,11x1200"')
    expect(out).not.toContain('srcset')
    expect(out).not.toContain('loading=')
    expect(out).toContain('mask:url(&quot;data:image/svg+xml;base64,g1.svg&quot;)')
    expect(out).toMatch(/background:#c8c8c8/)
    // Only the face the page sets is fetched; the other is left empty.
    expect(file).toHaveBeenCalledWith('/api/cappe/public/fonts/aaaaaaaaaaaaaaaa11.ttf', 'font/ttf')
    expect(file).not.toHaveBeenCalledWith('/api/cappe/public/fonts/bbbbbbbbbbbbbbbb22.ttf', 'font/ttf')
    expect(out).toContain('url(data:,)')
    // The crop's size, the page moved so the crop is at its top left, one point = 2 px.
    expect(out).toContain('width:400px;height:200px')
    expect(out).toContain('--u:2px')
    expect(out).toContain('left:-200px;top:-100px;width:1200px;height:1600px')
    expect(out).toContain('background:#fafaf0')
    expect(out).toMatch(/^<div xmlns="http:\/\/www\.w3\.org\/1999\/xhtml"/)
  })
})
