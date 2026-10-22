import type { PhotoCrop, StoryBlock } from '../../types'
import type { RtDoc } from '../canvas/rt'

export const BLOCK_LABELS: Record<StoryBlock['type'], string> = {
  cover: 'Cover', text: 'Text', photo: 'Photo', photos: 'Photo group', quote: 'Pull quote',
  sidebar: 'Sidebar', qa: 'Q & A', divider: 'Divider', paywall: 'Paywall', page: 'Designed page',
}

/** A fresh block of `type`, with empty slots. */
export function newBlock(type: StoryBlock['type']): StoryBlock {
  switch (type) {
    case 'cover': return { type, asset_id: null, style: 'stacked', tone: 'light', focal: { x: 50, y: 50 } }
    case 'text': return { type, md: '', dropcap: false, columns: 1, variant: 'body', align: 'left' }
    case 'photo': return { type, asset_id: null, caption: '', size: 'column', border: 'none', shape: 'rect', filter: 'none', crop: null, design: null }
    case 'photos': return { type, layout: 'pair', items: [{ asset_id: null, caption: '' }, { asset_id: null, caption: '' }] }
    case 'quote': return { type, text: '', attribution: '', style: 'big' }
    case 'sidebar': return { type, title: '', md: '' }
    case 'qa': return { type, items: [{ q: '', a_md: '' }] }
    case 'divider': return { type }
    case 'paywall': return { type }
    case 'page': return { type, aspect: '3:4', design: { layers: [], background: { kind: 'solid', color: '#ffffff', angle: 180, stops: [] } } }
  }
}

/** The ids of every picture the blocks use. */
export function assetIdsIn(blocks: StoryBlock[]): string[] {
  const ids: string[] = []
  for (const b of blocks) {
    if ('asset_id' in b && b.asset_id) ids.push(b.asset_id)
    if (b.type === 'photos') for (const i of b.items) if (i.asset_id) ids.push(i.asset_id)
  }
  return ids
}

/** Reorder so the cover (if any) stays first: a cover can only be block 0. */
export function moveBlock(blocks: StoryBlock[], from: number, to: number): StoryBlock[] {
  if (to < 0 || to >= blocks.length || from === to) return blocks
  if (blocks[from].type === 'cover' || blocks[to].type === 'cover') return blocks
  const next = blocks.slice()
  const [b] = next.splice(from, 1)
  next.splice(to, 0, b)
  return next
}

/** `block` added at `at`. A cover only ever goes first (and there is only
 *  one); nothing else goes in front of a cover. */
export function insertBlock(blocks: StoryBlock[], at: number, block: StoryBlock): StoryBlock[] {
  if (block.type === 'cover') return blocks[0]?.type === 'cover' ? blocks : [block, ...blocks]
  if (block.type === 'paywall' && blocks.some((b) => b.type === 'paywall')) return blocks
  const i = Math.max(blocks[0]?.type === 'cover' ? 1 : 0, Math.min(blocks.length, at))
  return [...blocks.slice(0, i), block, ...blocks.slice(i)]
}

/** A copy of block `index` right after it. The cover and the paywall are one
 *  of a kind, so they aren't copied. */
export function duplicateBlock(blocks: StoryBlock[], index: number): StoryBlock[] {
  const b = blocks[index]
  if (!b || !canDuplicate(b)) return blocks
  return [...blocks.slice(0, index + 1), structuredClone(b), ...blocks.slice(index + 1)]
}

export const canDuplicate = (b: StoryBlock) => b.type !== 'cover' && b.type !== 'paywall'

/** The blocks with `caption` under every use of the picture `assetId`. */
export function withCaption(blocks: StoryBlock[], assetId: string, caption: string): StoryBlock[] {
  return blocks.map((b) => {
    if (b.type === 'photo' && b.asset_id === assetId) return { ...b, caption }
    if (b.type === 'photos' && b.items.some((i) => i.asset_id === assetId)) {
      return { ...b, items: b.items.map((i) => (i.asset_id === assetId ? { ...i, caption } : i)) }
    }
    return b
  })
}

/** The blocks with text block `index` rewritten as `md` (any other kind is left alone). */
/** A text block's words replaced: the document the server kept with them,
 *  else none (the server makes one from the Markdown). */
export function withText(blocks: StoryBlock[], index: number, md: string, rt?: RtDoc): StoryBlock[] {
  return blocks.map((b, j) => {
    if (j !== index || b.type !== 'text') return b
    const next = { ...b, md, rt }
    if (!rt) delete next.rt
    return next
  })
}

/** The first words of a text block, to name it in a list. */
export function textPreview(md: string, words = 8): string {
  const plain = md.replace(/[*_`#>[\]()]/g, '').split(/\s+/).filter(Boolean)
  return plain.slice(0, words).join(' ') + (plain.length > words ? '…' : '')
}

/** The crop between two dragged points (percent), or null when it's under 5%
 *  either way — the server's smallest crop (story_schema.MIN_CROP). */
export function cropBetween(a: { x: number; y: number }, b: { x: number; y: number }): PhotoCrop | null {
  const x = Math.min(a.x, b.x), y = Math.min(a.y, b.y)
  const w = Math.abs(a.x - b.x), h = Math.abs(a.y - b.y)
  return w < 5 || h < 5 ? null : { x, y, w, h }
}
