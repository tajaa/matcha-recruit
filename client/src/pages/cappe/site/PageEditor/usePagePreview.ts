import { useEffect, useRef, useState, type MutableRefObject } from 'react'
import { cappeApi } from '../../../../api/cappeClient'
import type { CappeBlock, CappePage } from '../../../../types/cappe'

/** Debounced live preview of the current (unsaved) blocks + theme. In Canvas
 *  mode it renders with the selection/edit runtime (`editable`). While an inline
 *  edit or drag is in progress (`suspendPreview`), skip the refetch so the
 *  iframe — and the user's caret — survive; it resumes on `cz-editing-end`. */
export function usePagePreview(
  siteId: string | undefined,
  page: CappePage | null,
  title: string,
  blocks: CappeBlock[],
  theme: Record<string, unknown>,
  meta: Record<string, unknown>,
  editMode: 'form' | 'canvas',
  refreshTick: number,
  suspendPreview: MutableRefObject<boolean>,
  themeOpen: boolean,
) {
  const [preview, setPreview] = useState('')
  const previewSeq = useRef(0)
  // The theme drawer's highlight-sync bridge needs the `_CANVAS_JS` runtime in
  // the iframe even in Form mode — otherwise there's no listener for
  // `cz-theme-highlight` when the drawer is open over a plain form preview.
  const editable = editMode === 'canvas' || themeOpen

  useEffect(() => {
    if (!siteId || !page) return
    const seq = ++previewSeq.current
    const t = setTimeout(() => {
      if (suspendPreview.current) return
      cappeApi
        .postHtml(`/sites/${siteId}/preview`, {
          title, slug: page.slug, content: { blocks }, theme_config: theme, meta_config: meta, editable,
        })
        .then((html) => { if (seq === previewSeq.current) setPreview(html) })
        .catch(() => { /* keep last good preview */ })
    }, 400)
    return () => clearTimeout(t)
    // Depend on the computed `editable`, not `themeOpen`: in canvas mode the
    // runtime is always injected, so toggling the drawer must NOT force a full
    // iframe reload (flash + scroll reset) for byte-identical HTML.
  }, [siteId, page, title, blocks, theme, meta, editMode, refreshTick, editable])

  return preview
}
