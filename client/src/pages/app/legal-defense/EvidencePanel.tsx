import { useState } from 'react'
import type { EvidencePreview } from '../../../api/legal-defense/legalDefense'
import { EvidencePanel as PilotEvidencePanel } from '../../../components/pilot/EvidencePanel'
import { SOURCE_META } from './shared'
import { RecordViewer, type ViewerTarget } from './RecordViewer'

/** Evidence browser: every in-scope source expands to its record list —
 *  ref, one-line summary, date. Data is the already-fetched preview corpus.
 *  Clicking a record opens it in the shared RecordViewer doc-viewer in place —
 *  it never navigates away from the matter workbench. */
export function EvidencePanel({ evidence }: { evidence: EvidencePreview | null }) {
  const [selected, setSelected] = useState<ViewerTarget | null>(null)

  return (
    <PilotEvidencePanel
      helpText="Each record here is real data from your own systems. The record ids the analyst cites in chat trace back to one of these — click any to open it."
      total={evidence ? evidence.total : null}
      emptyText={evidence?.theory
        ? `No records match this matter's ${evidence.theory.label} subject inside its evidence window. Widen the window, or change the subject to "All records" under Legal landscape.`
        : "No records fall inside the matter's evidence window. Widen the window when creating the matter to pull more history in."}
      sourceMeta={SOURCE_META}
      recordsFor={(key) => evidence?.sources[key]?.records}
      labelFor={(meta) => evidence?.sources[meta.key]?.label ?? meta.label}
      notes={evidence?.notes ?? []}
      onRecordClick={(r, sourceLabel) => setSelected({ cid: r.cid, ref: r.ref, sourceLabel, summary: r.summary, when: r.when })}
      footer={selected && <RecordViewer target={selected} onClose={() => setSelected(null)} />}
    />
  )
}
