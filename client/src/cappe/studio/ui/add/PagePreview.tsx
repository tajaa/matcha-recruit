import { useLayoutEffect, useMemo, useRef } from 'react'
import type { FaceBook } from '../../fonts/faces'
import type { Doc } from '../../model/types'
import { frameThreads, pageItemsHtml } from '../../render/layoutRender'
import { setHtml } from '../../render/sink'
import { samplePreview } from './samplePreview'
import '../../render/layout.css'

/** A composed Studio page, shared by the editor and magazine setup. */
export function PagePreview({ doc, faces, page = 0, width = 112, sample }: {
  doc: Doc; faces: FaceBook; page?: number; width?: number; sample?: string
}) {
  const html = useMemo(() => {
    const preview = samplePreview(doc, sample)
    return pageItemsHtml(preview.doc, page, {
      assets: preview.assets, faces: faces.face, used: new Map(), threads: frameThreads(preview.doc),
    })
  }, [doc, page, faces, sample])
  const box = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => { if (box.current) setHtml(box.current, html) }, [html])
  return <div ref={box} aria-hidden className="relative shrink-0 overflow-hidden shadow-md" style={{
    width, height: width * doc.size.h / doc.size.w, background: doc.paper, ['--u' as string]: `${width / doc.size.w}px`,
  }} />
}
