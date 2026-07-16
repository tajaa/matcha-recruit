import { useEffect, useState } from 'react'
import { Loader2, ShieldCheck, EyeOff, AlertTriangle, Layers } from 'lucide-react'
import { adminOnboarding } from '../../api/adminOnboarding'
import type { FitMapResponse, FitMissing, FitReason } from '../../api/adminOnboarding'

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
 *  dossier on purpose — the two answer different questions and will disagree. */
export default function StatutoryFitPanel({ companyId }: { companyId: string }) {
  const [fit, setFit] = useState<FitMapResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let live = true
    setLoading(true)
    adminOnboarding.getFitMap(companyId)
      .then((d) => { if (live) setFit(d) })
      .catch(() => {})
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [companyId])

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
        <span className="font-mono text-[10px] text-zinc-600">
          {fit.keyset === 'labor_floor_only' ? 'labor floor only' : fit.keyset}
        </span>
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

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Tile icon={ShieldCheck} label="Visible" value={fit.counts.visible} tone="text-emerald-400"
              sub="codified — on their tab today" />
        <Tile icon={EyeOff} label="Gated" value={fit.counts.gated} tone="text-amber-400"
              sub="researched but withheld until codified" />
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
                </div>
                <p className="mt-0.5 text-[10px] leading-tight text-zinc-500">{meta.fix}</p>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {items.map((m: FitMissing) => (
                    <span key={`${m.category}:${m.regulation_key}`}
                          className="rounded border border-white/[0.08] bg-black/20 px-1.5 py-0.5 font-mono text-[10px] text-zinc-400"
                          title={m.category}>
                      {m.regulation_key}
                    </span>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
