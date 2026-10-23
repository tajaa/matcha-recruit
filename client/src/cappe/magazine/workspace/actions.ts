import type { CappeAsset, StoryBlock } from '../../types'
import type { FrameKey, FrameTarget } from '../canvas/bridge'
import { changeDesign, insertIndex, type StoryDoc } from '../canvas/storyDoc'
import {
  addLayers, arrange, cloneLayers, designOf, designPath, duplicate, group, holdsDesign, newImage, newShape, newText, removeLayers,
  topLevel, ungroup, walk, type ArtAt, type Heights, type TextPreset,
} from '../design/designOps'
import type { DesignAsset } from '../design/designRender'
import { fontHref } from '../design/fontStack'
import { insertBlock, newBlock } from '../editor/blocks'
import type { Design, Layer, PageAspect, ShapeKind } from '../design/types'
import { PAGE_ASPECTS } from '../design/types'

/** What the workspace does to the story for a click in its panels or a key
 *  on the page: pure, from one story to the next, with what to select after. */

export type Did = { doc: StoryDoc; select: FrameTarget | null }

/** The picture (or page) a selection is on, where layers go: a layer's, a
 *  picture selected, a page. A photo group as a whole has none (one of its
 *  pictures has), nor a picture not yet chosen. */
export function artOf(doc: StoryDoc, t: FrameTarget | null): ArtAt | null {
  if (!t || (t.kind !== 'layer' && t.kind !== 'block')) return null
  const item = t.kind === 'layer' ? t.item : t.item ?? null
  const b = doc.blocks[t.block]
  if (!b || !holdsDesign(b, item)) return null
  if (b.type === 'page') return { block: t.block, item: null }
  const asset = item !== null && b.type === 'photos' ? b.items[item]?.asset_id : 'asset_id' in b ? b.asset_id : null
  return asset ? { block: t.block, item } : null
}

/** The artboard's width over its height, for shapes that should look square
 *  and pictures laid at their own shape. */
export function artRatio(doc: StoryDoc, art: ArtAt, assets: Map<string, CappeAsset>): number {
  const b = doc.blocks[art.block]
  if (!b) return 1.5
  if (b.type === 'page') return PAGE_ASPECTS[b.aspect] ?? 0.75
  const id = art.item !== null && b.type === 'photos' ? b.items[art.item]?.asset_id : 'asset_id' in b ? b.asset_id : null
  const a = id ? assets.get(id) : null
  if (b.type === 'photo' && b.crop && a?.width && a.height) return (a.width * b.crop.w) / (a.height * b.crop.h)
  return a?.width && a.height ? a.width / a.height : 1.5
}

export const layerTarget = (story: string, art: ArtAt, ids: string[]): FrameTarget => ({ kind: 'layer', story, block: art.block, item: art.item, ids })

export const pictureTarget = (story: string, art: ArtAt): FrameTarget =>
  art.item === null ? { kind: 'block', story, block: art.block } : { kind: 'block', story, block: art.block, item: art.item }

/** Layers added to the picture or page in hand, selected. */
export function addToArt(doc: StoryDoc, story: string, art: ArtAt, layers: Layer[]): Did | null {
  const next = changeDesign(doc, art.block, art.item, (d) => addLayers(d, layers))
  return next ? { doc: next, select: layerTarget(story, art, layers.map((l) => l.id)) } : null
}

/** The layers' design, read for a selection of layers. */
const layersOf = (doc: StoryDoc, t: Extract<FrameTarget, { kind: 'layer' }>) => designOf(doc.blocks[t.block], t.item)

/** A key from the page (or the same command from a menu) done to what is
 *  selected. Null when it means nothing for that selection. */
