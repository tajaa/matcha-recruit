import type { CappePost, StoryBlock, StoryContent } from '../../types'
import { insertBlock, newBlock } from '../editor/blocks'
import { designOf, holdsDesign, mapLayers, setGeometry, withDesign } from '../design/designOps'
import type { Design } from '../design/types'
import type { FrameMessage, LayerChange } from './bridge'
import {
  FIELD_MAX, SIDEBAR_MD_MAX, blockHasField, clip, designField, fieldShape, isRichField, isStoryField, type StoryField,
} from './fields'
import { cleanRt, richPatch, type RtDoc } from './rt'

/** A story's header and settings. */
export type StoryFields = {
  title: string; kicker: string; excerpt: string; byline: string; topic: string
  layout: CappePost['layout']; status: CappePost['status']; access: CappePost['access']
}

/** One story as an editor edits it: its header and its blocks. */
export type StoryDoc = { fields: StoryFields; blocks: StoryBlock[] }

export const fieldsOf = (p: CappePost): StoryFields => ({
  title: p.title, kicker: p.kicker || '', excerpt: p.excerpt || '', byline: p.byline || '', topic: p.topic || '',
  layout: p.layout, status: p.status, access: p.access || 'free',
})

export const storyDocOf = (p: CappePost): StoryDoc => ({ fields: fieldsOf(p), blocks: p.content?.blocks || [] })

const HEADER: Record<StoryField, keyof StoryFields> = {
  '@title': 'title', '@kicker': 'kicker', '@excerpt': 'excerpt', '@byline': 'byline',
}

/** The story as the server takes it to render (the preview, an issue's
 *  unsaved story). */
export const storyPreviewBody = (d: StoryDoc) => ({
  title: d.fields.title, excerpt: d.fields.excerpt || null, kicker: d.fields.kicker || null, byline: d.fields.byline || null,
  layout: d.fields.layout, content: { blocks: d.blocks } satisfies StoryContent,
})

/** The PUT body that saves the story's words and blocks (and the settings
 *  that changed from `saved`). */
export function storySaveBody(d: StoryDoc, saved: CappePost) {
  const f = d.fields
  const body: Record<string, unknown> = {
    title: f.title.trim() || 'Untitled story', kicker: f.kicker.trim() || null, excerpt: f.excerpt.trim() || null,
    byline: f.byline.trim() || null, topic: f.topic || null, layout: f.layout, status: f.status,
  }
  if (f.access !== saved.access) body.access = f.access
  if (saved.format === 'blocks') {
    body.content = { blocks: d.blocks }
    body.cover_asset_id = d.blocks[0]?.type === 'cover' ? d.blocks[0].asset_id : null
  }
  return body
}

/** The PUT body that saves only a story's words and blocks: what the issue
 *  editor changes on its pages (its status, topic and layout are left as
 *  they are, so a story the issue just published stays published). */
export const storyWordsBody = (d: StoryDoc) => ({
  title: d.fields.title.trim() || 'Untitled story', kicker: d.fields.kicker.trim() || null,
  excerpt: d.fields.excerpt.trim() || null, byline: d.fields.byline.trim() || null,
  content: { blocks: d.blocks }, cover_asset_id: d.blocks[0]?.type === 'cover' ? d.blocks[0].asset_id : null,
})

export const sameStory = (a: StoryDoc, b: StoryDoc) => JSON.stringify(a) === JSON.stringify(b)

/** `block` with `path` (a field, or an item's) changed: `patch` holds the
 *  field's new value and, for rich text, its document beside it. */
function setIn(block: StoryBlock, path: string, patch: (key: string) => Record<string, unknown>): StoryBlock | null {
  const { shape, index } = fieldShape(path)
  const [list, , key] = shape.split('.')
  if (index === null) return { ...block, ...patch(shape) } as StoryBlock
  const items = (block as Record<string, unknown>)[list]
  if (!Array.isArray(items) || index >= items.length) return null
  return { ...block, [list]: items.map((it, i) => (i === index ? { ...it, ...patch(key) } : it)) } as StoryBlock
}

/** A rich field's document is kept beside its Markdown: `md` → `rt`,
 *  `a_md` → `a_rt`. */
const docKey = (key: string) => key.replace(/md$/, 'rt')

/** The story with words typed on its page. `block` is the block's index
 *  (the header's fields ignore it); a rich field's value is its document,
 *  kept with the Markdown the server will keep beside it. Null when the page
 *  named something this story doesn't have: the edit is dropped, never
 *  written somewhere else. */
