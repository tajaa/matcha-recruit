// Browsing and searching the graphics bank from the side panel
// (model/graphics.ts → routes/public/graphics.py).

import { useEffect, useRef, useState } from 'react'
import { graphicsApi, type GraphicCard, type GraphicGroup } from '../../model/graphics'

export const GROUP_TITLE: Record<GraphicGroup, string> = {
  shapes: 'Shapes', lines: 'Lines and dividers', badges: 'Badges and banners', icons: 'Icons', stickers: 'Stickers', patterns: 'Patterns',
}
const PAGE = 60

/** Matches for a search (or a group's, or a sticker set's), sixty at a time. */
export function useGraphicSearch(q: string, group?: GraphicGroup, set?: string) {
  const [items, setItems] = useState<GraphicCard[]>([])
  const [total, setTotal] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const gen = useRef(0)
  const load = (offset: number) => {
    const mine = ++gen.current
    setBusy(true)
    graphicsApi.search(q, group, set, offset, PAGE)
      .then((res) => {
        if (mine !== gen.current) return
        setItems((prev) => (offset ? [...prev, ...res.items] : res.items))
        setTotal(res.total)
        setError(null)
      })
      .catch((e) => { if (mine === gen.current) setError(e instanceof Error ? e.message : 'The graphics didn’t load.') })
      .finally(() => { if (mine === gen.current) setBusy(false) })
  }
  useEffect(() => {
    const t = setTimeout(() => load(0), q ? 250 : 0)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- a new search whenever what is asked changes
  }, [q, group, set])
  return { items, total, busy, error, more: () => load(items.length) }
}

