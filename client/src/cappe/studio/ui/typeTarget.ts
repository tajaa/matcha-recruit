// What the Character and Paragraph panels act on: the text being typed in
// (its selection, or what the caret will type), else every word in the text
// frames selected.

import { charOf, paraOf, paraText, type FullChar, type FullPara } from '../model/doc'
import { applyChar, applyPara, setParas } from '../model/ops'
import type { CharAttrs, Doc, ParaAttrs } from '../model/types'
import type { State } from '../store/store'
import type { StudioCtx } from './context'

/** The threads of the selected text frames (when nothing is being typed in). */
export function selectedThreads(s: State): string[] {
  const frames = new Set(s.doc.items.filter((i) => s.selection.includes(i.id) && i.kind === 'text').map((i) => i.id))
  return s.doc.threads.filter((t) => t.frames.some((f) => frames.has(f))).map((t) => t.id)
}

export function hasTypeTarget(s: State): boolean {
  return !!s.editing || selectedThreads(s).length > 0
}

/** The type shown in the panels: at the caret, or the first word of the frames. */
export function currentType(c: StudioCtx, s: State): { char: FullChar; para: FullPara } {
  if (s.editing) return { char: charOf(c.editor.currentChar()), para: paraOf(c.editor.currentPara()) }
  const t = s.doc.threads.find((x) => x.id === selectedThreads(s)[0])
  const p = t?.paras[0]
  return { char: charOf(p?.runs[0] ?? { t: '' }), para: paraOf(p ?? { runs: [] }) }
}

const everywhere = (doc: Doc, threads: string[], fn: (paras: Doc['threads'][number]['paras']) => Doc['threads'][number]['paras']) =>
  threads.reduce((d, id) => {
    const t = d.threads.find((x) => x.id === id)
    return t ? setParas(d, id, fn(t.paras)) : d
  }, doc)

export function setChar(c: StudioCtx, attrs: CharAttrs): void {
  const s = c.store.get()
  if (s.editing) { c.editor.applyChar(attrs); return }
  const threads = selectedThreads(s)
  if (!threads.length) return
  c.store.edit((d) => everywhere(d, threads, (paras) => {
    const last = paras.length - 1
    return applyChar(paras, [0, 0], [last, paraText(paras[last]).length], attrs)
  }))
}

export function setPara(c: StudioCtx, attrs: ParaAttrs): void {
  const s = c.store.get()
  if (s.editing) { c.editor.applyPara(attrs); return }
  const threads = selectedThreads(s)
  if (!threads.length) return
  c.store.edit((d) => everywhere(d, threads, (paras) => applyPara(paras, 0, paras.length - 1, attrs)))
}
