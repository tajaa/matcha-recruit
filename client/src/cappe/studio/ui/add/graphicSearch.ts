// Browsing and searching the graphics bank from the side panel
// (model/graphics.ts → routes/public/graphics.py).

import { useEffect, useRef, useState } from 'react'
import { graphicsApi, type GraphicCard, type GraphicGroup } from '../../model/graphics'

export const GROUP_TITLE: Record<GraphicGroup, string> = {
  shapes: 'Shapes', lines: 'Lines and dividers', badges: 'Badges and banners', icons: 'Icons', stickers: 'Stickers', patterns: 'Patterns',
}
const PAGE = 60

/** Matches for a search (or a group's, or a sticker set's), sixty at a time.
 *  The list belongs to the search that found it: while a changed search loads,
 *  the old matches stay in view but have no total, so More can't ask the new
 *  search for the old one's next page, and an old answer arriving late is dropped. */
export function useGraphicSearch(q: string, group?: GraphicGroup, set?: string) {
  const want = JSON.stringify([q, group ?? null, set ?? null])
  const [items, setItems] = useState<GraphicCard[]>([])
  const [total, setTotal] = useState<number | null>(null)
  const [shown, setShown] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const gen = useRef(0)
  const load = (offset: number) => {
    const mine = ++gen.current
    setBusy(true)
    if (!offset) setError(null)
    graphicsApi.search(q, group, set, offset, PAGE)
      .then((res) => {
        if (mine !== gen.current) return
        setItems((prev) => (offset ? [...prev, ...res.items] : res.items))
        setTotal(res.total)
        setShown(want)
        setError(null)
      })
      .catch((e) => { if (mine === gen.current) setError(e instanceof Error ? e.message : 'The graphics didn’t load.') })
      .finally(() => { if (mine === gen.current) setBusy(false) })
  }
  useEffect(() => {
    gen.current++
    const t = setTimeout(() => load(0), q ? 250 : 0)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- a new search whenever what is asked changes
  }, [want])
  const settled = shown === want
  return {
    items, total: settled ? total : null, busy: busy || (!settled && !error), error,
    more: () => { if (settled && !busy) load(items.length) },
  }
}
