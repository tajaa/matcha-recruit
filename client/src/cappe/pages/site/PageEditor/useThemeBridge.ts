import type { RefObject } from 'react'
import { useEffect, useRef } from 'react'

/** Closed set of theme regions the preview iframe knows how to highlight
 *  (kept in lockstep with THEME_REGION_SEL in render.py's _CANVAS_JS). */
export type ThemeRegion =
  | 'brand' | 'accent' | 'headingFont' | 'bodyFont' | 'radius' | 'mode'
  | 'container' | 'gutter' | 'sectionPad' | 'gap' | 'cardPad' | 'cardBorder'
  | 'headerPad' | 'brandSize' | 'footerPad'

/** Mirrors useCanvasBridge's shape: posts `cz-theme-*` messages to the shared
 *  preview iframe so theme controls can highlight what they affect, and listens
 *  for the reverse `cz-theme-probe` (click a page element while the drawer is
 *  open) so the caller can jump the drawer to the governing control. */
export function useThemeBridge(iframeRef: RefObject<HTMLIFrameElement | null>, probeEnabled: boolean, onProbe?: (region: ThemeRegion) => void) {
  const postToTheme = (msg: unknown) => iframeRef.current?.contentWindow?.postMessage(msg, '*')
  const highlightRegion = (region: ThemeRegion) => postToTheme({ type: 'cz-theme-highlight', region })
  const clearHighlight = () => postToTheme({ type: 'cz-theme-clear' })

  const onProbeRef = useRef(onProbe)
  onProbeRef.current = onProbe
  const probeEnabledRef = useRef(probeEnabled)
  probeEnabledRef.current = probeEnabled

  // Tell the iframe runtime whether a page click means "which theme control
  // governs this?" (drawer open in Form mode) or falls through to canvas-mode
  // section selection.
  useEffect(() => {
    postToTheme({ type: probeEnabled ? 'cz-theme-open' : 'cz-theme-close' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [probeEnabled])

  useEffect(() => {
    function onMsg(e: MessageEvent) {
      if (e.source !== iframeRef.current?.contentWindow) return
      const d = e.data || {}
      if (d.type === 'cz-theme-probe' && d.region) onProbeRef.current?.(d.region)
      // The iframe is fully replaced (srcDoc) on most edits — re-assert the flag
      // once the fresh runtime says it's ready, or it resets to false and page
      // clicks stop probing until the drawer is toggled again.
      else if (d.type === 'cz-ready' && probeEnabledRef.current) postToTheme({ type: 'cz-theme-open' })
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { highlightRegion, clearHighlight }
}
