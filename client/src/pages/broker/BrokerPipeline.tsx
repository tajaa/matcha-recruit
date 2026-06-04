import { useEffect, useState } from 'react'
import { Loader2, AlertCircle, ChevronLeft, ChevronRight, Send, Workflow, MapPin } from 'lucide-react'
import { Badge } from '../../components/ui'
import { api } from '../../api/client'

type OnboardingStage = 'submitted' | 'under_review' | 'configuring' | 'live'

type ClientSetup = {
  id: string
  company_name: string
  contact_name: string | null
  contact_email: string | null
  status: string
  created_at: string
  locations?: { city: string; state: string; type: string }[]
  onboarding_stage?: OnboardingStage
}

// Ordered onboarding stages. The DB column defaults to 'submitted' (never
// NULL), so every setup lands in one of these four columns; `status` (the
// invite lifecycle) is shown per-card and is orthogonal to the stage.
const STAGES: OnboardingStage[] = ['submitted', 'under_review', 'configuring', 'live']
const STAGE_LABEL: Record<OnboardingStage, string> = {
  submitted: 'Submitted',
  under_review: 'Under Review',
  configuring: 'Configuring',
  live: 'Live',
}

const COLUMNS: Array<{ key: OnboardingStage; label: string }> = STAGES.map((s) => ({ key: s, label: STAGE_LABEL[s] }))

function statusBadge(status: string) {
  if (status === 'active' || status === 'registered') return <Badge variant="success">{status}</Badge>
  if (status === 'invited' || status === 'pending') return <Badge variant="warning">{status}</Badge>
  if (status === 'expired') return <Badge variant="danger">Expired</Badge>
  return <Badge variant="warning">{status}</Badge>
}

function locationSummary(locations?: { city: string; state: string; type: string }[]) {
  if (!locations || locations.length === 0) return null
  if (locations.length === 1) {
    const l = locations[0]
    return `${l.city}${l.state ? ', ' + l.state : ''}`
  }
  return `${locations.length} locations`
}

export default function BrokerPipeline() {
  const [setups, setSetups] = useState<ClientSetup[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [needsTerms, setNeedsTerms] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)

  function fetchSetups() {
    setLoading(true)
    setNeedsTerms(false)
    api.get<{ setups: ClientSetup[] }>('/brokers/client-setups')
      .then((res) => setSetups(res.setups))
      .catch((err) => {
        const msg = err instanceof Error ? err.message : ''
        if (msg.toLowerCase().includes('terms')) setNeedsTerms(true)
        else setError('Unable to load pipeline')
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchSetups() }, [])

  async function moveStage(s: ClientSetup, dir: -1 | 1) {
    const curIdx = s.onboarding_stage ? STAGES.indexOf(s.onboarding_stage) : -1
    const nextIdx = curIdx + dir
    if (nextIdx < 0 || nextIdx >= STAGES.length) return
    const next = STAGES[nextIdx]
    setBusyId(s.id)
    // Optimistic.
    setSetups((prev) => prev.map((x) => (x.id === s.id ? { ...x, onboarding_stage: next } : x)))
    try {
      await api.post(`/brokers/client-setups/${s.id}/stage`, { onboarding_stage: next })
    } catch {
      setSetups((prev) => prev.map((x) => (x.id === s.id ? { ...x, onboarding_stage: s.onboarding_stage } : x)))
    } finally {
      setBusyId(null)
    }
  }

  async function sendInvite(s: ClientSetup) {
    setBusyId(s.id)
    try {
      await api.post(`/brokers/client-setups/${s.id}/send-invite`, { expires_days: 14 })
      fetchSetups()
    } catch {
      setBusyId(null)
    }
  }

  if (needsTerms) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-zinc-500">
        <AlertCircle className="h-8 w-8 mb-2" />
        <p className="text-sm">Accept the broker terms on the Onboarding page to manage your pipeline.</p>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 text-zinc-500 animate-spin" />
      </div>
    )
  }

  if (error && setups.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-zinc-500">
        <AlertCircle className="h-8 w-8 mb-2" />
        <p className="text-sm">{error}</p>
      </div>
    )
  }

  const byColumn = (key: OnboardingStage) =>
    setups.filter((s) => (s.onboarding_stage ?? 'submitted') === key)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
          <Workflow className="w-5 h-5 text-zinc-500" />
          Pipeline
        </h1>
        <p className="text-sm text-zinc-500 mt-1">Onboarding stages across your referred clients.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3">
        {COLUMNS.map((col) => {
          const items = byColumn(col.key)
          return (
            <div key={col.key} className="bg-zinc-900/40 border border-white/5 rounded-xl p-3">
              <div className="flex items-center justify-between mb-3 px-1">
                <span className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider">{col.label}</span>
                <span className="text-[11px] text-zinc-600 font-mono">{items.length}</span>
              </div>
              <div className="space-y-2">
                {items.length === 0 && (
                  <p className="text-[11px] text-zinc-700 px-1 py-4 text-center">—</p>
                )}
                {items.map((s) => {
                  const stageIdx = STAGES.indexOf(s.onboarding_stage ?? 'submitted')
                  const canInvite = (s.status === 'draft' || s.status === 'expired') && !!s.contact_email
                  const locText = locationSummary(s.locations)
                  return (
                    <div key={s.id} className="bg-zinc-900 border border-white/10 rounded-lg p-3">
                      <p className="text-[13px] font-medium text-zinc-100 leading-snug">{s.company_name}</p>
                      {s.contact_name && <p className="text-[11px] text-zinc-500 mt-0.5">{s.contact_name}</p>}
                      {locText && (
                        <p className="text-[10px] text-zinc-600 flex items-center gap-1 mt-0.5">
                          <MapPin size={9} />
                          {locText}
                        </p>
                      )}
                      <div className="mt-2 flex items-center justify-between">
                        {statusBadge(s.status)}
                        <div className="flex items-center gap-1">
                          {canInvite && (
                            <button
                              type="button"
                              disabled={busyId === s.id}
                              onClick={() => sendInvite(s)}
                              title="Send invite"
                              className="p-1 text-zinc-500 hover:text-emerald-400 transition-colors disabled:opacity-40"
                            >
                              <Send size={13} />
                            </button>
                          )}
                          <button
                            type="button"
                            disabled={busyId === s.id || stageIdx <= 0}
                            onClick={() => moveStage(s, -1)}
                            title="Move back"
                            className="p-1 text-zinc-600 hover:text-zinc-200 transition-colors disabled:opacity-30"
                          >
                            <ChevronLeft size={14} />
                          </button>
                          <button
                            type="button"
                            disabled={busyId === s.id || stageIdx >= STAGES.length - 1}
                            onClick={() => moveStage(s, 1)}
                            title="Move forward"
                            className="p-1 text-zinc-600 hover:text-zinc-200 transition-colors disabled:opacity-30"
                          >
                            <ChevronRight size={14} />
                          </button>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
