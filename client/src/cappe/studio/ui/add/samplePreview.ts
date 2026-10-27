// A presentation-only projection. Never hand this document to the store or
// placement code: collection/template source documents keep empty photo frames.
import { cappeApiBase } from '../../../api'
import type { Asset, Doc } from '../../model/types'

const DIRECTIONS: Record<string, readonly string[]> = {
  'quiet-form': ['editorial-fashion', 'vessel'],
  'off-register': ['editorial-art', 'lamp'],
  'still-light': ['editorial-coast', 'editorial-detail'],
  maison: ['vessel', 'editorial-fashion', 'tote'],
}

/** Saved collections and unknown directions receive no example photography. */
export function samplePreview(doc: Doc, direction?: string): { doc: Doc; assets: Record<string, Asset> } {
  const pictures = direction && Object.hasOwn(DIRECTIONS, direction) ? DIRECTIONS[direction] : undefined
  const assets: Record<string, Asset> = {}
  if (!pictures) return { doc, assets }
  let n = 0
  const items = doc.items.map((item) => {
    if (item.kind !== 'image' || item.asset_id) return item
    const picture = pictures[n++ % pictures.length]
    const id = `sample${n}`
    const portrait = picture.startsWith('editorial-'), detail = picture === 'editorial-detail'
    assets[id] = { id, url: `${cappeApiBase}/templates/starter-media/${picture}-v1.webp`,
      alt: 'Illustrative sample photograph', ai_generated: true, width: detail ? 600 : portrait ? 750 : 960,
      height: detail ? 800 : portrait ? 1000 : 960 }
    return { ...item, asset_id: id, fy: picture === 'editorial-fashion' ? 35 : item.fy }
  })
  return { doc: { ...doc, items }, assets }
}

export function pageSample(templateId: string): string {
  if (templateId === 'cover-classic' || templateId === 'back-subscribe') return 'maison'
  if (templateId === 'cover-photo' || templateId === 'interview') return 'quiet-form'
  return 'still-light'
}
