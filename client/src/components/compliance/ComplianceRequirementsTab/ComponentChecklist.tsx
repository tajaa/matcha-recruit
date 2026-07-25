import { useEffect, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { fetchRequirementComponents, attestRequirementComponent } from '../../../api/compliance/compliance'
import type { RequirementComponentChecklist as Checklist } from '../../../types/compliance'
import { STATUS_LABEL, STATUS_CLASS } from './componentStatus'
import { AuditRevealModal } from './AuditRevealModal'

type Props = {
  locationId: string
  catalogId: string
  readOnly?: boolean
  /** For the animation's header card — already fetched onto the row. */
  employeeCount?: number | null
}

function safeGet(key: string): string | null {
  try { return localStorage.getItem(key) } catch { return null }
}
function safeSet(key: string, value: string): void {
  try { localStorage.setItem(key, value) } catch { /* Safari private mode etc — non-fatal */ }
}

// A statute decomposed into its checkable clauses (reqcomp01). `unknown`
// always reads as "no evidence on file" + a suggested fix + an attest
// control — never as a gap. The engine underneath is blind-never-violating
// (compliance_status.py) and this card must not contradict that by reusing
// "GAP" copy for the absence of a record.
export function ComponentChecklist({ locationId, catalogId, readOnly, employeeCount }: Props) {
  const [checklist, setChecklist] = useState<Checklist | null>(null)
  const [loading, setLoading] = useState(true)
  // Load failures are fatal (nothing rendered underneath to fall back to) and
  // block the whole card below. Attest failures are NOT — the checklist is
  // already loaded and showing real data; a failed attestation must not wipe
  // five clauses, the coverage rollup, and Replay down to one line of text
  // with no retry path. Two separate states, two separate render paths.
  const [loadError, setLoadError] = useState<string | null>(null)
  const [attestError, setAttestError] = useState<string | null>(null)
  const [attesting, setAttesting] = useState<string | null>(null)
  const [revealOpen, setRevealOpen] = useState(false)
  const [runId, setRunId] = useState(0)
  const didAutoOpen = useRef(false)
  const seenKey = `matcha_audit_reveal_seen:${locationId}:${catalogId}`

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setLoadError(null)
    fetchRequirementComponents(locationId, catalogId)
      .then((data) => {
        if (cancelled) return
        setChecklist(data)
        if (!didAutoOpen.current && !safeGet(seenKey)) {
          didAutoOpen.current = true
          safeSet(seenKey, '1')
          setRevealOpen(true)
        }
      })
      .catch(() => { if (!cancelled) setLoadError('Could not load the component checklist.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locationId, catalogId])

  async function attest(componentKey: string) {
    setAttesting(componentKey)
    setAttestError(null)
    try {
      const updated = await attestRequirementComponent(locationId, catalogId, componentKey, {
        status: 'compliant',
      })
      setChecklist((prev) => prev && {
        ...prev,
        components: prev.components.map((c) => (c.component_key === componentKey ? updated : c)),
      })
    } catch {
      setAttestError('Could not save that attestation.')
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
  if (loadError) {
    return <p className="px-4 py-4 text-xs text-red-400">{loadError}</p>
  }
  if (!checklist) return null

  const { summary } = checklist
  return (
    <div className="px-4 py-3 bg-white/[0.015] border-t border-white/[0.06]">
      <AuditRevealModal
        open={revealOpen}
        onClose={() => setRevealOpen(false)}
        checklist={checklist}
        employeeCount={employeeCount}
        runId={runId}
      />
      {attestError && (
        <div className="flex items-center justify-between mb-2 rounded border border-red-800/40 bg-red-950/20 px-2.5 py-1.5">
          <span className="text-[11px] text-red-400">{attestError}</span>
          <button
            type="button"
            onClick={() => setAttestError(null)}
            className="text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            Dismiss
          </button>
        </div>
      )}
      <div className="flex items-center justify-between mb-2">
        <span className="text-[11px] text-zinc-500">
          {summary.known}/{summary.total} components with a known status
        </span>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => { setRunId((n) => n + 1); setRevealOpen(true) }}
            className="text-[11px] text-zinc-500 hover:text-amber-400 transition-colors"
          >
            ↻ Replay audit
          </button>
          <span className="text-[11px] text-zinc-500">
            {summary.coverage_pct == null ? '—' : `${summary.coverage_pct}%`}
          </span>
        </div>
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
