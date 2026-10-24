// The Studio's built-in graphics (server studio/graphics.py,
// routes/public/graphics.py): a graphic item names its file by sha, and the
// side panel browses and searches the bank. Gummfit's picks (studio/bank.py)
// are graphics an admin added, named and drawn the same way.

import { cappeApiBase } from '../../api'
import type { GraphicFit } from './types'

export type GraphicGroup = 'shapes' | 'lines' | 'badges' | 'icons' | 'stickers' | 'patterns'
/** A graphic as the side panel shows and places it (a pick also carries
 *  its tags and collection, to be searched where it is shown). */
export type GraphicCard = {
  sha: string; name: string; group: GraphicGroup; mono: boolean; fit: GraphicFit; w: number; h: number; set?: string
  tags?: string[]; collection?: string | null
}
export type GraphicBrowse = {
  version: string
  groups: { group: GraphicGroup; count: number; items: GraphicCard[] }[]
  sets: { set: string; count: number }[]
}
export type GraphicSearch = { total: number; items: GraphicCard[] }

/** A graphic's file; `stretch`, made to fill its box out of its own shape
 *  (server graphics.stretched). */
export const graphicUrl = (sha: string, stretch = false) =>
  `/api/cappe/public/graphics/${stretch ? 'stretch/' : ''}${sha}.svg`

const get = async <T>(path: string): Promise<T> => {
  const res = await fetch(`${cappeApiBase}/public/graphics/${path}`)
  if (!res.ok) throw new Error('The graphics didn’t load. Try again.')
  return res.json() as Promise<T>
}

let browsed: Promise<GraphicBrowse> | null = null
let picked: Promise<GraphicCard[]> | null = null

/** The picks matching every word of `q` (in the name, a tag or the collection). */
export function matchPicks(picks: GraphicCard[], q: string): GraphicCard[] {
  const words = q.toLowerCase().split(/\s+/).filter(Boolean)
  return picks.filter((g) => {
    const text = [g.name, ...(g.tags ?? []), g.collection ?? ''].join(' ').toLowerCase()
    return words.every((w) => text.includes(w))
  })
}

export const graphicsApi = {
  /** Each group's first graphics (asked once a session). */
  browse: (): Promise<GraphicBrowse> => {
    browsed ??= get<GraphicBrowse>('browse').catch((e) => { browsed = null; throw e })
    return browsed
  },
  /** Gummfit's picks, in the admin's order (asked once a session). */
  picks: (): Promise<GraphicCard[]> => {
    picked ??= get<{ items: GraphicCard[] }>('picks').then((r) => r.items).catch((e) => { picked = null; throw e })
    return picked
  },
  search: (q: string, group?: GraphicGroup, set?: string, offset = 0, limit = 60): Promise<GraphicSearch> => {
    const params = new URLSearchParams({ q, offset: String(offset), limit: String(limit) })
    if (group) params.set('group', group)
    if (set) params.set('set', set)
    return get<GraphicSearch>(`search?${params.toString()}`)
  },
}
