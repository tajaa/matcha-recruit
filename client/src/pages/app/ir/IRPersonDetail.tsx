import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Loader2, User } from 'lucide-react'
import { Badge } from '../../../components/ui'
import { api } from '../../../api/client'
import {
  typeLabel, statusLabel, severityLabel,
  SEVERITY_BADGE, STATUS_BADGE, PERSON_ROLE_LABEL,
  type IRPersonHistory,
} from '../../../types/ir'

export default function IRPersonDetail() {
  const { personId } = useParams<{ personId: string }>()
  const navigate = useNavigate()
  const [data, setData] = useState<IRPersonHistory | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!personId) return
    let cancelled = false
    setLoading(true)
    setError(null)
    api.get<IRPersonHistory>(`/ir/incidents/people/${personId}/incidents`)
      .then((res) => { if (!cancelled) setData(res) })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load person') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [personId])

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh] text-zinc-500">
        <Loader2 className="w-4 h-4 animate-spin" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="max-w-3xl">
        <button onClick={() => navigate(-1)} className="flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-200 mb-4">
          <ArrowLeft className="w-4 h-4" /> Back
        </button>
        <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 text-sm text-red-400">
          {error || 'Person not found'}
        </div>
      </div>
    )
  }

  const { person, role_breakdown, incidents } = data

  return (
    <div className="max-w-6xl space-y-6">
      <button onClick={() => navigate(-1)} className="flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-200">
        <ArrowLeft className="w-4 h-4" /> Back
      </button>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 w-10 h-10 rounded-full bg-zinc-800 flex items-center justify-center text-zinc-400">
            <User className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold text-zinc-100">{person.display_name}</h1>
            <p className="mt-1 text-sm text-zinc-500">
              {person.incident_count} {person.incident_count === 1 ? 'incident' : 'incidents'}
              {person.email && <span className="ml-2 text-zinc-600">· {person.email}</span>}
            </p>
          </div>
        </div>

        {role_breakdown.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {role_breakdown.map((rb) => (
              <span key={rb.role} className="text-xs px-2.5 py-1 rounded-full bg-zinc-800 text-zinc-300">
                {PERSON_ROLE_LABEL[rb.role]}: <span className="text-zinc-100 font-medium">{rb.count}</span>
              </span>
            ))}
          </div>
        )}
      </div>

      <div>
        <h2 className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-3">Incidents</h2>
        {incidents.length === 0 ? (
          <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 text-sm text-zinc-500 text-center">
            No incidents linked to this person.
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {incidents.map((inc) => (
              <Link
                key={`${inc.id}-${inc.role}`}
                to={`/app/ir/${inc.id}`}
                className="flex items-center justify-between gap-3 px-4 py-3 rounded-xl border border-zinc-800 bg-zinc-900/40 hover:bg-zinc-900/80 hover:border-zinc-700 transition-colors"
              >
                <div className="min-w-0">
                  <div className="text-sm text-zinc-200 truncate">{inc.title}</div>
                  <div className="text-[11px] text-zinc-500 font-mono mt-0.5">
                    {inc.incident_number}
                    {inc.occurred_at && <span className="ml-2">{new Date(inc.occurred_at).toLocaleDateString()}</span>}
                    <span className="ml-2">· {PERSON_ROLE_LABEL[inc.role]}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-[11px] text-zinc-400">{typeLabel(inc.incident_type)}</span>
                  <Badge variant={SEVERITY_BADGE[inc.severity]}>{severityLabel(inc.severity)}</Badge>
                  <Badge variant={STATUS_BADGE[inc.status]}>{statusLabel(inc.status)}</Badge>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
