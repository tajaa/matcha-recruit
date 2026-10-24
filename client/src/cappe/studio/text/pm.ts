// A thread's paragraphs as a ProseMirror document and back. The editor that
// owns typing (text/editor.ts) works in this; the Studio keeps paragraphs.
//
// Each paragraph keeps its attributes; each text node carries one `ch` mark
// holding its run's character attributes (as the stored JSON). An empty
// paragraph keeps its run's attributes too (`ec`), so its line keeps its
// height and typing there takes its type. A line break is "\n" in the text.

import { Fragment, Schema, Slice, type Mark, type Node as PMNode } from '@tiptap/pm/model'
import { mergeRuns, sparseChar, sparsePara } from '../model/doc'
import { resolveChar } from '../model/identity'
import type { CharAttrs, MagazineIdentity, Para, ParaAttrs, Run } from '../model/types'

export const schema = new Schema({
  nodes: {
    doc: { content: 'paragraph+' },
    paragraph: {
      content: 'text*',
      attrs: { pa: { default: '{}' }, ec: { default: '{}' } },
      parseDOM: [{ tag: 'p', getAttrs: (el) => {
        try {
          const raw = JSON.parse((el as HTMLElement).dataset.pa || '{}')
          return { pa: JSON.stringify(sparsePara({ ...raw, style: undefined })) }
        } catch { return { pa: '{}' } }
      } }],
      toDOM: (p) => ['p', { 'data-pa': p.attrs.pa }, 0],
    },
    text: {},
  },
  marks: {
    ch: {
      attrs: { a: { default: '{}' } },
      parseDOM: [{ tag: 'span[data-ch]', getAttrs: (el) => {
        try {
          const raw = JSON.parse((el as HTMLElement).dataset.ch || '{}')
          return { a: JSON.stringify(sparseChar({ ...raw, style: undefined, swatch: undefined }, true)) }
        } catch { return { a: '{}' } }
      } }],
      toDOM: (m) => ['span', { 'data-ch': m.attrs.a }, 0],
    },
  },
})

const parse = <T>(s: string): T => {
  try { return JSON.parse(s) as T } catch { return {} as T }
}

export const markFor = (attrs: CharAttrs, inherited = false): Mark[] => {
  const a = sparseChar(attrs, inherited)
  return Object.keys(a).length ? [schema.marks.ch.create({ a: JSON.stringify(a) })] : []
}

export const attrsOf = (marks: readonly Mark[]): CharAttrs => {
  const m = marks.find((x) => x.type === schema.marks.ch)
  return m ? parse<CharAttrs>(m.attrs.a) : {}
}

export function toPM(paras: Para[]): PMNode {
  return schema.node('doc', null, paras.map((p) => {
    const { runs, ...pa } = p
    const kids = runs.filter((r) => r.t).map((r) => schema.text(r.t, markFor(r, !!p.style)))
    const ec = !kids.length ? JSON.stringify(sparseChar(runs[0] ?? { t: '' }, !!p.style)) : '{}'
    return schema.node('paragraph', { pa: JSON.stringify(sparsePara(pa as ParaAttrs)), ec }, kids)
  }))
}

export function fromPM(doc: PMNode): Para[] {
  const out: Para[] = []
  doc.forEach((p) => {
    const runs: Run[] = []
    p.forEach((t) => { runs.push({ t: t.text ?? '', ...attrsOf(t.marks) }) })
    if (!runs.length) runs.push({ t: '', ...parse<CharAttrs>(p.attrs.ec) })
    const pa = sparsePara(parse<ParaAttrs>(p.attrs.pa))
    out.push({ runs: mergeRuns(runs, !!pa.style), ...pa })
  })
  return out
}

export const paraAttrsOf = (p: PMNode): ParaAttrs => parse<ParaAttrs>(p.attrs.pa)
export const emptyAttrsOf = (p: PMNode): CharAttrs => parse<CharAttrs>(p.attrs.ec)

/** Clipboard HTML carries appearance, never document-local style IDs. */
export function portableSlice(slice: Slice, identity?: MagazineIdentity, paragraphAttrs: ParaAttrs = {}): Slice {
  if (!identity) return slice
  const copy = (node: PMNode, base: CharAttrs = {}): PMNode => {
    if (node.isText) return node.mark([schema.marks.ch.create({ a: JSON.stringify(resolveChar(attrsOf(node.marks), base, identity)) })])
    const raw = node.type === schema.nodes.paragraph ? paraAttrsOf(node) : {}
    const paragraph = identity.paragraphs.find((p) => p.id === raw.style)
    const children: PMNode[] = []
    node.forEach((child) => children.push(copy(child, paragraph?.char ?? base)))
    const pa = { ...raw }; delete pa.style
    return node.type.create({ ...node.attrs, pa: JSON.stringify({ ...paragraph?.para, ...pa }) }, children, node.marks)
  }
  const children: PMNode[] = []
  const base = identity.paragraphs.find((p) => p.id === paragraphAttrs.style)?.char
  slice.content.forEach((node) => children.push(copy(node, base)))
  return new Slice(Fragment.fromArray(children), slice.openStart, slice.openEnd)
}

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
