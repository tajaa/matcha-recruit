import { describe, expect, it } from 'vitest'
import manifest from '../../../../../server/app/cappe/services/magazine/studio/fonts_manifest.json'
import { composeDoc, type Measure } from '../../studio/compose/compose'
import { Shaper } from '../../studio/compose/shaper'
import { FaceBook, type Manifest } from '../../studio/fonts/faces'
import { docProblem } from '../../studio/model/limits'
import { COLLECTIONS } from '../../studio/ui/add/collections'
import { magazineStarter } from './starter'

const book = new FaceBook(manifest as Manifest)
const measure: Measure = { width: (c, text) => [...text].length * c.size * 0.5,
  metrics: (c) => Shaper.metrics(book.measureFace(c.font, c.wt, c.it)!, c.size) }

describe('a magazine’s first Studio draft', () => {
  it.each(COLLECTIONS)('fits short, maximum-length and Unicode mastheads in $name', ({ doc }) => {
    const snapshot = structuredClone(doc)
    for (const name of ['Harbour', 'A'.repeat(120), 'The Harbour Review — art, fashion & culture', '光と風 🌊 Café e\u0301']) {
      const draft = magazineStarter(doc, name, measure)
      expect(docProblem(draft)).toBeNull()
      expect(draft.pages).toHaveLength(10)
      const id = draft.items.find((i) => i.name === 'Masthead')!.id
      const thread = draft.threads.find((t) => t.frames.includes(id))!
      expect(thread.paras.flatMap((p) => p.runs.map((r) => r.t)).join('')).toBe(name)
      expect(composeDoc(draft, measure, true).overset.has(thread.id)).toBe(false)
      expect(draft.items.filter((i) => i.kind === 'image').every((i) => !i.asset_id)).toBe(true)
      expect(draft.paywall_page).toBeNull()
    }
    expect(doc).toEqual(snapshot)
  })
})
