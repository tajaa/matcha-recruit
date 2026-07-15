import { useEffect, useState } from 'react'
import { Loader2, Sparkles } from 'lucide-react'
import { fetchPendingResearch, type PendingResearch } from '../../api/compliance'

/**
 * Tenant-facing "we're working on it" panel for the Compliance page.
 *
 * Surfaces what Matcha is still researching for this company — real catalog
 * gaps their onboarding build queued (coverage requests) plus industry-specialty
 * areas (e.g. dental) not yet in the library. When our team finishes and maps it
 * onto the shared catalog, the tab auto-populates and the admin gets an email —
 * so this panel is the "pending" half of that loop. Renders nothing when there's
 * nothing outstanding.
 */
export default function PendingResearchPanel() {
  const [data, setData] = useState<PendingResearch | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    fetchPendingResearch()
      .then((d) => { if (alive) setData(d) })
      .catch(() => { if (alive) setData(null) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [])

  if (loading || !data) return null

  const areas = data.vertical?.areas ?? 0
  const hasCoverage = data.coverage_requests.length > 0
  if (!hasCoverage && areas === 0) return null

  const cleanNote = (note: string | null): string | null => {
    if (!note) return null
    return note.replace(/^(needs research:|missing:)\s*/i, '').trim()
  }

  return (
    <div className="rounded-lg border border-amber-500/30 bg-amber-500/[0.06] px-4 py-3 mb-4">
      <div className="flex items-center gap-2 mb-1">
        <Sparkles className="w-4 h-4 text-amber-400" />
        <p className="text-sm font-medium text-amber-200">
          We're researching more requirements for you
        </p>
        <Loader2 className="w-3.5 h-3.5 text-amber-400/70 animate-spin" />
      </div>

      <ul className="mt-1.5 space-y-1.5 text-xs text-zinc-300">
        {data.vertical && areas > 0 && (
          <li>
            <span className="text-amber-300 font-medium">{data.vertical.label}-specific</span>
            {' '}requirements — {areas} area{areas === 1 ? '' : 's'} in progress.
          </li>
        )}
        {data.coverage_requests.map((r, i) => (
          <li key={`${r.city}-${r.state}-${i}`}>
            <span className="text-amber-300 font-medium">{r.city}, {r.state}</span>
            {cleanNote(r.note) ? <>: {cleanNote(r.note)}</> : null}
          </li>
        ))}
      </ul>

      <p className="mt-2 text-[11px] text-zinc-500">
        We're working on this for you. We'll email you when it's done — the new
        requirements appear here automatically once published.
      </p>
    </div>
  )
}
