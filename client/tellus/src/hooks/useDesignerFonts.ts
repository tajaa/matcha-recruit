// Font manifest loader for the designer.
//
// Konva measures text against whatever the browser has resolved at draw time.
// If a family is still loading, the stage bakes fallback metrics and the export
// comes out with the wrong line breaks — so every render path (first Stage
// draw AND each export) awaits ensureLoaded() for the families in the document
// before it draws.
//
// Manifest entries with `file: null` are platform fonts: nothing to fetch, so
// they resolve immediately. Entries with a file get a real FontFace.
import { useCallback, useEffect, useRef, useState } from 'react'
import type { FontManifestEntry } from '../api/types'
import { ASSET_BASE } from '../utils/designer'

export const FALLBACK_FONTS: FontManifestEntry[] = [
  { family: 'Helvetica Neue', file: null, weight: 400, preview: 'Aa' },
]

export function useDesignerFonts() {
  const [fonts, setFonts] = useState<FontManifestEntry[]>(FALLBACK_FONTS)
  const [ready, setReady] = useState(false)
  // Family -> in-flight or settled load. Keyed promises rather than a boolean
  // set so two concurrent ensureLoaded() calls share one FontFace load.
  const loads = useRef(new Map<string, Promise<void>>())
  const manifest = useRef<FontManifestEntry[]>(FALLBACK_FONTS)

  useEffect(() => {
    let alive = true
    void (async () => {
      try {
        const res = await fetch(`${ASSET_BASE}/fonts/index.json`)
        if (!res.ok) throw new Error(String(res.status))
        const list = (await res.json()) as FontManifestEntry[]
        if (!alive || !Array.isArray(list) || list.length === 0) return
        manifest.current = list
        setFonts(list)
      } catch {
        // Asset pack missing (or a bad deploy) must not brick the designer —
        // the platform stack still renders, it just offers one family.
      } finally {
        if (alive) setReady(true)
      }
    })()
    return () => { alive = false }
  }, [])

  const ensureLoaded = useCallback(async (families: string[]) => {
    const wanted = [...new Set(families)].filter(Boolean)
    await Promise.all(wanted.map((family) => {
      const existing = loads.current.get(family)
      if (existing) return existing
      const entry = manifest.current.find((f) => f.family === family)
      const load = (async () => {
        try {
          if (entry?.file) {
            const face = new FontFace(family, `url(${ASSET_BASE}/fonts/${entry.file})`, { weight: String(entry.weight) })
            await face.load()
            document.fonts.add(face)
          }
          await document.fonts.load(`${entry?.weight ?? 400} 16px "${family}"`)
        } catch {
          // A missing font degrades to the platform fallback; blocking the
          // canvas on it would be worse than a metrics mismatch.
        }
      })()
      loads.current.set(family, load)
      return load
    }))
  }, [])

  return { fonts, ready, ensureLoaded }
}
