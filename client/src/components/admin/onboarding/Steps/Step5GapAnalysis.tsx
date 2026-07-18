import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2 } from 'lucide-react'

import {
  adminOnboarding,
  type GapCheckResult,
  type ResolvedScopeMissing,
} from '../../../../api/admin/adminOnboarding'
import GapCard from '../GapCard'
import { ErrorBox, PrimaryButton, type StepProps } from './_shared'

// ── Gap-analysis helpers (shared by Step 5) ────────────────────────────

function missingId(m: ResolvedScopeMissing): string {
  return [
    m.category_slug || '?',
    m.scope_level || '?',
    m.state || '-',
    m.county || '-',
    m.city || '-',
  ].join('::')
}

function jurisdictionKey(
  state?: string | null,
  county?: string | null,
  city?: string | null,
): string {
  return [state, county, city].filter(Boolean).join(' / ') || 'Federal'
}

function groupByKey<T>(items: T[], key: (item: T) => string): Map<string, T[]> {
  const buckets = new Map<string, T[]>()
  for (const item of items) {
    const k = key(item)
    const arr = buckets.get(k)
    if (arr) arr.push(item)
    else buckets.set(k, [item])
  }
  return buckets
}

// ── Step 5: Gap Analysis (coverage + missing + AI safety net) ──────────

