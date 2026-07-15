import { useCallback, useEffect, useState } from 'react'
import { Check, Layers } from 'lucide-react'
import { api } from '../../../api/client'
import { LABEL } from '../../../components/ui/typography'
import { HelpHint } from '../../../components/ui/HelpHint'
import AuthorityCockpit from '../../../components/admin/scope/AuthorityCockpit'

// Authority drift (re-ingest diff) change types — the "a law changed" queue.
const DRIFT_BADGE: Record<string, string> = {
  new: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  amended: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  removed: 'bg-red-500/15 text-red-300 border-red-500/30',
}

type DriftRow = {
  id: string
  index_slug: string
  index_name: string
  change_type: 'new' | 'amended' | 'removed'
  citation: string
  heading: string | null
  old_amendment_date: string | null
  new_amendment_date: string | null
  detected_at: string
  status: 'open' | 'acknowledged'
  affected_requirements: number
}

// The SUPPLY funnel authoring surface: ingest → classify → confirm → reconcile
// (AuthorityCockpit) + the "a law changed" drift review queue.
export default function AuthorityTab({ onMutate }: { onMutate?: () => void }) {
  const [drift, setDrift] = useState<{ drift: DriftRow[]; open_count: number } | null>(null)
  const [driftError, setDriftError] = useState<string | null>(null)
  const [driftShowAll, setDriftShowAll] = useState(false)
  const [driftNonce, setDriftNonce] = useState(0)
  const [ackBusy, setAckBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const qs = driftShowAll ? '' : '?status=open'
        const res = await api.get<{ drift: DriftRow[]; open_count: number }>(
          `/admin/scope-registry/drift${qs}`,
        )
        if (!cancelled) { setDrift(res); setDriftError(null) }
      } catch (e) {
        if (!cancelled) setDriftError(e instanceof Error ? e.message : 'Failed to load drift')
      }
    })()
    return () => { cancelled = true }
  }, [driftShowAll, driftNonce])

  const acknowledgeDrift = useCallback(async (ids: string[]) => {
    if (!ids.length) return
    setAckBusy(true)
    try {
      await api.post('/admin/scope-registry/drift/acknowledge', { ids })
      setDriftNonce((n) => n + 1)
      onMutate?.()
    } catch (e) {
      setDriftError(e instanceof Error ? e.message : 'Failed to acknowledge')
    } finally {
      setAckBusy(false)
    }
  }, [onMutate])

  return (
    <div className="text-zinc-200">
      <div className="mb-4">
        <div className={LABEL}>Supply funnel</div>
        <h2 className="mt-0.5 flex items-center gap-2 text-lg font-semibold tracking-tight text-zinc-100">
          <Layers className="h-4 w-4 text-emerald-400" /> Authority
        </h2>
        <p className="mt-1 max-w-[70ch] text-sm leading-relaxed text-zinc-500">
          Ingest a statute source → classify each section → confirm → reconcile.
          This is the only surface that WRITES the authority registry; every
          other tab reads it.
        </p>
      </div>

      {/* Authority drift — new/amended/removed citations detected on re-ingest */}
      <div className="rounded-xl border border-white/[0.06] bg-zinc-950 p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className={LABEL}>Authority drift</div>
            <HelpHint text="What changed at the source since the last ingest of each authority index — a new section appeared, a heading was amended, or a citation vanished upstream. Review each row, act on it (research / reclassify), then acknowledge it to clear the queue." />
            {drift && drift.open_count > 0 && (
              <span className={`rounded border px-1.5 py-0.5 text-[10px] ${DRIFT_BADGE.amended}`}>
                {drift.open_count} open
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setDriftShowAll((v) => !v)}
              className="rounded border border-white/[0.08] px-2 py-1 text-[11px] text-zinc-400 hover:border-white/20">
              {driftShowAll ? 'Show open only' : 'Show all (incl. acknowledged)'}
            </button>
            {drift && drift.drift.some((d) => d.status === 'open') && (
              <button
                disabled={ackBusy}
                onClick={() => acknowledgeDrift(drift.drift.filter((d) => d.status === 'open').map((d) => d.id))}
                className="rounded border border-white/[0.08] px-2 py-1 text-[11px] text-emerald-300 hover:border-white/20 disabled:opacity-50">
                {ackBusy ? 'Acknowledging…' : 'Acknowledge all shown'}
              </button>
            )}
          </div>
        </div>

        {driftError ? (
          <div className="text-xs text-red-400">{driftError}</div>
        ) : !drift ? (
          <div className="text-xs text-zinc-500">Loading…</div>
        ) : drift.drift.length === 0 ? (
          <div className="text-xs text-zinc-500">
            {driftShowAll
              ? 'No drift recorded yet — run an ingest twice to establish a baseline and diff against it.'
              : 'No open drift. The authority indexes match their last-reviewed state.'}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-zinc-500">
                <tr>
                  <th className="py-2">Change</th>
                  <th className="py-2">Citation</th>
                  <th className="py-2">Index</th>
                  <th className="py-2">Affected</th>
                  <th className="py-2">Detected</th>
                  <th className="py-2" />
                </tr>
              </thead>
              <tbody>
                {drift.drift.map((d) => (
                  <tr key={d.id} className={d.status === 'acknowledged' ? 'opacity-50' : ''}>
                    <td className="py-1.5">
                      <span className={`rounded border px-1.5 py-0.5 text-[10px] ${DRIFT_BADGE[d.change_type]}`}>
                        {d.change_type}
                      </span>
                    </td>
                    <td className="py-1.5 text-zinc-200">
                      <span className="font-mono">{d.citation}</span>
                      {d.heading && <span className="text-zinc-500"> — {d.heading}</span>}
                    </td>
                    <td className="py-1.5 text-xs text-zinc-400">{d.index_slug}</td>
                    <td className="py-1.5 text-xs">
                      {d.affected_requirements > 0 ? (
                        <span className="rounded bg-purple-500/15 px-1.5 py-0.5 text-[10px] text-purple-300"
                              title="Codified policy rows flagged needs_review by this change">
                          {d.affected_requirements} {d.affected_requirements === 1 ? 'policy' : 'policies'}
                        </span>
                      ) : (
                        <span className="text-zinc-600">—</span>
                      )}
                    </td>
                    <td className="py-1.5 text-xs text-zinc-500">{d.detected_at.slice(0, 10)}</td>
                    <td className="py-1.5 text-right">
                      {d.status === 'open' ? (
                        <button
                          disabled={ackBusy}
                          onClick={() => acknowledgeDrift([d.id])}
                          className="rounded border border-white/[0.08] px-2 py-0.5 text-[11px] text-zinc-300 hover:border-white/20 disabled:opacity-50"
                          title="Mark reviewed — clears it from the open queue (kept for audit)">
                          <Check className="inline h-3 w-3" /> Ack
                        </button>
                      ) : (
                        <span className="text-[10px] uppercase text-zinc-600">acknowledged</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* The authoring pipeline: ingest → classify → confirm/key → reconcile.
          Every surface in Coverage/Pipeline READS the registry; this is the
          only one that fills it. */}
      <div className="mt-5">
        <AuthorityCockpit onMutate={() => { setDriftNonce((n) => n + 1); onMutate?.() }} />
      </div>
    </div>
  )
}
