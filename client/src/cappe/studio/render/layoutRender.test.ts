import { describe, expect, it } from 'vitest'
import fixture from '../../../../../server/tests/cappe/fixtures/studio_render_cases.json'
import type { Asset, Doc, Face } from '../model/types'
import { facesCss, n, pagesHtml } from './layoutRender'

/** The Studio shows each page by drawing it itself: it must draw the bytes a
 *  reader's page holds (services/magazine/studio/render.py), or what was
 *  designed isn't what is read. The fixture is the server's own output
 *  (test_cappe_studio_parity.py checks it is current). */
describe('the page renderer', () => {
  const table = new Map((fixture.faces as Face[]).map((f) => [`${f.family}|${f.weight}|${f.italic}`, f]))
  const faces = (family: string, weight: number, italic: boolean) => table.get(`${family}|${weight}|${italic}`)

  for (const c of fixture.cases) {
    it(`draws ${c.name} as the server does`, () => {
      const { html, used } = pagesHtml(c.doc as unknown as Doc, fixture.assets as unknown as Record<string, Asset>,
        faces, { lockedFrom: c.locked_from, label: fixture.label })
      expect(html).toBe(c.html)
      expect(Object.fromEntries([...used].sort().map(([k, v]) => [k, [...v].sort()]))).toEqual(c.used)
      expect(facesCss(c.doc as unknown as Doc, faces)).toBe(c.faces_css)
    })
  }

  it('prints numbers as the server does', () => {
    expect([12, 0.5, 1.005, 2.675, -0, 1234.5678, -3.14159].map(n)).toEqual(['12', '0.5', '1', '2.68', '0', '1234.57', '-3.14'])
  })
})