export function Step5GapAnalysis({ session, onUpdated, onNext }: StepProps) {
  const persistedGap =
    (session.resolved_scope as unknown as { gap_check?: GapCheckResult } | null)?.gap_check ?? null

  const [approved, setApproved] = useState<Set<string>>(new Set())
  const [dispatchBusy, setDispatchBusy] = useState(false)
  const [advanceBusy, setAdvanceBusy] = useState(false)
  const [dispatchedCount, setDispatchedCount] = useState<number | null>(null)
  const [gap, setGap] = useState<GapCheckResult | null>(persistedGap)
  const [gapBusy, setGapBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const resolved = session.resolved_scope
  const missing = resolved?.missing || []
  const existing = resolved?.existing || []

  const missingByJurisdiction = useMemo(
    () => groupByKey(missing, (m) => jurisdictionKey(m.state, m.county, m.city)),
    [missing],
  )

  const existingByCategory = useMemo(
    () => groupByKey(existing, (e) => e.category_slug || 'other'),
    [existing],
  )

  const suggestedJurisdictionsByState = useMemo(() => {
    if (!gap) return new Map<string, GapCheckResult['suggested_jurisdictions']>()
    return groupByKey(gap.suggested_jurisdictions, (j) => j.state || 'Federal')
  }, [gap])

  const totalSuggestions = gap
    ? gap.suggested_compliance_categories.length +
      gap.suggested_certifications.length +
      gap.suggested_licenses.length +
      gap.suggested_jurisdictions.length
    : 0

  function toggle(id: string) {
    setApproved((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleBucket(ids: string[], allSelected: boolean) {
    setApproved((prev) => {
      const next = new Set(prev)
      if (allSelected) ids.forEach((id) => next.delete(id))
      else ids.forEach((id) => next.add(id))
      return next
    })
  }

  async function dispatchResearch() {
    setDispatchBusy(true)
    setError(null)
    try {
      const res = await adminOnboarding.dispatchResearch(session.id, Array.from(approved))
      setDispatchedCount(res.dispatched.length)
      setApproved(new Set())
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't start research")
    } finally {
      setDispatchBusy(false)
    }
  }

  async function runGapCheck() {
    setGapBusy(true)
    setError(null)
    try {
      const res = await adminOnboarding.gapCheck(session.id)
      setGap(res.gap_check)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Gap check failed')
    } finally {
      setGapBusy(false)
    }
  }

  async function advance() {
    setAdvanceBusy(true)
    setError(null)
    try {
      const updated = await adminOnboarding.patchSession(session.id, { step: 'review' })
      onUpdated(updated)
      onNext()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not advance')
    } finally {
      setAdvanceBusy(false)
    }
  }

  return (
    <div className="max-w-3xl">
      <h2 className="text-base font-medium text-zinc-100 mb-1">Gap Analysis</h2>
      <p className="text-sm text-zinc-400 mb-2">
        {missing.length} to research · {existing.length} already covered
        {gap ? ` · AI flagged ${totalSuggestions} extra${totalSuggestions === 1 ? '' : 's'}` : ''}
      </p>
      {session.company_id && (
        <Link
          to={`/admin/gap-analysis/company/${session.company_id}`}
          className="inline-flex items-center gap-1 text-xs font-medium text-vsc-accent hover:opacity-80 mb-5"
        >
          Open full gap dashboard →
        </Link>
      )}
      <ErrorBox message={error} />

      {/* Card A — Needs research (actionable) */}
      {missing.length > 0 ? (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-4 mb-4">
          <div className="mb-3">
            <div className="text-sm font-medium text-amber-100">
              Needs research · {missing.length}
            </div>
            <div className="text-[11px] text-amber-200/70">
              Tick what to dispatch — background workers research and write to the compliance DB.
            </div>
          </div>

          <div className="space-y-3 max-h-[28rem] overflow-auto pr-1">
            {Array.from(missingByJurisdiction.entries()).map(([jKey, items]) => {
              const ids = items.map(missingId)
              const allSelected = ids.every((id) => approved.has(id))
              return (
                <div key={jKey}>
                  <div className="flex items-center justify-between mb-1">
                    <div className="text-[11px] uppercase tracking-wider text-zinc-400">
                      {jKey} · {items.length}
                    </div>
                    <button
                      onClick={() => toggleBucket(ids, allSelected)}
                      className="text-[11px] text-amber-300 hover:text-amber-200"
                    >
                      {allSelected ? 'Clear' : 'Select all'}
                    </button>
                  </div>
                  <div className="space-y-2">
                    {items.map((m) => {
                      const id = missingId(m)
                      return (
                        <GapCard
                          key={id}
                          gap={m}
                          selected={approved.has(id)}
                          onToggle={() => toggle(id)}
                          disabled={dispatchBusy}
                        />
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>

          <div className="flex items-center gap-3 mt-4 pt-3 border-t border-amber-500/20">
            <button
              onClick={() => void dispatchResearch()}
              disabled={dispatchBusy || approved.size === 0}
              className="inline-flex items-center gap-2 px-4 h-9 rounded-md bg-amber-500/90 hover:bg-amber-500 text-zinc-950 text-sm font-medium disabled:opacity-50"
            >
              {dispatchBusy && <Loader2 className="w-4 h-4 animate-spin" />}
              Start research ({approved.size})
            </button>
            {dispatchedCount !== null && (
              <div className="text-xs text-emerald-300">
                {dispatchedCount} job{dispatchedCount === 1 ? '' : 's'} started — results land in the compliance DB.
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3 text-sm text-emerald-200 mb-4">
          Nothing new to research — every resolved requirement is already in the compliance DB.
        </div>
      )}

      {/* Card B — Already covered (informational, collapsed) */}
      {existing.length > 0 && (
        <details className="group rounded-md border border-vsc-border bg-vsc-panel p-4 mb-4">
          <summary className="cursor-pointer list-none flex items-center justify-between [&::-webkit-details-marker]:hidden">
            <div className="text-[11px] uppercase tracking-wider text-emerald-400">
              Already covered · {existing.length}
            </div>
            <span className="text-[11px] text-zinc-500 group-open:hidden">Show</span>
            <span className="text-[11px] text-zinc-500 hidden group-open:inline">Hide</span>
          </summary>
          <div className="mt-3 space-y-3 max-h-72 overflow-auto pr-1">
            {Array.from(existingByCategory.entries()).map(([cat, items]) => (
              <div key={cat}>
                <div className="text-[11px] uppercase tracking-wider text-zinc-500 mb-1">
                  {cat.replace(/_/g, ' ')} · {items.length}
                </div>
                <ul className="text-sm text-zinc-300 space-y-0.5">
                  {items.map((e) => (
                    <li key={e.requirement_id}>
                      • {e.title || e.canonical_key || e.requirement_id}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </details>
      )}

      {/* Card C — AI safety net (read-only suggestion) */}
      <div className="rounded-md border border-vsc-border bg-vsc-panel p-4 mb-6">
        <div className="flex items-start justify-between gap-3 mb-2">
          <div>
            <div className="text-sm font-medium text-zinc-100">AI safety net</div>
            <div className="text-[11px] text-zinc-500">
              Gemini re-reads the manifest and flags anything the wizard missed. Read-only — Finalize on the next step.
            </div>
          </div>
          <button
            onClick={() => void runGapCheck()}
            disabled={gapBusy}
            className="inline-flex items-center gap-2 px-3 h-8 rounded-md border border-vsc-border hover:border-zinc-500 text-xs text-zinc-200 disabled:opacity-50 shrink-0"
          >
            {gapBusy && <Loader2 className="w-3 h-3 animate-spin" />}
            {gap ? 'Re-run' : 'Run gap check'}
          </button>
        </div>

        {gap && totalSuggestions === 0 && (
          <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3 text-sm text-emerald-200 mt-3">
            <div className="font-medium">Manifest looks comprehensive.</div>
            {gap.summary && (
              <div className="text-xs text-emerald-300/80 mt-0.5">{gap.summary}</div>
            )}
          </div>
        )}

        {gap && totalSuggestions > 0 && (
          <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3 space-y-4 mt-3">
            {gap.summary && <div className="text-xs text-amber-200">{gap.summary}</div>}

            {gap.suggested_jurisdictions.length > 0 && (
              <div>
                <div className="text-[11px] uppercase tracking-wider text-amber-300 mb-1">
                  New jurisdictions to track
                </div>
                <div className="space-y-2">
                  {Array.from(suggestedJurisdictionsByState.entries()).map(([state, items]) => (
                    <div key={state}>
                      <div className="text-[11px] text-zinc-400">{state}</div>
                      <ul className="text-sm text-zinc-100 space-y-0.5 ml-2">
                        {items.map((j, i) => (
                          <li key={i}>
                            • {jurisdictionKey(j.state, j.county, j.city)}
                            {j.reason && (
                              <div className="text-[11px] text-zinc-400 ml-3">{j.reason}</div>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {(gap.suggested_compliance_categories.length > 0 ||
              gap.suggested_certifications.length > 0 ||
              gap.suggested_licenses.length > 0) && (
              <div>
                <div className="text-[11px] uppercase tracking-wider text-amber-300 mb-1">
                  Items to add to manifest
                </div>
                <ul className="text-sm text-zinc-100 space-y-1.5">
                  {gap.suggested_compliance_categories.map((c, i) => (
                    <li key={`c-${i}`}>
                      <span className="text-[10px] uppercase tracking-wider text-zinc-500 mr-2">
                        Category
                      </span>
                      {c.category_slug.replace(/_/g, ' ')}
                      <span className="text-zinc-500"> · {c.scope}</span>
                      {c.reason && (
                        <div className="text-[11px] text-zinc-400 ml-3">{c.reason}</div>
                      )}
                    </li>
                  ))}
                  {gap.suggested_certifications.map((c, i) => (
                    <li key={`cert-${i}`}>
                      <span className="text-[10px] uppercase tracking-wider text-zinc-500 mr-2">
                        Cert
                      </span>
                      {c.name}
                      {c.reason && (
                        <div className="text-[11px] text-zinc-400 ml-3">{c.reason}</div>
                      )}
                    </li>
                  ))}
                  {gap.suggested_licenses.map((l, i) => (
                    <li key={`lic-${i}`}>
                      <span className="text-[10px] uppercase tracking-wider text-zinc-500 mr-2">
                        License
                      </span>
                      {l.name}
                      {l.reason && (
                        <div className="text-[11px] text-zinc-400 ml-3">{l.reason}</div>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <PrimaryButton busy={advanceBusy} onClick={() => void advance()}>
          Continue to Finalize
        </PrimaryButton>
        {gap && totalSuggestions > 0 && (
          <span className="text-[11px] text-amber-300">
            {totalSuggestions} suggestion{totalSuggestions === 1 ? '' : 's'} flagged — re-run earlier steps to fold them in, or finalize and address from the company compliance page later.
          </span>
        )}
      </div>
    </div>
  )
}