export function command(doc: StoryDoc, story: string, t: FrameTarget | null, key: FrameKey, clipboard: Clipboard,
  heights?: Heights): Did | null {
  if (t?.kind !== 'layer') {
    // A picture or page in hand takes what was copied.
    const art = artOf(doc, t)
    if (key === 'paste' && art && clipboard.layers.length) {
      return addToArt(doc, story, art, cloneLayers(designOf(doc.blocks[art.block], art.item), clipboard.layers, clipboard.from === artKey(art) ? 2 : 0))
    }
    return null
  }
  const art = { block: t.block, item: t.item }
  const d = layersOf(doc, t)
  if (!d) return null
  const change = (fn: Parameters<typeof changeDesign>[3]) => changeDesign(doc, art.block, art.item, fn)
  switch (key) {
    case 'delete': case 'cut': {
      if (key === 'cut') copy(clipboard, d, t.ids, art)
      const next = change((x) => removeLayers(x, t.ids))
      return next ? { doc: next, select: pictureTarget(story, art) } : null
    }
    case 'copy':
      copy(clipboard, d, t.ids, art)
      return null
    case 'paste': {
      if (!clipboard.layers.length) return null
      return addToArt(doc, story, art, cloneLayers(d, clipboard.layers, clipboard.from === artKey(art) ? 2 : 0))
    }
    case 'duplicate': {
      const r = duplicate(d, t.ids)
      const next = change(() => r.design)
      return next ? { doc: next, select: layerTarget(story, art, r.ids) } : null
    }
    case 'group': {
      const r = group(d, t.ids, heights)
      if (!r.id) return null
      const next = change(() => r.design)
      return next ? { doc: next, select: layerTarget(story, art, [r.id]) } : null
    }
    case 'ungroup': {
      if (t.ids.length !== 1) return null
      const r = ungroup(d, t.ids[0])
      const next = change(() => r.design)
      return next ? { doc: next, select: layerTarget(story, art, r.ids) } : null
    }
    case 'front': case 'forward': case 'backward': case 'back': {
      const next = change((x) => arrange(x, t.ids, key))
      return next ? { doc: next, select: t } : null
    }
    default:
      return null
  }
}

/** Layers copied, kept beside the story (any picture can take them). */
export type Clipboard = { layers: Layer[]; from: string }

export const artKey = (art: ArtAt) => `${art.block}:${art.item}`

function copy(c: Clipboard, d: NonNullable<ReturnType<typeof designOf>>, ids: string[], art: ArtAt) {
  c.layers = structuredClone(topLevel(d, ids))
  c.from = artKey(art)
}

/** Where a new block goes: after the block in hand (or the one its layers
 *  are on), else at the end; never in front of the cover. */
export function blockAfter(doc: StoryDoc, t: FrameTarget | null): number {
  const at = t && (t.kind === 'block' || t.kind === 'layer') && doc.blocks[t.block] ? t.block + 1 : doc.blocks.length
  return insertIndex(doc.blocks, at)
}

/** A block added after the one in hand, selected. Null when the story is full. */
export function addBlock(doc: StoryDoc, story: string, t: FrameTarget | null, block: StoryBlock): Did | null {
  if (doc.blocks.length >= 120) return null
  const i = blockAfter(doc, t)
  const blocks = insertBlock(doc.blocks, i, block)
  if (blocks === doc.blocks) return null
  return { doc: { ...doc, blocks }, select: { kind: 'block', story, block: blocks.indexOf(block) } }
}

/** A designed page of that shape, after the block in hand. */
export function addPage(doc: StoryDoc, story: string, t: FrameTarget | null, aspect: PageAspect): Did | null {
  const page = newBlock('page')
  return addBlock(doc, story, t, page.type === 'page' ? { ...page, aspect } : page)
}

/** Whether the art is a page with a light background (dark words go on it)
 *  rather than a picture (light words do). */
function lightArt(doc: StoryDoc, art: ArtAt): boolean {
  const b = doc.blocks[art.block]
  if (b?.type !== 'page') return true
  const c = b.design.background?.kind === 'solid' ? b.design.background.color : '#ffffff'
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})/i.exec(c)
  if (!m) return false
  const [r, g, bl] = [m[1], m[2], m[3]].map((h) => parseInt(h, 16))
  return 0.2126 * r + 0.7152 * g + 0.0722 * bl < 140
}

/** Words of a preset style on the picture or page in hand. */
export function addText(doc: StoryDoc, story: string, art: ArtAt, preset: TextPreset): Did | null {
  return addToArt(doc, story, art, [newText(designOf(doc.blocks[art.block], art.item), preset, undefined, lightArt(doc, art))])
}

