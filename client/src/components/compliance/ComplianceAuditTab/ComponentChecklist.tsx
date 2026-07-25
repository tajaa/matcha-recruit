import { useEffect, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { fetchRequirementComponents, attestRequirementComponent } from '../../../api/compliance/compliance'
import type { RequirementComponentChecklist as Checklist } from '../../../types/compliance'
import { STATUS_LABEL, STATUS_CLASS, rollupComponents } from './componentStatus'
import { AuditRevealModal } from './AuditRevealModal'

type Props = {
  locationId: string
  catalogId: string
  readOnly?: boolean
  /** For the animation's header card — already fetched onto the row. */
  employeeCount?: number | null
  /** Called after a successful attestation so the owning surface can refetch
   *  its own rollups (the Audit tab's statute/location coverage numbers come
   *  from a separate one-shot fetch and would otherwise stay pre-attest until
   *  a full page reload). */
  onAttested?: () => void
  /** Admin impersonation override, threaded down from ComplianceAuditTab. */
  companyId?: string
}

// The reveal is a full-screen one-time flourish, and the Audit tab mounts one
// checklist per (statute, location) row. Expanding two first-time rows back to
// back would otherwise stack two overlays with two animation loops, and only
// the last one answers ESC. Module-scoped because the constraint is global to
// the page, not to any one checklist.
let autoRevealActive = false

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
export function ComponentChecklist({
  locationId, catalogId, readOnly, employeeCount, onAttested, companyId,
}: Props) {
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
  // True only while THIS checklist holds the page-wide auto-reveal slot, so
  // the release below can't free a slot another row is using.
  const ownsAutoReveal = useRef(false)
  const seenKey = `matcha_audit_reveal_seen:${locationId}:${catalogId}`

  function releaseAutoReveal() {
    if (ownsAutoReveal.current) {
      ownsAutoReveal.current = false
      autoRevealActive = false
    }
  }

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setLoadError(null)
    fetchRequirementComponents(locationId, catalogId, companyId)
      .then((data) => {
        if (cancelled) return
        setChecklist(data)
        // Not-yet-seen AND nobody else is mid-reveal. When suppressed the seen
        // marker is deliberately NOT written — the row keeps its first-open
        // flourish for next time rather than silently losing it.
        if (!didAutoOpen.current && !safeGet(seenKey) && !autoRevealActive) {
          didAutoOpen.current = true
          ownsAutoReveal.current = true
          autoRevealActive = true
          safeSet(seenKey, '1')
          setRevealOpen(true)
        }
      })
      .catch(() => { if (!cancelled) setLoadError('Could not load the component checklist.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true; releaseAutoReveal() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locationId, catalogId, companyId])

  async function attest(componentKey: string) {
    setAttesting(componentKey)
    setAttestError(null)
    try {
      const updated = await attestRequirementComponent(locationId, catalogId, componentKey, {
        status: 'compliant',
      }, companyId)
      setChecklist((prev) => {
        if (!prev) return prev
        const components = prev.components.map(
          (c) => (c.component_key === componentKey ? updated : c),
        )
        // Recomputed, not carried over: the coverage line above the list reads
        // `checklist.summary`, so reusing the server's pre-attest summary
        // prints "0/5 known" over a row that just flipped to Compliant.
        return { ...prev, components, summary: rollupComponents(components) }
      })
      onAttested?.()
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
        onClose={() => { setRevealOpen(false); releaseAutoReveal() }}
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
