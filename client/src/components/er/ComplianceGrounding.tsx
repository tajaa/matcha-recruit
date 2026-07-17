import type { ComplianceCitation } from '../../types/er'

// Renders the codified state/federal employment-law requirements the AI grounded
// its guidance/outcome in, as citation chips. Renders nothing when there are no
// citations — identical to pre-grounding behavior. Shared by ERGuidancePanel and
// EROutcomePanel so both surfaces present grounding identically.
export function ComplianceGrounding({ citations }: { citations?: ComplianceCitation[] | null }) {
  if (!citations || citations.length === 0) return null
  return (
    <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/[0.04] px-4 py-3 space-y-2">
      <p className="text-[11px] uppercase tracking-wide text-emerald-400/80">Legal grounding</p>
      <div className="flex flex-wrap gap-1.5">
        {citations.map((c) => {
          const label = `${c.state}${c.statute_citation ? ` · ${c.statute_citation}` : ''}`
          const chip = (
            <span
              className="inline-flex items-center gap-1 rounded-md border border-emerald-500/25 bg-emerald-500/10 px-2 py-1 text-[11px] text-emerald-200"
              title={c.title}
            >
              {label}
            </span>
          )
          return c.source_url ? (
            <a key={c.cid} href={c.source_url} target="_blank" rel="noopener noreferrer" className="hover:opacity-80">
              {chip}
            </a>
          ) : (
            <span key={c.cid}>{chip}</span>
          )
        })}
      </div>
    </div>
  )
}
