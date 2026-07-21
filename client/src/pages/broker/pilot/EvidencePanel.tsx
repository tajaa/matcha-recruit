import type { ContextPreview } from '../../../api/broker/brokerPilot'
import { EvidencePanel as PilotEvidencePanel } from '../../../components/pilot/EvidencePanel'
import { SOURCE_META, SYSTEM_LABEL, deriveSystems } from './shared'

/** Evidence browser: every grounding subsystem expands to its records — ref,
 *  one-line summary, date. Data is the already-fetched context corpus, split
 *  into per-subsystem buckets. Read-only (platform records, not documents). */
export function EvidencePanel({ context }: { context: ContextPreview | null }) {
  const systems = deriveSystems(context)

  return (
    <PilotEvidencePanel
      className="border-b border-white/[0.06]"
      helpText="Every record the analyst can cite, grouped by system. Expand a system to browse its records — the same refs appear as citations under each answer, so you can trace any claim back to its source."
      total={context ? context.total : null}
      emptyText="No platform data on file for this client yet. Upload documents, or add loss runs / EPL / property from the client's detail page to ground the analysis."
      sourceMeta={SOURCE_META}
      recordsFor={(key) => systems[key]}
      labelFor={(meta) => SYSTEM_LABEL[meta.key] ?? meta.label}
      notes={context?.notes ?? []}
    />
  )
}
