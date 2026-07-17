import { useCallback, useEffect, useState } from 'react'
import { Loader2, ShieldCheck, EyeOff, AlertTriangle, Layers, Check, Search, RefreshCw, ExternalLink } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, ensureFreshToken } from '../../api/client'
import { adminOnboarding, getLocationCheckUrl } from '../../api/adminOnboarding'
import type { FitGatedRow, FitMapResponse, FitMissing, FitReason } from '../../api/adminOnboarding'
import { useResearchGaps } from '../../hooks/useResearchGaps'

// Each reason is a different fix. Collapsing them into one "missing" number is
// what makes a gap list unusable: a preempted rule needs nothing done, a staged
// row needs one click, and only the last two are research. Ordered benign-first
// so the eye lands on real work last — where the actions are.
const REASON_META: Record<FitReason, { label: string; fix: string; tone: string; gap: boolean }> = {
  no_jurisdiction: {
    label: 'Location not on the map',
    fix: "This location has no jurisdiction resolved, so it has no chain and nothing can project to it. Fix the address/onboarding first — researching law for it is meaningless until it resolves to a place.",
    tone: 'text-rose-400 border-rose-800/40 bg-rose-900/20',
    gap: true,
  },
  covered_by_stricter: {
    label: 'Covered by a stricter rule',
    fix: 'Nothing to do — a local rule preempts this, or a facility trigger correctly excluded it.',
    tone: 'text-zinc-500 border-white/[0.08] bg-white/[0.02]',
    gap: false,
  },
  stale_projection: {
    label: 'Not synced yet',
    fix: 'Researched since this location last synced — run a compliance check to release it.',
    tone: 'text-sky-400 border-sky-800/40 bg-sky-900/20',
    gap: true,
  },
  staged: {
    label: 'Staged, awaiting approval',
    fix: 'Already researched and sitting in the review queue — approve it.',
    tone: 'text-violet-400 border-violet-800/40 bg-violet-900/20',
    gap: true,
  },
  researched_elsewhere: {
    label: 'Researched elsewhere',
    fix: 'Exists for other jurisdictions but not this chain — research it here, or re-parent it if it is federal law filed under a state.',
    tone: 'text-amber-400 border-amber-800/40 bg-amber-900/20',
    gap: true,
  },
  never_researched: {
    label: 'Never researched',
    fix: 'Nowhere in the catalog. This business is blind to it.',
    tone: 'text-rose-400 border-rose-800/40 bg-rose-900/20',
    gap: true,
  },
}

const ORDER: FitReason[] = [
  'no_jurisdiction', 'never_researched', 'researched_elsewhere', 'staged',
  'stale_projection', 'covered_by_stricter',
]

function ActionButton({ onClick, busy, icon: Icon, label, disabled }: {
  onClick: () => void; busy: boolean; icon: typeof Check; label: string; disabled?: boolean
}) {
  return (
    <button type="button" onClick={onClick} disabled={busy || disabled}
      className="inline-flex shrink-0 items-center gap-1 rounded border border-white/[0.14] bg-white/[0.06] px-1.5 py-0.5 text-[10px] font-medium text-zinc-100 hover:bg-white/[0.12] disabled:opacity-40">
      {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Icon className="h-3 w-3" />}
      {label}
    </button>
  )
}

function Tile({ icon: Icon, label, value, sub, tone }: {
  icon: typeof ShieldCheck; label: string; value: number; sub: string; tone: string
}) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
      <div className={`flex items-center gap-1.5 text-[11px] ${tone}`}>
        <Icon className="h-3.5 w-3.5" /> {label}
      </div>
      <div className="mt-1 font-mono text-lg text-zinc-100">{value}</div>
      <div className="mt-0.5 text-[10px] leading-tight text-zinc-600">{sub}</div>
    </div>
  )
}

/** What this business HAS vs what it NEEDS, measured against the curated
 *  statutory checklist rather than a Gemini scope run. Sits alongside the AI
 *  dossier on purpose — the two answer different questions and will disagree.
 *
 *  `onCodifyGated`: when the host owns a codify chain (the Fill Gaps tab does),
 *  the Gated tile hands it this company's withheld rows and the work happens in
 *  place. Without it (GapDashboard) the tile links out to Studio instead —
 *  the panel never pretends to an action its host can't finish.
 *  `refreshKey`: bump to re-measure after the host codifies something. */
