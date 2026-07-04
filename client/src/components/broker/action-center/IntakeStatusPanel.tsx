import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ClipboardList, CheckCircle2, Clock, CircleDashed, Loader2 } from 'lucide-react'
import { Card } from '../../ui'
import TabHeader from './TabHeader'
import { fetchExternalClients } from '../../../api/broker'
import type { ExternalClientRow, ExternalIntakeState } from '../../../types/broker'

/**
 * Action Center — EPL intake status. Surfaces where each off-platform (Broker Pro)
 * client stands on the self-serve EPL questionnaire: submitted (+ the date the
 * broker reads to confirm the answers are current), a link still pending, or none
 * collected yet. Reuses the book-of-business roster (already carries the derived
 * intake state) — no extra endpoint. Renders nothing when the broker has no
 * external clients (or isn't Broker Pro, in which case the fetch 403s and we hide).
 */

const fmtDate = (iso: string | null) => {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

// Needs-action states first so the worklist reads top-down.
const ORDER: Record<ExternalIntakeState, number> = { not_sent: 0, pending: 1, submitted: 2 }

function StatusBadge({ row }: { row: ExternalClientRow }) {
  if (row.intake_status === 'submitted') {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-emerald-400 shrink-0">
        <CheckCircle2 className="h-3.5 w-3.5" /> Submitted {fmtDate(row.intake_submitted_at) || '—'}
      </span>
    )
  }
  if (row.intake_status === 'pending') {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-amber-400 shrink-0" title="Intake link sent — awaiting the client's response">
        <Clock className="h-3.5 w-3.5" /> Awaiting client
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs text-zinc-500 shrink-0" title="No intake link sent yet — collect the client's EPL answers">
      <CircleDashed className="h-3.5 w-3.5" /> No intake sent
    </span>
  )
}

export default function IntakeStatusPanel() {
  const [clients, setClients] = useState<ExternalClientRow[] | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    fetchExternalClients()
      .then((r) => { if (alive) setClients(r.clients) })
      .catch(() => { if (alive) setClients(null) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [])

  if (loading) {
    return (
      <Card className="p-5">
        <div className="flex items-center gap-2 text-sm text-zinc-500">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading intake status…
        </div>
      </Card>
    )
  }
  // No Broker-Pro external clients (or not entitled) → keep the Action Center clean.
  if (!clients || clients.length === 0) return null

  const sorted = [...clients].sort((a, b) => {
    const d = ORDER[a.intake_status] - ORDER[b.intake_status]
    return d !== 0 ? d : (a.name || '').localeCompare(b.name || '')
  })
  const needsAction = clients.filter((c) => c.intake_status !== 'submitted').length

  return (
    <Card className="p-5 space-y-4">
      <TabHeader
        icon={ClipboardList}
        title="EPL intake status"
        hint="Confirm each client's EPL answers are current — chase pending links, collect where none was sent."
        badge={needsAction > 0 ? (
          <span className="text-[11px] font-medium text-amber-400 bg-amber-400/10 border border-amber-400/20 rounded-full px-2 py-0.5">{needsAction} to collect</span>
        ) : (
          <span className="text-[11px] font-medium text-emerald-400 bg-emerald-400/10 border border-emerald-400/20 rounded-full px-2 py-0.5">All current</span>
        )}
      />
      <div className="divide-y divide-zinc-800/70">
        {sorted.map((c) => (
          <Link
            key={c.id}
            to={`/broker/external/${c.id}`}
            className="flex items-center justify-between gap-3 py-2.5 group"
          >
            <span className="text-sm text-zinc-300 group-hover:text-zinc-100 transition-colors truncate">{c.name}</span>
            <StatusBadge row={c} />
          </Link>
        ))}
      </div>
    </Card>
  )
}
