import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import type { Design } from './design/types'
import { drawDesign, fontsHref, loadFonts } from './frame/layers'

/** What the editor on the page takes from a message: a design's layers drawn
 *  cleaned, and only Google Fonts stylesheets loaded. */

const PAGE = `
<article class="mz-story" data-mz-s="p1">
  <figure class="mz-photo" data-mz-b="2"><div class="mzd" data-mzd="design"><i class="mzd__box"></i></div></figure>
</article>`

const base = {
  name: '', x: 0, y: 0, w: 50, h: 10, rot: 0, flip_x: false, flip_y: false, opacity: 100, blend: 'normal',
  hidden: false, locked: false, link: '', fill: { kind: 'none', color: '#000000', angle: 180, stops: [] },
  radius: [0, 0, 0, 0], shadows: [], blur: 0,
} as const

beforeAll(() => { document.body.innerHTML = PAGE })
afterAll(() => { document.body.innerHTML = ''; document.head.querySelectorAll('link').forEach((l) => l.remove()) })

describe('a design drawn from a message', () => {
  it('keeps its layers and drops markup slipped into a value', () => {
    const design = {
      layers: [{
        ...base, id: 'a', kind: 'shape', shape: 'line',
        stroke: { color: '#111111', width: 1, style: 'solid"><img src=x onerror="alert(1)"><i x="' },
      }],
    } as unknown as Design
    drawDesign({ story: 'p1', block: 2, item: null }, design, {})
    const art = document.querySelector('.mzd')!
    expect(art.querySelector(':scope > .mzd__box')).not.toBeNull()
    expect(art.querySelector('[data-mzd-l="a"]')).not.toBeNull()
    expect(art.innerHTML).not.toContain('onerror')
  })
})

describe('fonts from a message', () => {
  it('loads only Google Fonts stylesheets, rebuilt on their origin', () => {
    const ok = 'https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;1,700&display=swap'
    expect(fontsHref(ok)).toBe(ok)
    for (const bad of [
      'javascript:alert(1)', 'https://fonts.googleapis.com.evil.test/css2?family=X', 'https://evil.test/css2?family=X',
      'https://fonts.googleapis.com/css?family=X', 'https://fonts.googleapis.com/css2', 'not a url', 7, null,
    ]) expect(fontsHref(bad)).toBeNull()
    loadFonts([ok, ok, 'https://evil.test/css2?family=X'])
    const links = Array.from(document.head.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"]'))
    expect(links.map((l) => l.href)).toEqual([ok])
  })
})
