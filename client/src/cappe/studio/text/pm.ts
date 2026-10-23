// A thread's paragraphs as a ProseMirror document and back. The editor that
// owns typing (text/editor.ts) works in this; the Studio keeps paragraphs.
//
// Each paragraph keeps its attributes; each text node carries one `ch` mark
// holding its run's character attributes (as the stored JSON). An empty
// paragraph keeps its run's attributes too (`ec`), so its line keeps its
// height and typing there takes its type. A line break is "\n" in the text.

import { Schema, type Mark, type Node as PMNode } from '@tiptap/pm/model'
import { mergeRuns, sparseChar, sparsePara } from '../model/doc'
import type { CharAttrs, Para, ParaAttrs, Run } from '../model/types'

export const schema = new Schema({
  nodes: {
    doc: { content: 'paragraph+' },
    paragraph: {
      content: 'text*',
      attrs: { pa: { default: '{}' }, ec: { default: '{}' } },
      parseDOM: [{ tag: 'p' }],
      toDOM: () => ['p', 0],
    },
    text: {},
  },
  marks: {
    ch: {
      attrs: { a: { default: '{}' } },
      parseDOM: [{ tag: 'span[data-ch]', getAttrs: (el) => ({ a: (el as HTMLElement).dataset.ch || '{}' }) }],
      toDOM: (m) => ['span', { 'data-ch': m.attrs.a }, 0],
    },
  },
})

const parse = <T>(s: string): T => {
  try { return JSON.parse(s) as T } catch { return {} as T }
}

export const markFor = (attrs: CharAttrs): Mark[] => {
  const a = sparseChar(attrs)
  return Object.keys(a).length ? [schema.marks.ch.create({ a: JSON.stringify(a) })] : []
}

export const attrsOf = (marks: readonly Mark[]): CharAttrs => {
  const m = marks.find((x) => x.type === schema.marks.ch)
  return m ? parse<CharAttrs>(m.attrs.a) : {}
}

export function toPM(paras: Para[]): PMNode {
  return schema.node('doc', null, paras.map((p) => {
    const { runs, ...pa } = p
    const kids = runs.filter((r) => r.t).map((r) => schema.text(r.t, markFor(r)))
    const ec = !kids.length ? JSON.stringify(sparseChar(runs[0] ?? { t: '' })) : '{}'
    return schema.node('paragraph', { pa: JSON.stringify(sparsePara(pa as ParaAttrs)), ec }, kids)
  }))
}

export function fromPM(doc: PMNode): Para[] {
  const out: Para[] = []
  doc.forEach((p) => {
    const runs: Run[] = []
    p.forEach((t) => { runs.push({ t: t.text ?? '', ...attrsOf(t.marks) }) })
    if (!runs.length) runs.push({ t: '', ...parse<CharAttrs>(p.attrs.ec) })
    out.push({ runs: mergeRuns(runs), ...sparsePara(parse<ParaAttrs>(p.attrs.pa)) })
  })
  return out
}

export const paraAttrsOf = (p: PMNode): ParaAttrs => parse<ParaAttrs>(p.attrs.pa)
export const emptyAttrsOf = (p: PMNode): CharAttrs => parse<CharAttrs>(p.attrs.ec)

/** A ProseMirror position ↔ [paragraph, offset]. */
export function posOf(doc: PMNode, para: number, offset: number): number {
  let pos = 0
  const n = Math.min(para, doc.childCount - 1)
  for (let i = 0; i < n; i++) pos += doc.child(i).nodeSize
  return pos + 1 + Math.min(offset, doc.child(n).content.size)
}

export function locOf(doc: PMNode, pos: number): [number, number] {
  let at = 0
  for (let i = 0; i < doc.childCount; i++) {
    const size = doc.child(i).nodeSize
    if (pos < at + size) return [i, Math.max(0, Math.min(doc.child(i).content.size, pos - at - 1))]
    at += size
  }
  return [doc.childCount - 1, doc.lastChild!.content.size]
}
