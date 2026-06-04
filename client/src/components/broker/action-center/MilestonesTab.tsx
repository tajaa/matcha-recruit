import { useEffect, useState } from 'react'
import { Award, ShieldCheck, TrendingDown, Sparkles, Check, Loader2, PartyPopper } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { fetchActionCenterMilestones, markMilestoneRead } from '../../../api/broker'
import { fmtDate } from '../../../utils/brokerFormat'
import type { BrokerMilestone, MilestoneFamily } from '../../../types/broker'
import OutreachDrawer from './OutreachDrawer'

const FAMILY_ICON: Record<MilestoneFamily, LucideIcon> = {
  incident_free: Award,
  dart_free: ShieldCheck,
  trir_below_benchmark: TrendingDown,
}

export function MilestonesTab() {
  const [milestones, setMilestones] = useState<BrokerMilestone[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [outreach, setOutreach] = useState<{ id: string; name: string } | null>(null)

  useEffect(() => {
    fetchActionCenterMilestones()
      .then((r) => setMilestones(r.milestones))
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load milestones'))
      .finally(() => setLoading(false))
  }, [])

  async function handleRead(id: string) {
    setMilestones((prev) => prev.map((m) => (m.id === id ? { ...m, is_read: true } : m)))
    try {
      await markMilestoneRead(id)
    } catch {
      setMilestones((prev) => prev.map((m) => (m.id === id ? { ...m, is_read: false } : m)))
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <Loader2 className="w-5 h-5 text-zinc-600 animate-spin" />
      </div>
    )
  }

  if (error) {
    return <div className="bg-red-500/10 border border-red-500/20 rounded-2xl p-4 text-sm text-red-400">{error}</div>
  }

  if (milestones.length === 0) {
    return (
      <div className="bg-zinc-900 border border-white/10 rounded-2xl p-12 text-center">
        <PartyPopper className="w-6 h-6 text-zinc-700 mx-auto mb-2" />
        <p className="text-sm text-zinc-400">No milestones yet.</p>
        <p className="text-[11px] text-zinc-600 mt-1">
          Positive safety achievements (incident-free streaks, DART-free quarters, TRIR below benchmark) show up here.
        </p>
      </div>
    )
  }

  return (
    <>
      <div className="space-y-2">
        {milestones.map((m) => {
          const Icon = FAMILY_ICON[m.milestone_family] ?? Award
          return (
            <div
              key={m.id}
              className={`bg-zinc-900 border rounded-xl p-4 flex items-start gap-3 transition-colors ${
                m.is_read ? 'border-white/5' : 'border-emerald-500/20'
              }`}
            >
              <div className="mt-0.5 w-8 h-8 rounded-lg bg-emerald-500/10 flex items-center justify-center shrink-0">
                <Icon className="w-4 h-4 text-emerald-400" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  {!m.is_read && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />}
                  <h3 className="text-[13px] font-medium text-zinc-100 truncate">{m.title}</h3>
                </div>
                <p className="text-[11px] text-zinc-500 mt-0.5">
                  {m.company_name}
                  {m.detail ? ` · ${m.detail}` : ''}
                  {` · ${fmtDate(m.achieved_at)}`}
                </p>
                <button
                  type="button"
                  onClick={() => setOutreach({ id: m.company_id, name: m.company_name })}
                  className="mt-2 inline-flex items-center gap-1.5 text-[11px] text-emerald-400 hover:text-emerald-300 transition-colors"
                >
                  <Sparkles className="w-3 h-3" />
                  Outreach ideas
                </button>
              </div>
              {!m.is_read && (
                <button
                  type="button"
                  onClick={() => handleRead(m.id)}
                  title="Mark seen"
                  className="p-1.5 text-zinc-600 hover:text-zinc-300 transition-colors shrink-0"
                >
                  <Check className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          )
        })}
      </div>

      {outreach && (
        <OutreachDrawer companyId={outreach.id} companyName={outreach.name} onClose={() => setOutreach(null)} />
      )}
    </>
  )
}

export default MilestonesTab
