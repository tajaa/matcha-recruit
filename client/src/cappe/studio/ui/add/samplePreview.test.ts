import { describe, expect, it } from 'vitest'
import { portableCollection } from '../../model/collections'
import { COLLECTIONS } from './collections'
import { previewDoc } from './applyTemplate'
import { TEMPLATES } from './templates'
import { pageSample, samplePreview } from './samplePreview'

describe('editorial sample photography', () => {
  it.each(COLLECTIONS)('illustrates $name without changing its insertable document', (collection) => {
    const before = JSON.stringify(collection.doc)
    const preview = samplePreview(collection.doc, collection.id)
    const pictures = preview.doc.items.filter((i) => i.kind === 'image')
    expect(pictures.length).toBeGreaterThan(0)
    for (const picture of pictures) {
      if (picture.kind !== 'image') continue
      expect(preview.assets[picture.asset_id!].url).toMatch(/\/templates\/starter-media\/[a-z-]+-v1\.webp$/)
    }
    expect(JSON.stringify(collection.doc)).toBe(before)
    expect(collection.doc.items.filter((i) => i.kind === 'image').every((i) => !i.asset_id)).toBe(true)
    // Even an accidentally reused preview must lose its pictures on placement/save.
    expect(portableCollection(preview.doc).items.filter((i) => i.kind === 'image').every((i) => !i.asset_id)).toBe(true)
  })

  it.each([undefined, 'saved-collection', 'constructor', '__proto__'])('does not illustrate a saved or unknown direction: %s', (direction) => {
    const doc = COLLECTIONS[0].doc
    expect(samplePreview(doc, direction)).toEqual({ doc, assets: {} })
    expect(samplePreview(doc, direction).doc).toBe(doc)
  })

  it('never replaces a photograph already in a document', () => {
    const source = COLLECTIONS[0].doc
    const image = source.items.find((i) => i.kind === 'image')!
    const doc = { ...source, items: source.items.map((i) => i.id === image.id ? { ...image, asset_id: 'owned-photo' } : i) }
    const preview = samplePreview(doc, 'quiet-form')
    expect(preview.doc.items.find((i) => i.id === image.id)).toBe(doc.items.find((i) => i.id === image.id))
    expect(preview.assets['owned-photo']).toBeUndefined()
  })

  it('illustrates single-page templates while keeping their frames empty for placement', () => {
    for (const template of TEMPLATES) {
      const doc = previewDoc(template, COLLECTIONS[0].doc)
      const before = JSON.stringify(doc)
      samplePreview(doc, pageSample(template.id))
      expect(JSON.stringify(doc)).toBe(before)
      expect(doc.items.filter((i) => i.kind === 'image').every((i) => !i.asset_id)).toBe(true)
    }
  })
})