export function applyEdit(doc: StoryDoc, block: number, field: string, value: string | RtDoc): StoryDoc | null {
  const rich = typeof value !== 'string'
  if (isStoryField(field)) {
    if (rich) return null
    const key = HEADER[field]
    const words = clip(value.replace(/\s*\n\s*/g, ' '), FIELD_MAX[field])
    return doc.fields[key] === words ? doc : { ...doc, fields: { ...doc.fields, [key]: words } }
  }
  const b = doc.blocks[block]
  const layer = designField(field)
  if (layer) return rich ? editLayerWords(doc, block, layer.item, layer.id, value) : null
  if (!b || !blockHasField(b.type, field) || rich !== isRichField(field)) return null
  const shape = fieldShape(field).shape
  const max = b.type === 'sidebar' && shape === 'md' ? SIDEBAR_MD_MAX : FIELD_MAX[shape]
  let next: StoryBlock | null
  if (rich) {
    const { rt, md } = richPatch(value, max)
    next = setIn(b, field, (key) => ({ [key]: md, [docKey(key)]: rt }))
  } else {
    // Only words on a photo keep their line breaks; a caption or a quote is one run.
    const words = clip(shape === 'overlays.#.text' ? value : value.replace(/\s*\n\s*/g, ' '), max)
    next = setIn(b, field, (key) => ({ [key]: words }))
  }
  if (!next) return null
  if (JSON.stringify(next) === JSON.stringify(b)) return doc
  return { ...doc, blocks: doc.blocks.map((x, i) => (i === block ? next : x)) }
}

const pct = (n: number) => Math.round(Math.max(0, Math.min(100, n)))

/** The story with the design at `block` (its picture `item`) rewritten by
 *  `fn`. Null when that block holds no design or `fn` leaves it as it was. */
export function changeDesign(doc: StoryDoc, block: number, item: number | null, fn: (d: Design) => Design | null): StoryDoc | null {
  const b = doc.blocks[block]
  if (!holdsDesign(b, item)) return null
  const before = designOf(b, item) ?? { layers: [] }
  const after = fn(before)
  if (!after || after === before) return null
  return { ...doc, blocks: doc.blocks.map((x, i) => (i === block ? withDesign(b, item, after) : x)) }
}

/** Words typed into a design's text layer. */
function editLayerWords(doc: StoryDoc, block: number, item: number | null, id: string, value: RtDoc): StoryDoc | null {
  const rt = cleanRt(value, FIELD_MAX.design)
  if (!rt) return null
  let found = false
  const next = changeDesign(doc, block, item, (d) => mapLayers(d, [id], (l) => {
    if (l.kind !== 'text') return l
    found = true
    return JSON.stringify(l.rt) === JSON.stringify(rt) ? l : { ...l, rt }
  }))
  return found ? next ?? doc : null
}

/** Layers moved, sized or turned on the page. */
export function moveLayers(doc: StoryDoc, block: number, item: number | null, changes: LayerChange[]): StoryDoc | null {
  return changeDesign(doc, block, item, (d) => {
    let next = setGeometry(d, changes)
    const fixed = changes.filter((c) => c.autosize === 'none').map((c) => c.id)
    if (fixed.length) next = mapLayers(next, fixed, (l) => (l.kind === 'text' ? { ...l, autosize: 'none' } : l))
    return JSON.stringify(next) === JSON.stringify(d) ? d : next
  })
}

/** The part of a cover picture it keeps in view. */
export function setFocal(doc: StoryDoc, block: number, x: number, y: number): StoryDoc | null {
  const b = doc.blocks[block]
  if (!b || b.type !== 'cover') return null
  return { ...doc, blocks: doc.blocks.map((x2, i) => (i === block ? { ...b, focal: { x: pct(x), y: pct(y) } } : x2)) }
}

/** The block with a picture chosen: the block's own, or item `item` of a
 *  photo group's. */
export function withPicture(block: StoryBlock, assetId: string, item: number | null): StoryBlock {
  if (block.type === 'photos') {
    if (item === null) {
      const empty = block.items.findIndex((x) => !x.asset_id)
      return empty === -1 ? block : withPicture(block, assetId, empty)
    }
    return { ...block, items: block.items.map((x, i) => (i === item ? { ...x, asset_id: assetId } : x)) }
  }
  return 'asset_id' in block ? { ...block, asset_id: assetId } : block
}

/** Where a block added at `at` lands: never in front of the cover. */
export const insertIndex = (blocks: StoryBlock[], at: number) =>
  Math.max(blocks[0]?.type === 'cover' ? 1 : 0, Math.min(blocks.length, at))

/** A message from the page applied to one story: the story after it, whether
 *  it is an undo step of its own (typing isn't: a sentence undoes as one),
 *  and the block to select after it. Null when it isn't about this story's
 *  words or blocks, or names something the story doesn't have. */
export function storyFromMessage(doc: StoryDoc, msg: FrameMessage): { doc: StoryDoc; step: boolean; select?: number } | null {
  switch (msg.type) {
    case 'mz-edit': {
      const next = applyEdit(doc, msg.block, msg.field, msg.value)
      return next ? { doc: next, step: false } : null
    }
    case 'mz-insert': {
      const at = insertIndex(doc.blocks, msg.at)
      const blocks = insertBlock(doc.blocks, at, newBlock(msg.kind))
      return blocks === doc.blocks || doc.blocks.length >= 120 ? null : { doc: { ...doc, blocks }, step: true, select: at }
    }
    case 'mz-layers': {
      const next = moveLayers(doc, msg.block, msg.item, msg.changes)
      return next ? { doc: next, step: true } : null
    }
    case 'mz-focal': {
      if (msg.target.kind !== 'block') return null
      const next = setFocal(doc, msg.target.block, msg.x, msg.y)
      return next ? { doc: next, step: true } : null
    }
    default:
      return null
  }
}
