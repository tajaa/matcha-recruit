import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { frameThreads, pageItemsHtml } from '../../render/layoutRender'
import { setHtml } from '../../render/sink'
import { useStudio } from '../../store/store'
import { useCtx } from '../context'
import { applyTemplate, blankPage, previewDoc, templateFaces } from './applyTemplate'
import { TEMPLATES, type Template } from './templates'

const THUMB = 124

/** A template drawn by the page renderer itself, small. */
function Thumb({ t }: { t: Template }) {
  const c = useCtx()
  const size = useStudio(c.store, (s) => s.doc.size)
  const paper = useStudio(c.store, (s) => s.doc.paper)
  const bleed = useStudio(c.store, (s) => s.doc.bleed)
  const html = useMemo(() => {
    const d = previewDoc(t, { ...c.store.get().doc, size, paper, bleed })
    return pageItemsHtml(d, 0, { assets: {}, faces: c.fonts.book.face, used: new Map(), threads: frameThreads(d) })
  }, [t, size, paper, bleed, c])
  const box = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => { if (box.current) setHtml(box.current, html) }, [html])
  return (
    <div ref={box} aria-hidden className="relative overflow-hidden rounded-sm shadow" style={{
      width: THUMB, height: (THUMB * size.h) / size.w, background: paper, ['--u' as string]: `${THUMB / size.w}px`,
    }} />
  )
}

/** Ready-made pages: on a blank page in view it takes that page, else it
 *  comes in as a new page after it. */
export default function TemplatesTab() {
  const c = useCtx()
  const book = c.fonts.book
  const blank = useStudio(c.store, (s) => blankPage(s.doc, s.page))
  const page = useStudio(c.store, (s) => s.page)
  // The template being set up (its faces loading): the others wait for it.
  const [pending, setPending] = useState<string | null>(null)
  const use = (t: Template) => {
    setPending(t.id)
    applyTemplate(c, t)
      .catch((err) => c.store.set({ notice: err instanceof Error && err.message ? err.message : 'Couldn’t use that template.' }))
      .finally(() => setPending(null))
  }
  useEffect(() => {
    for (const t of TEMPLATES) for (const [f, w, i] of templateFaces(t)) {
      const face = book.face(f, w, i)
      if (face) void c.fonts.ensure(face).catch(() => {})
    }
  }, [book, c.fonts])
  const groups = [...new Set(TEMPLATES.map((t) => t.group))]
  return (
    <div className="space-y-4">
      <p className="text-[11px] leading-snug text-zinc-500">
        {blank ? `Click one to lay out page ${page + 1}.` : `Click one to add it as a new page after page ${page + 1}.`}
        {' '}Then fill its frames from Photos or Yours, and type over its words.
      </p>
      {groups.map((g) => (
        <section key={g}>
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-400">{g}</h3>
          <div className="grid grid-cols-2 gap-3">
            {TEMPLATES.filter((t) => t.group === g).map((t) => (
              <button key={t.id} type="button" onClick={() => use(t)} disabled={pending !== null} aria-busy={pending === t.id}
                aria-label={`Use the ${t.label.toLowerCase()} template`}
                className="flex flex-col items-center gap-1.5 rounded-md p-1 text-[10px] text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 disabled:cursor-wait disabled:opacity-60">
                <Thumb t={t} />
                <span className="text-center">{pending === t.id ? 'Setting it up…' : t.label}</span>
              </button>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
