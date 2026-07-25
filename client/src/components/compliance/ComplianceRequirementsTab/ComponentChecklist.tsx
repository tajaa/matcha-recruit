import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { fetchRequirementComponents, attestRequirementComponent } from '../../../api/compliance/compliance'
import type { RequirementComponent, RequirementComponentChecklist as Checklist } from '../../../types/compliance'

type Props = {
  locationId: string
  catalogId: string
  readOnly?: boolean
}

const STATUS_LABEL: Record<RequirementComponent['status'], string> = {
  compliant: 'Compliant',
  non_compliant: 'Gap',
  in_progress: 'In progress',
  unknown: 'No evidence on file',
}

const STATUS_CLASS: Record<RequirementComponent['status'], string> = {
  compliant: 'bg-emerald-900/20 text-emerald-400 border-emerald-800/40',
  non_compliant: 'bg-red-900/20 text-red-400 border-red-800/40',
  in_progress: 'bg-amber-900/20 text-amber-400 border-amber-800/40',
  unknown: 'bg-white/[0.04] text-zinc-400 border-white/[0.08]',
}

// A statute decomposed into its checkable clauses (reqcomp01). `unknown`
// always reads as "no evidence on file" + a suggested fix + an attest
// control — never as a gap. The engine underneath is blind-never-violating
// (compliance_status.py) and this card must not contradict that by reusing
// "GAP" copy for the absence of a record.
export function ComponentChecklist({ locationId, catalogId, readOnly }: Props) {
  const [checklist, setChecklist] = useState<Checklist | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [attesting, setAttesting] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchRequirementComponents(locationId, catalogId)
      .then((data) => { if (!cancelled) setChecklist(data) })
      .catch(() => { if (!cancelled) setError('Could not load the component checklist.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [locationId, catalogId])

  async function attest(componentKey: string) {
    setAttesting(componentKey)
    try {
      const updated = await attestRequirementComponent(locationId, catalogId, componentKey, {
        status: 'compliant',
      })
      setChecklist((prev) => prev && {
        ...prev,
        components: prev.components.map((c) => (c.component_key === componentKey ? updated : c)),
      })
    } catch {
      setError('Could not save that attestation.')
    } finally {
      setAttesting(null)
    }
  }

  if (loading) {
    return (
      <div className="px-4 py-4 flex items-center gap-2 text-xs text-zinc-500">
        <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading checklist...
      </div>
    )
  }
  if (error) {
    return <p className="px-4 py-4 text-xs text-red-400">{error}</p>
  }
  if (!checklist) return null

  const { summary } = checklist
  return (
    <div className="px-4 py-3 bg-white/[0.015] border-t border-white/[0.06]">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[11px] text-zinc-500">
          {summary.known}/{summary.total} components with a known status
        </span>
        <span className="text-[11px] text-zinc-500">
          {summary.coverage_pct == null ? '—' : `${summary.coverage_pct}%`}
        </span>
      </div>
      <div className="space-y-2">
        {checklist.components.map((c) => (
          <div key={c.component_key} className="rounded-lg border border-white/[0.06] p-2.5">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-xs font-medium text-zinc-200">{c.label}</p>
                <p className="text-[11px] text-zinc-500 mt-0.5">{c.question}</p>
              </div>
              <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded border ${STATUS_CLASS[c.status]}`}>
                {STATUS_LABEL[c.status]}
              </span>
            </div>
            {c.status !== 'compliant' && c.suggested_fix && (
              <p className="text-[11px] text-zinc-500 mt-1.5">
                <span className="text-zinc-600">Suggested fix: </span>{c.suggested_fix}
              </p>
            )}
            <div className="flex items-center justify-between mt-1.5">
              {c.statute_citation && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-900/20 text-emerald-400 border border-emerald-800/40">
                  {c.statute_citation}
                </span>
              )}
              {/* Derivable components are auto-checked from the tenant's own
                  records — the server refuses attestation on them (409), so
                  the control must not render for them at all. */}
              {!readOnly && !c.derivable && (
                <button
                  type="button"
                  disabled={attesting === c.component_key}
                  onClick={() => attest(c.component_key)}
                  className="text-[11px] text-zinc-500 hover:text-emerald-400 transition-colors disabled:opacity-50">
                  {attesting === c.component_key ? 'Saving...' : 'We have this'}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
