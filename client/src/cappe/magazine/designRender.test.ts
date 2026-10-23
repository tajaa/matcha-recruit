import { describe, expect, it } from 'vitest'
import designCases from '../../../../server/tests/cappe/fixtures/magazine_design_cases.json'
import rtCases from '../../../../server/tests/cappe/fixtures/magazine_rt_cases.json'
import { rtToHtml, type RtDoc } from './canvas/rt'
import { designHtml, safeImage, type DesignAsset } from './design/designRender'
import { fontHref, fontStack, nearestWeight } from './design/fontStack'
import type { Design } from './design/types'

/** The editor draws a design on the page itself, at once, while the server
 *  sets the page again: the two must draw the same bytes, or the server's
 *  page would flicker in. The fixture is the server's own output
 *  (test_cappe_design_schema.py checks it is current). */
describe('the design renderer', () => {
  for (const c of designCases) {
    it(`draws ${c.name} as the server does`, () => {
      const picture = c.picture ? { ratio: c.picture[0], fx: c.picture[1], fy: c.picture[2] } : null
      expect(designHtml(c.design as unknown as Design, c.assets as Record<string, DesignAsset>,
        { edit: c.edit, path: c.path, picture })).toBe(c.html)
    })
  }

  it('draws rich text as the server does', () => {
    for (const c of rtCases) expect(rtToHtml(c.rt as RtDoc), c.name).toBe(c.html)
  })

  it('keeps only addresses a page may load', () => {
    expect(safeImage('https://cdn.example.test/a.jpg')).toBe('https://cdn.example.test/a.jpg')
    for (const bad of ['javascript:alert(1)', 'https://x.test/a"b', 'data:image/png;base64,x', '', 3]) expect(safeImage(bad)).toBeNull()
  })

  it('sets faces with their fallbacks, the weights they have, and asks for those', () => {
    expect(fontStack('heading')).toBe('var(--mz-h)')
    expect(fontStack('Lora')).toBe("'Lora', Georgia, 'Times New Roman', serif")
    expect(nearestWeight('Anton', 900)).toBe(400)
    expect(nearestWeight('Inter', 650)).toBe(700)
    expect(fontHref('Lora', [{ weight: 700, italic: true }, { weight: 900, italic: false }]))
      .toBe('https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,700;1,700&display=swap')
    expect(fontHref('Not a face', [])).toBeNull()
  })
})