export default function StatutoryFitPanel({ companyId, onCodifyGated, refreshKey }: {
  companyId: string
  onCodifyGated?: (items: FitGatedRow[]) => void
  refreshKey?: number
}) {
  const [fit, setFit] = useState<FitMapResponse | null>(null)
  const [loading, setLoading] = useState(true)
  // Keyed by ACTION, not by reason. Reconcile and the compliance check are two
  // different jobs that happened to share the 'stale_projection' reason key —
  // so running one greyed out the other and neither said which was going.
  const [busy, setBusy] = useState<'approve' | 'check' | 'reconcile' | null>(null)
  const [note, setNote] = useState<string | null>(null)
  // Deselected keys, per reason. Absent = all selected — "act on everything you
  // showed me" is the common case, and nothing fires until a button is clicked
  // anyway.
  const [off, setOff] = useState<Record<string, Set<string>>>({})
  const research = useResearchGaps()

  const keyOf = (m: FitMissing) => `${m.category}:${m.regulation_key}`
  const isOn = (reason: string, m: FitMissing) => !off[reason]?.has(keyOf(m))
  const toggle = (reason: string, m: FitMissing) => setOff((prev) => {
    const next = new Set(prev[reason] ?? [])
    const k = keyOf(m)
    if (next.has(k)) next.delete(k); else next.add(k)
    return { ...prev, [reason]: next }
  })
  const selectedIn = (reason: string, items: FitMissing[]) => items.filter((m) => isOn(reason, m))

  const load = useCallback(() => {
    return adminOnboarding.getFitMap(companyId)
      .then(setFit)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [companyId])

  useEffect(() => { void load() }, [load])
  // A research run rewrites the catalog + re-syncs the location, so every bucket
  // can move. Re-measure rather than patching counts client-side.
  useEffect(() => { if (research.done) void load() }, [research.done, load])
  // The host codified something — same reasoning, re-measure.
  useEffect(() => { if (refreshKey) void load() }, [refreshKey, load])

  /** Approve the staged rows behind these keys, then re-measure.
   *
   *  Approve is only the FIRST of three steps, and the note has to say so or it
   *  reads as done. The endpoint's publish loop runs off request_ids /
   *  company_ids, which the panel doesn't send — so the row goes active but is
   *  not projected to this tenant. It self-heals rather than stranding:
   *  approve_staged bumps `updated_at`, so on re-measure the key reappears
   *  under "Not synced yet" (the GREATEST(created, updated) test exists for
   *  exactly this), where the panel's own compliance-check button projects it.
   *  Then it's gated, and codify releases it. approve → check → codify. */
  const approveStaged = useCallback(async (items: FitMissing[]) => {
    const ids = items.flatMap((m) => m.requirement_ids ?? [])
    if (!ids.length) return
    setBusy('approve'); setNote(null)
    try {
      await api.post('/admin/research-review/approve', { ids })
      setNote(`Approved ${ids.length} — now live, but not yet on this tenant's tab. They move to "Not synced yet": run the compliance check to project them, then codify to release.`)
      await load()
    } catch {
      setNote('Approve failed.')
    } finally { setBusy(null) }
  }, [load])

  /** Re-project the locations that never saw these rows.
   *
   *  This endpoint answers with SSE, not JSON — `api.post` would choke parsing
   *  `data: {...}`. And the stream is the WORK: the server projects as it
   *  yields, so the body has to be drained to completion or the check is
   *  abandoned half-done. Same fetch+reader shape useResearchGaps uses. */
  const runCheck = useCallback(async (items: FitMissing[]) => {
    const locs = [...new Set(items.flatMap((m) => m.location_ids ?? []))]
    if (!locs.length) return
    setBusy('check'); setNote(null)
    try {
      const token = await ensureFreshToken()
      for (const id of locs) {
        const res = await fetch(
          getLocationCheckUrl(id, companyId),
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
            body: '{}',
          },
        )
        if (!res.ok) throw new Error(String(res.status))
        const reader = res.body?.getReader()
        while (reader) { const { done } = await reader.read(); if (done) break }
      }
      setNote(`Re-checked ${locs.length} location${locs.length === 1 ? '' : 's'}.`)
      await load()
    } catch {
      setNote('Compliance check failed.')
    } finally { setBusy(null) }
  }, [companyId, load])

  /** Bind every gated row whose key a confirmed classification already covers.
   *  No typing, no per-row modal — this is what the registry is FOR. Global by
   *  design (the endpoint takes no scope): a statute confirmed for one tenant
   *  codifies it for every tenant holding the same key, which is the leverage
   *  the catalog exists to give. */
  const reconcile = useCallback(async () => {
    setBusy('reconcile'); setNote(null)
    try {
      await api.post('/admin/scope-registry/reconcile', {})
      setNote('Reconciled — rows bound to statutes already in the registry.')
      await load()
    } catch {
      setNote('Reconcile failed.')
    } finally { setBusy(null) }
  }, [load])

  /** Research these categories, for every location that resolved to a place.
   *  Reuses the same selective-fill stream the dossier's gap list uses, so this
   *  never triggers an all-jurisdictions sweep. */
  const researchGaps = useCallback((items: FitMissing[]) => {
    if (!fit?.research_targets.length) return
    const cats = [...new Set(items.map((m) => m.category))]
    setNote(null)
    void research.run(companyId, fit.research_targets.flatMap((t) =>
      cats.map((category_slug) => ({ category_slug, state: t.state, city: t.city })),
    ))
  }, [companyId, fit, research])

  if (loading) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-vsc-border bg-vsc-panel/40 px-4 py-6 text-xs text-zinc-500">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> Measuring statutory fit…
      </div>
    )
  }
  if (!fit) return null

  const byReason = ORDER
    .map((reason) => ({ reason, items: fit.missing.filter((m) => m.reason === reason) }))
    .filter((g) => g.items.length > 0)

  return (
    <div className="rounded-xl border border-vsc-border bg-vsc-panel/40 p-4">
      <div className="mb-1 flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
          <ShieldCheck className="h-4 w-4 text-emerald-400" /> Statutory fit — core checklist
        </h2>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] text-zinc-600">
            {fit.keyset === 'labor_floor_only' ? 'labor floor only' : fit.keyset}
          </span>
          {/* Where the whole chain can be finished. Only shown when this host
              can't finish it itself. */}
          {!onCodifyGated && (
            <Link to={`/admin/studio?view=pipeline&company=${companyId}`}
                  className="inline-flex items-center gap-0.5 text-[10px] text-emerald-400 hover:text-emerald-300">
              Work this in Studio <ExternalLink className="h-2.5 w-2.5" />
            </Link>
          )}
        </div>
      </div>
      <p className="mb-3 text-[11px] leading-relaxed text-zinc-600">
        Deterministic: the curated must-have checklist for a{' '}
        <span className="text-zinc-400">{fit.industry ?? 'business of unknown industry'}</span>, not an AI
        scope run — so a gap here means the law expects it, not that a model thought of it.
        Scoped to this business: nothing outside its industry and jurisdictions is counted.
      </p>
      {fit.keyset_note && (
        <p className="mb-3 rounded-lg border border-amber-800/40 bg-amber-900/20 px-2.5 py-1.5 text-[11px] text-amber-400">
          {fit.keyset_note}
        </p>
      )}
      {note && (
        <p className="mb-3 rounded-lg border border-white/[0.1] bg-white/[0.03] px-2.5 py-1.5 text-[11px] text-zinc-300">
          {note}
        </p>
      )}
      {(research.running || research.error) && (
        <p className="mb-3 flex items-center gap-1.5 rounded-lg border border-white/[0.1] bg-white/[0.03] px-2.5 py-1.5 text-[11px] text-zinc-400">
          {research.running && <Loader2 className="h-3 w-3 animate-spin" />}
          {research.error
            ? <span className="text-red-300">{research.error}</span>
            : (research.events[research.events.length - 1]?.message ?? 'Researching…')}
        </p>
      )}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Tile icon={ShieldCheck} label="Visible" value={fit.counts.visible} tone="text-emerald-400"
              sub="codified — on their tab today" />
        <div className="relative">
          <Tile icon={EyeOff} label="Gated" value={fit.counts.gated} tone="text-amber-400"
                sub={fit.gated.length > fit.counts.codifiable_now
                  ? `${fit.counts.codifiable_now} reconcilable · ${fit.gated.length - fit.counts.codifiable_now} have no statute in the registry yet`
                  : 'researched but withheld until codified'} />
          {/* "Codify 302" was a lie: only the rows whose key already carries a
              confirmed classification can be reconciled. The rest need a statute
              INGESTED into the registry before anything can bind them — or a
              citation typed by hand, one at a time. Three different jobs, so
              three different controls. */}
          {fit.counts.gated > 0 && (
            <div className="absolute right-2 top-2 flex items-center gap-1.5">
              {fit.counts.codifiable_now > 0 && (
                <button type="button" onClick={() => void reconcile()} disabled={busy === 'reconcile'}
                        title="One reconcile binds these to statutes already confirmed in the registry — no typing"
                        className="inline-flex items-center gap-0.5 rounded border border-cyan-800/50 bg-cyan-900/30 px-1.5 py-0.5 text-[10px] font-medium text-cyan-300 hover:bg-cyan-900/50 disabled:opacity-40">
                  Reconcile {fit.counts.codifiable_now}
                </button>
              )}
              {onCodifyGated ? (
                <button type="button" onClick={() => onCodifyGated(fit.gated)}
                        title="Walks the rows one at a time — you supply each statute citation"
                        className="inline-flex items-center gap-0.5 rounded border border-amber-800/50 bg-amber-900/30 px-1.5 py-0.5 text-[10px] font-medium text-amber-300 hover:bg-amber-900/50">
                  By hand
                </button>
              ) : (
                <Link to={`/admin/studio?view=pipeline&company=${companyId}`}
                      className="inline-flex items-center gap-0.5 text-[10px] text-amber-400 hover:text-amber-300">
                  Codify <ExternalLink className="h-2.5 w-2.5" />
                </Link>
              )}
            </div>
          )}
        </div>
        <Tile icon={AlertTriangle} label="Real gaps" value={fit.counts.gaps} tone="text-rose-400"
              sub={`of ${fit.counts.expected} expected · ${fit.counts.covered_by_stricter} preempted, not a gap`} />
        <Tile icon={Layers} label="Beyond core" value={fit.counts.beyond_core} tone="text-sky-400"
              sub="extra coverage — breadth, not excess" />
      </div>

      {/* Per-location, ALL of them — including sites with nothing projected,
          which are the ones worth seeing. Onc shows 24 here; before the roster
          seed it showed the 9 that happened to have rows. */}
      {fit.locations.length > 1 && (
        <div className="mt-3 rounded-lg border border-white/[0.06] bg-black/20 p-2">
          <div className="mb-1.5 text-[10px] uppercase tracking-wide text-zinc-600">
            {fit.locations.length} locations
          </div>
          <div className="space-y-0.5">
            {fit.locations.map((l) => (
              <div key={l.location_id}
                   className="flex items-center justify-between gap-3 rounded px-1.5 py-1 text-[11px] hover:bg-white/[0.03]">
                <span className="min-w-0 flex-1 truncate text-zinc-400">
                  {l.city || '—'}{l.state ? `, ${l.state}` : ''}
                </span>
                {l.has_jurisdiction ? (
                  <span className="flex shrink-0 items-center gap-2 font-mono text-[10px]">
                    <span className="text-emerald-400" title="visible — codified, on their tab">{l.counts.visible}</span>
                    <span className="text-amber-400" title="gated — researched, withheld until codified">{l.counts.gated}</span>
                    <span className={l.counts.gaps > 0 ? 'text-rose-400' : 'text-zinc-600'}
                          title="real gaps (preempted rules excluded)">{l.counts.gaps} gap{l.counts.gaps === 1 ? '' : 's'}</span>
                  </span>
                ) : (
                  <span className="shrink-0 rounded-full border border-rose-800/40 bg-rose-900/20 px-1.5 py-0.5 font-mono text-[10px] text-rose-400"
                        title="No jurisdiction resolved — nothing can project to this location until its address is fixed">
                    no jurisdiction
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* The ceiling, named. Codification binds a row to a statute in the
          registry; when the registry has nothing for a key, no amount of
          clicking here helps — the fix is upstream, in Authority. Saying so
          beats letting an admin grind a modal that can't finish. */}
      {fit.gated.length - fit.counts.codifiable_now > 0 && (
        <p className="mt-2 text-[11px] text-zinc-500">
          {fit.gated.length - fit.counts.codifiable_now} withheld row
          {fit.gated.length - fit.counts.codifiable_now === 1 ? ' has' : 's have'} no statute in the
          registry to bind to — codification needs the authority ingested first.{' '}
          <Link to="/admin/studio?view=authority" className="text-cyan-400 hover:text-cyan-300">
            Ingest authority →
          </Link>
        </p>
      )}

      {byReason.length === 0 ? (
        <p className="mt-3 text-[11px] text-emerald-400">
          Every core obligation for this business is accounted for.
        </p>
      ) : (
        <div className="mt-3 space-y-2.5">
          {byReason.map(({ reason, items }) => {
            const meta = REASON_META[reason]
            return (
              <div key={reason} className={`rounded-lg border px-3 py-2 ${meta.tone}`}>
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-medium">{meta.label}</span>
                  <span className="rounded-full bg-white/[0.06] px-1.5 py-0.5 font-mono text-[10px]">
                    {items.length}
                  </span>
                  <span className="flex-1" />
                  {/* The fix, as a button. A bucket that can't be actioned from
                      here says nothing rather than offering a dead control. */}
                  {reason === 'staged' && (
                    <ActionButton onClick={() => void approveStaged(selectedIn(reason, items))}
                                  busy={busy === 'approve'} icon={Check}
                                  disabled={!selectedIn(reason, items).length}
                                  label={`Approve ${selectedIn(reason, items).reduce((n, m) => n + (m.requirement_ids?.length ?? 0), 0)}`} />
                  )}
                  {reason === 'stale_projection' && (
                    <ActionButton onClick={() => void runCheck(items)}
                                  busy={busy === 'check'} icon={RefreshCw}
                                  label="Run compliance check" />
                  )}
                  {(reason === 'never_researched' || reason === 'researched_elsewhere') && (
                    <ActionButton onClick={() => researchGaps(selectedIn(reason, items))}
                                  busy={research.running} icon={Search}
                                  label={`Research ${selectedIn(reason, items).length}`}
                                  disabled={!fit.research_targets.length || !selectedIn(reason, items).length} />
                  )}
                </div>
                <p className="mt-0.5 text-[10px] leading-tight text-zinc-500">{meta.fix}</p>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {items.map((m: FitMissing) => {
                    // Only buckets with an action are selectable — toggling a
                    // preempted rule or an unmapped location changes nothing,
                    // so a checkbox there would be a control that lies.
                    const selectable = meta.gap && reason !== 'no_jurisdiction'
                    const on = isOn(reason, m)
                    return selectable ? (
                      <button key={keyOf(m)} type="button" onClick={() => toggle(reason, m)}
                              title={`${m.category} — click to ${on ? 'exclude from' : 'include in'} the action`}
                              className={`rounded border px-1.5 py-0.5 font-mono text-[10px] transition-colors ${
                                on ? 'border-white/[0.14] bg-black/30 text-zinc-300'
                                   : 'border-white/[0.05] bg-transparent text-zinc-600 line-through'}`}>
                        {m.regulation_key}
                      </button>
                    ) : (
                      <span key={keyOf(m)}
                            className="rounded border border-white/[0.08] bg-black/20 px-1.5 py-0.5 font-mono text-[10px] text-zinc-400"
                            title={m.category}>
                        {m.regulation_key}
                      </span>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
