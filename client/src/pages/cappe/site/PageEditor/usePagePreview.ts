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
) {
  const [preview, setPreview] = useState('')
  const previewSeq = useRef(0)

  useEffect(() => {
    if (!siteId || !page) return
    const seq = ++previewSeq.current
    const t = setTimeout(() => {
      if (suspendPreview.current) return
      cappeApi
        .postHtml(`/sites/${siteId}/preview`, {
          title, slug: page.slug, content: { blocks }, theme_config: theme, meta_config: meta, editable: editMode === 'canvas',
        })
        .then((html) => { if (seq === previewSeq.current) setPreview(html) })
        .catch(() => { /* keep last good preview */ })
    }, 400)
    return () => clearTimeout(t)
  }, [siteId, page, title, blocks, theme, meta, editMode, refreshTick])

  return preview
}
