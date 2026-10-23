// The Studio's built-in graphics (server studio/graphics.py,
// routes/public/graphics.py): a graphic item names its file by sha, and the
// side panel browses and searches the bank.

import { cappeApiBase } from '../../api'
import type { GraphicFit } from './types'

export type GraphicGroup = 'shapes' | 'lines' | 'badges' | 'icons' | 'stickers' | 'patterns'
/** A graphic as the side panel shows and places it. */
export type GraphicCard = { sha: string; name: string; group: GraphicGroup; mono: boolean; fit: GraphicFit; w: number; h: number; set?: string }
export type GraphicBrowse = {
  version: string
  groups: { group: GraphicGroup; count: number; items: GraphicCard[] }[]
  sets: { set: string; count: number }[]
}
export type GraphicSearch = { total: number; items: GraphicCard[] }

export const graphicUrl = (sha: string) => `/api/cappe/public/graphics/${sha}.svg`

const get = async <T>(path: string): Promise<T> => {
  const res = await fetch(`${cappeApiBase}/public/graphics/${path}`)
  if (!res.ok) throw new Error('The graphics didn’t load. Try again.')
  return res.json() as Promise<T>
}

let browsed: Promise<GraphicBrowse> | null = null

export const graphicsApi = {
  /** Each group's first graphics (asked once a session). */
  browse: (): Promise<GraphicBrowse> => {
    browsed ??= get<GraphicBrowse>('browse').catch((e) => { browsed = null; throw e })
    return browsed
  },
  search: (q: string, group?: GraphicGroup, set?: string, offset = 0, limit = 60): Promise<GraphicSearch> => {
    const params = new URLSearchParams({ q, offset: String(offset), limit: String(limit) })
    if (group) params.set('group', group)
    if (set) params.set('set', set)
    return get<GraphicSearch>(`search?${params.toString()}`)
  },
}
