import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2, Sparkles } from 'lucide-react'
import { listPilotSessions, type PilotSession } from '../../../api/brokerPilot'
import { useMe } from '../../../hooks/useMe'
import { fmtWhen } from './shared'

/** Light per-client tab for BrokerClientDetail / external detail: this client's
 *  pilot sessions + a jump into the full Broker Pilot workbench. Pro-gated —
 *  non-Pro brokers see the upsell. */
export function PilotTab({ subjectKind, subjectId }: {
  subjectKind: 'company' | 'external'
  subjectId: string
}) {
  const { me } = useMe()
  const isPro = me?.profile?.plan === 'pro'
  const [sessions, setSessions] = useState<PilotSession[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!isPro) { setLoading(false); return }
    let cancelled = false
    listPilotSessions({ subject_kind: subjectKind, subject_id: subjectId })
      .then((rows) => { if (!cancelled) setSessions(rows) })
      .catch(() => { if (!cancelled) setSessions([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [isPro, subjectKind, subjectId])

  const deepLink = subjectKind === 'company'
    ? `/broker/pilot?client=${subjectId}`
    : `/broker/pilot?external=${subjectId}`

  if (!isPro) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-6 text-center">
        <Sparkles className="h-6 w-6 text-emerald-500 mx-auto mb-2" />
        <p className="text-sm text-zinc-300 font-medium">Broker Pilot is a Broker Pro feature</p>
        <p className="text-xs text-zinc-500 mt-1 max-w-md mx-auto">
          Upload this client's loss runs, dec pages, and quotes, and analyze them against the
          platform data on file — with every answer citing its records.
        </p>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32">
        <Loader2 className="h-5 w-5 text-zinc-500 animate-spin" />
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-zinc-400">
          {sessions.length
            ? `${sessions.length} analysis session${sessions.length === 1 ? '' : 's'} for this client.`
            : 'No analysis sessions for this client yet.'}
        </p>
        <Link
          to={deepLink}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md bg-emerald-700 text-white hover:bg-emerald-600 transition-colors"
        >
          <Sparkles className="h-3.5 w-3.5" />
          Open in Broker Pilot
        </Link>
      </div>
      {sessions.length > 0 && (
        <ul className="space-y-1.5">
          {sessions.map((s) => (
            <li key={s.id} className="rounded-md border border-zinc-800 px-3 py-2 flex items-center justify-between">
              <div className="min-w-0">
                <p className="text-sm text-zinc-200 truncate">{s.title}</p>
                <p className="text-[11px] text-zinc-500 mt-0.5">
                  {s.document_count ?? 0} docs · {s.message_count ?? 0} messages · updated {fmtWhen(s.updated_at)}
                </p>
              </div>
              {s.status === 'closed' && <span className="text-[11px] text-amber-500 flex-shrink-0">Closed</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
