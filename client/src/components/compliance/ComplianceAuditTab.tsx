import { useEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react'
import { useComplianceAudit } from '../../hooks/compliance/useComplianceAudit'
import { ComponentChecklist } from './ComplianceAuditTab/ComponentChecklist'
import { exposureLabel } from './ComplianceAuditTab/AuditRevealModal'
import type { ComplianceAuditLocationRow, ComplianceAuditStatute } from '../../types/compliance'

type Props = {
  /** Statute to scroll to + highlight, set when opened from a Requirements
   *  row's "Audit →" link. */
  targetCatalogId?: string | null
  onTargetConsumed?: () => void
  readOnly?: boolean
  /** Admin impersonation override — the target company's id, from the
   *  `?company_id=` query param. Undefined for a normal client session. */
  companyId?: string
}

function locationRowKey(statuteId: string, locationId: string): string {
  return `${statuteId}::${locationId}`
}

function CoverageBadge({ summary }: { summary: ComplianceAuditLocationRow['summary'] }) {
  return (
    <span className="text-[11px] text-zinc-500 tabular-nums">
      {summary.known}/{summary.total} known
      {summary.coverage_pct != null && (
        <span className="text-zinc-600"> · {summary.coverage_pct}%</span>
      )}
    </span>
  )
}

function StatuteCard({
  statute,
  expandedRows,
  toggleRow,
  isHighlighted,
  readOnly,
  onAttested,
  companyId,
}: {
  statute: ComplianceAuditStatute
  expandedRows: Set<string>
  toggleRow: (key: string) => void
  isHighlighted: boolean
  readOnly?: boolean
  onAttested: () => void
  companyId?: string
}) {
  const exposureText = exposureLabel(statute.summary, statute.exposure?.penalty ?? null)
  return (
    <div
      data-statute-id={statute.jurisdiction_requirement_id}
      className={`rounded-lg border p-4 transition-colors ${
        isHighlighted
          ? 'border-emerald-500/40 bg-emerald-500/[0.07] ring-1 ring-inset ring-emerald-500/40'
          : 'border-white/[0.08] bg-white/[0.02]'
      }`}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-zinc-100">{statute.title}</p>
          <p className="text-[11px] text-zinc-500 mt-0.5">
            {statute.statute_citation}
            {statute.authority_level && ` · ${statute.authority_level}`}
            {statute.authority_name && ` · ${statute.authority_name}`}
            {` · ${statute.component_count} clauses`}
          </p>
        </div>
        <div className="text-right shrink-0">
          <div className="font-mono text-sm font-bold text-amber-300 tabular-nums">
            {statute.summary.known}/{statute.summary.total}
          </div>
          <div className="text-[10px] text-zinc-500 uppercase tracking-wide">known</div>
        </div>
      </div>

      {exposureText && (
        <p className="text-[11px] text-amber-400/80 mt-2">{exposureText}</p>
      )}

      <div className="mt-3 divide-y divide-white/[0.04] border-t border-white/[0.06]">
        {statute.locations.map((loc) => {
          const key = locationRowKey(statute.jurisdiction_requirement_id, loc.location_id)
          const open = expandedRows.has(key)
          return (
            <div key={loc.location_id}>
              <button
                type="button"
                onClick={() => toggleRow(key)}
                className="w-full flex items-center justify-between gap-3 py-2 text-left hover:bg-white/[0.02] transition-colors"
              >
                <span className="flex items-center gap-1.5 text-xs text-zinc-300">
                  {open ? <ChevronDown className="w-3.5 h-3.5 text-zinc-500" /> : <ChevronRight className="w-3.5 h-3.5 text-zinc-500" />}
                  {loc.location_label}
                  {loc.employee_count != null && loc.employee_count > 0 && (
                    <span className="text-zinc-600">· {loc.employee_count} employees</span>
                  )}
                </span>
                <CoverageBadge summary={loc.summary} />
              </button>
              {open && (
                <ComponentChecklist
                  locationId={loc.location_id}
                  catalogId={statute.jurisdiction_requirement_id}
                  readOnly={readOnly}
                  employeeCount={loc.employee_count}
                  onAttested={onAttested}
                  companyId={companyId}
                />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function ComplianceAuditTab({ targetCatalogId, onTargetConsumed, readOnly, companyId }: Props) {
  const { data, loading, error, refreshError, refetch, refresh } = useComplianceAudit(companyId)
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())
  const [highlightId, setHighlightId] = useState<string | null>(null)
  const didFocus = useRef<string | null>(null)

  function toggleRow(key: string) {
    setExpandedRows((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  // Focus a statute cited by a Requirements row's "Audit →" link: scroll it
  // into view, highlight it briefly. Mirrors useTargetReqFocus.ts, simpler
  // (no accordion to expand) — and for the same reason that file documents,
  // the two one-shot timers below are deliberately NOT cleaned up: a
  // clearTimeout in a cleanup fired by consuming the target would kill the
  // scroll before it ever ran.
  useEffect(() => {
    if (!targetCatalogId || loading || !data) return
    if (didFocus.current === targetCatalogId) return
    const match = data.statutes.find((s) => s.jurisdiction_requirement_id === targetCatalogId)
    if (!match) { onTargetConsumed?.(); return }
    didFocus.current = targetCatalogId
    setHighlightId(targetCatalogId)
    setTimeout(() => {
      document.querySelector(`[data-statute-id="${targetCatalogId}"]`)
        ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 60)
    setTimeout(() => setHighlightId(null), 4000)
    onTargetConsumed?.()
  }, [targetCatalogId, loading, data, onTargetConsumed])

  if (loading) {
    return (
      <div className="px-4 py-8 flex items-center gap-2 text-sm text-zinc-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading audit overview...
      </div>
    )
  }
  if (error) {
    return (
      <div className="px-4 py-8 text-sm text-red-400">
        {error}{' '}
        <button type="button" onClick={refetch} className="underline hover:text-red-300">Retry</button>
      </div>
    )
  }
  if (!data || data.statutes.length === 0) {
    return (
      <div className="px-4 py-8 text-sm text-zinc-500 max-w-lg">
        No statute in your jurisdictions has a per-clause audit yet. Requirements are
        still tracked at the obligation level on the Requirements tab.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <p className="text-[11px] text-zinc-500">
        {data.statutes.length} statute{data.statutes.length !== 1 ? 's' : ''} · {data.location_count} location{data.location_count !== 1 ? 's' : ''}
      </p>
      {refreshError && (
        <p className="text-[11px] text-red-400">{refreshError}</p>
      )}
      {data.statutes.map((statute) => (
        <StatuteCard
          key={statute.jurisdiction_requirement_id}
          statute={statute}
          expandedRows={expandedRows}
          toggleRow={toggleRow}
          isHighlighted={highlightId === statute.jurisdiction_requirement_id}
          readOnly={readOnly}
          // An attestation moves the statute + location coverage numbers, which
          // come from this one-shot fetch and not from the checklist below. A
          // failed refresh here surfaces as `refreshError` above, not a
          // full-tab replacement — the data on screen is still valid.
          onAttested={refresh}
          companyId={companyId}
        />
      ))}
    </div>
  )
}