/** A shape on the picture or page in hand; `square` makes it look square
 *  (or round) on that artboard's shape. */
export function addShape(doc: StoryDoc, story: string, art: ArtAt, assets: Map<string, CappeAsset>, shape: ShapeKind, square = false): Did | null {
  return addToArt(doc, story, art, [newShape(designOf(doc.blocks[art.block], art.item), shape, { square, ratio: artRatio(doc, art, assets) })])
}

/** A library picture laid on the picture or page in hand, at its own shape. */
export function addImage(doc: StoryDoc, story: string, art: ArtAt, assets: Map<string, CappeAsset>, asset: CappeAsset): Did | null {
  const ratio = asset.width && asset.height ? asset.width / asset.height : 1.5
  const name = (asset.title || asset.alt || 'Picture').slice(0, 60)
  return addToArt(doc, story, art, [newImage(designOf(doc.blocks[art.block], art.item), asset.id, ratio, artRatio(doc, art, assets), name)])
}

/** A key pressed in the workspace's panels (not the page, not a box being
 *  typed in), as the page reads it (frame/layers.ts `commandKey`), plus
 *  Delete. */
export function panelKey(e: { key: string; code?: string; metaKey: boolean; ctrlKey: boolean; shiftKey: boolean; altKey: boolean }): FrameKey | null {
  const mod = e.metaKey || e.ctrlKey, k = (e.key || '').toLowerCase()
  if (!mod) return k === 'delete' || k === 'backspace' ? 'delete' : null
  if (k === 'c') return 'copy'
  if (k === 'x') return 'cut'
  if (k === 'v') return 'paste'
  if (k === 'd') return 'duplicate'
  if (k === 'g') return e.shiftKey ? 'ungroup' : 'group'
  if (k === ']' || e.code === 'BracketRight') return e.altKey ? 'front' : 'forward'
  if (k === '[' || e.code === 'BracketLeft') return e.altKey ? 'back' : 'backward'
  return null
}

/** The stylesheets a design's faces need, for the page to load at once. */
export function designFontHrefs(d: Design | null | undefined): string[] {
  const styles = new Map<string, { weight: number; italic: boolean }[]>()
  for (const l of walk(d?.layers ?? [])) {
    if (l.kind !== 'text') continue
    const list = styles.get(l.font) ?? []
    list.push({ weight: l.weight, italic: l.italic }, { weight: 700, italic: false })
    styles.set(l.font, list)
  }
  return [...styles].map(([font, s]) => fontHref(font, s)).filter((h): h is string => !!h)
}

/** Every picture a design lays on, as drawing it needs them. */
export function designAssets(d: Design | null | undefined, assets: Map<string, CappeAsset>): Record<string, DesignAsset> {
  const out: Record<string, DesignAsset> = {}
  for (const l of walk(d?.layers ?? [])) {
    const a = l.kind === 'image' ? assets.get(l.asset_id) : undefined
    if (a) out[a.id] = { id: a.id, url: a.url, alt: a.alt, width: a.width, height: a.height, variants: a.variants }
  }
  return out
}

/** Each design that differs between two states of the story, as a message
 *  that draws it on the page at once (frame/index.ts `mz-design`); the
 *  server's page follows. Blocks that moved are left to the server. */
export function designMessages(before: StoryDoc | null, after: StoryDoc, story: string, assets: Map<string, CappeAsset>): Record<string, unknown>[] {
  if (!before || before.blocks.length !== after.blocks.length) return []
  const out: Record<string, unknown>[] = []
  after.blocks.forEach((b, i) => {
    const a = before.blocks[i]
    if (a === b || a.type !== b.type) return
    const items = b.type === 'photos' ? b.items.map((_, j) => j as number | null) : [null]
    for (const item of items) {
      if (!holdsDesign(b, item)) continue
      const d0 = designOf(a, item), d1 = designOf(b, item)
      if (d0 === d1 || JSON.stringify(d0) === JSON.stringify(d1)) continue
      const design = d1 ?? { layers: [] }
      out.push({ type: 'mz-design', story, block: i, item, path: designPath(item), design, assets: designAssets(design, assets), fonts: designFontHrefs(design) })
    }
  })
  return out
}
