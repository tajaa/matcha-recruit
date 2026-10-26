import { composeDoc, type Measure } from '../../studio/compose/compose'
import { portableCollection } from '../../studio/model/collections'
import type { Doc } from '../../studio/model/types'

/** Keep the source collection reusable. Its masthead becomes this magazine's;
 * long names are fitted with the same measurements Studio uses. */
export function magazineStarter(source: Doc, name: string, measure: Measure): Doc {
  let doc = portableCollection(source)
  const mastheads = new Set(doc.items.filter((i) => i.kind === 'text' && i.name === 'Masthead').map((i) => i.id))
  const changed = new Set(doc.threads.filter((t) => t.frames.some((id) => mastheads.has(id))).map((t) => t.id))
  doc = { ...doc, threads: doc.threads.map((t) => changed.has(t.id) ? {
    ...t, paras: [{ ...t.paras[0], runs: [{ ...t.paras[0].runs[0], t: name.trim() || 'Your magazine' }] }],
  } : t) }
  // Only shrink the personalised masthead, leaving the collection's other type intact.
  for (let attempt = 0; attempt < 32; attempt++) {
    const composed = composeDoc(doc, measure, true)
    const over = new Set([...composed.overset].filter((id) => changed.has(id)))
    if (!over.size) return composed.doc
    doc = { ...doc, threads: doc.threads.map((t) => !over.has(t.id) ? t : {
      ...t, paras: t.paras.map((p) => ({ ...p, lead: (p.lead ?? 60) * 0.9,
        runs: p.runs.map((r) => ({ ...r, size: (r.size ?? 60) * 0.9 })) })),
    }) }
  }
  return composeDoc(doc, measure, true).doc
}
