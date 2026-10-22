import { useLayoutEffect, useRef } from 'react'
import { ensureThread } from '../../model/ops'
import { useStudio } from '../../store/store'
import { useCtx } from '../context'

/** The Story Editor (⌘Y): the text being typed in, as plain running text,
 *  with the browser's own spelling check, for long passages and screen
 *  readers. It is the same editor the page types through, shown here. */
export function StoryPanel() {
  const c = useCtx()
  const editing = useStudio(c.store, (s) => s.editing)
  const frame = useStudio(c.store, (s) => s.doc.items.find((i) => s.selection.includes(i.id) && i.kind === 'text')?.id ?? null)
  const box = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const el = box.current
    if (!el) return
    c.editor.showIn(el)
    return () => c.editor.showIn(null)
  }, [c.editor])
  const open = () => {
    if (!frame) return
    let thread = ''
    c.store.edit((d) => { const r = ensureThread(d, frame); thread = r.thread; return r.doc })
    c.editor.open(thread)
  }
  return (
    <section aria-label="Story Editor" className="flex min-h-0 flex-1 flex-col border-b border-zinc-800">
      <div className="flex items-center justify-between px-4 py-2">
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">Story Editor</h3>
        <span className="text-[10px] text-zinc-500">⌘Y</span>
      </div>
      {!editing && (
        <div className="px-4 pb-3 text-xs text-zinc-500">
          {frame
            ? <button type="button" onClick={open} className="text-emerald-400 hover:text-emerald-300">Edit this frame's text here</button>
            : 'Select a text frame, or type in one, to read and edit its text here.'}
        </div>
      )}
      <div ref={box} className={`min-h-[160px] flex-1 overflow-y-auto bg-zinc-950/60 ${editing ? '' : 'hidden'}`} />
    </section>
  )
}
