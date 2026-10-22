import type { StoryBlock } from '../../types'

export const BLOCK_LABELS: Record<StoryBlock['type'], string> = {
  cover: 'Cover', text: 'Text', photo: 'Photo', photos: 'Photo group', quote: 'Pull quote',
  sidebar: 'Sidebar', qa: 'Q & A', divider: 'Divider', paywall: 'Paywall',
}

/** A fresh block of `type`, with empty slots. */
export function newBlock(type: StoryBlock['type']): StoryBlock {
  switch (type) {
    case 'cover': return { type, asset_id: null, style: 'stacked', tone: 'light', focal: { x: 50, y: 50 } }
    case 'text': return { type, md: '', dropcap: false, columns: 1 }
    case 'photo': return { type, asset_id: null, caption: '', size: 'column' }
    case 'photos': return { type, layout: 'pair', items: [{ asset_id: null, caption: '' }, { asset_id: null, caption: '' }] }
    case 'quote': return { type, text: '', attribution: '', style: 'big' }
    case 'sidebar': return { type, title: '', md: '' }
    case 'qa': return { type, items: [{ q: '', a_md: '' }] }
    case 'divider': return { type }
    case 'paywall': return { type }
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
