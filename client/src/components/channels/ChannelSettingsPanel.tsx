import { useState, useEffect } from 'react'
import { X, Hash } from 'lucide-react'
import {
  updatePaidSettings,
  getMemberActivity,
  getChannelRevenue,
  getChannelPaymentInfo,
} from '../../api/channels'
import type { MemberActivity, ChannelRevenue } from '../../api/channels'

interface Props {
  channelId: string
  channelName: string
  isPaid: boolean
  onClose: () => void
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const days = Math.floor(diff / 86400000)
  if (days === 0) return 'today'
  if (days === 1) return 'yesterday'
  return `${days}d ago`
}

const statusColors: Record<string, string> = {
  active: 'bg-emerald-500',
  at_risk: 'bg-amber-500',
  warned: 'bg-red-500',
  expired: 'bg-zinc-500',
  exempt: 'bg-blue-500',
}

export default function ChannelSettingsPanel({
  channelId,
  channelName,
  isPaid,
  onClose,
}: Props) {
  const [members, setMembers] = useState<MemberActivity[]>([])
  const [revenue, setRevenue] = useState<ChannelRevenue | null>(null)
  const [threshold, setThreshold] = useState<number>(14)
  const [warningDays, setWarningDays] = useState<number>(3)
  const [, setSettingsLoaded] = useState(false)

  useEffect(() => {
    if (!isPaid) return
    getMemberActivity(channelId).then(setMembers).catch(() => {})
    getChannelRevenue(channelId).then(setRevenue).catch(() => {})
    // Load current settings from server
    getChannelPaymentInfo(channelId).then((info) => {
      if (info.inactivity_threshold_days != null) setThreshold(info.inactivity_threshold_days)
      if (info.inactivity_warning_days != null) setWarningDays(info.inactivity_warning_days)
      setSettingsLoaded(true)
    }).catch(() => setSettingsLoaded(true))
  }, [channelId, isPaid])

  const activeCount = members.filter((m) => m.activity_status === 'active').length
  const atRiskCount = members.filter((m) => m.activity_status === 'at_risk').length
  const warnedCount = members.filter((m) => m.activity_status === 'warned').length

  const handleThresholdChange = (value: number) => {
    setThreshold(value)
    updatePaidSettings(channelId, { inactivity_threshold_days: value }).catch(() => {})
  }

  const handleWarningChange = (value: number) => {
    setWarningDays(value)
    updatePaidSettings(channelId, { inactivity_warning_days: value }).catch(() => {})
  }

  return (
    <div className="fixed top-0 right-0 w-80 h-full bg-zinc-900 border-l border-zinc-800 overflow-y-auto z-50 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
        <div className="flex items-center gap-2">
          <Hash className="w-4 h-4 text-emerald-500" />
          <h2 className="text-sm font-semibold text-zinc-100 truncate">{channelName}</h2>
        </div>
        <button onClick={onClose} className="text-zinc-400 hover:text-zinc-300 transition-colors">
          <X className="w-4 h-4" />
        </button>
      </div>

      {!isPaid ? (
        <div className="flex-1 flex items-center justify-center px-4">
          <p className="text-sm text-zinc-500 text-center">This is a free channel</p>
        </div>
      ) : (
        <div className="flex-1 p-4 space-y-6">
          {/* Activity Summary */}
          <section className="space-y-3">
            <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wider">
              Activity Summary
            </h3>
            <div className="flex gap-2">
              <span className="text-xs px-2 py-1 rounded-full bg-emerald-900/30 text-emerald-400 border border-emerald-800/40">
                {activeCount} active
              </span>
              <span className="text-xs px-2 py-1 rounded-full bg-amber-900/30 text-amber-400 border border-amber-800/40">
                {atRiskCount} at risk
              </span>
              <span className="text-xs px-2 py-1 rounded-full bg-red-900/30 text-red-400 border border-red-800/40">
                {warnedCount} warned
              </span>
            </div>

            <div className="space-y-1">
              {members.map((m) => (
                <div
                  key={m.user_id}
                  className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-zinc-800/50 transition-colors"
                >
                  <span className={`w-2 h-2 rounded-full shrink-0 ${statusColors[m.activity_status] || 'bg-zinc-500'}`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-zinc-300 truncate">{m.name}</p>
                    <div className="flex items-center gap-2 text-xs text-zinc-500">
                      {m.last_contributed_at && (
                        <span>{relativeTime(m.last_contributed_at)}</span>
                      )}
                      {m.days_until_removal != null && (
                        <span className="text-amber-500">
                          {m.days_until_removal}d left
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Inactivity Settings */}
          <section className="space-y-3">
            <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wider">
              Inactivity Settings
            </h3>
            <div className="space-y-2">
              <label className="block">
                <span className="text-xs text-zinc-500">Removal threshold</span>
                <select
                  value={threshold}
                  onChange={(e) => handleThresholdChange(Number(e.target.value))}
                  className="mt-1 block w-full rounded-lg bg-zinc-800 border border-zinc-700 text-sm text-zinc-300 px-3 py-1.5 focus:outline-none focus:border-emerald-600"
                >
                  <option value={7}>7 days</option>
                  <option value={14}>14 days</option>
                  <option value={21}>21 days</option>
                  <option value={30}>30 days</option>
                </select>
              </label>
              <label className="block">
                <span className="text-xs text-zinc-500">Warning before removal</span>
                <select
                  value={warningDays}
                  onChange={(e) => handleWarningChange(Number(e.target.value))}
                  className="mt-1 block w-full rounded-lg bg-zinc-800 border border-zinc-700 text-sm text-zinc-300 px-3 py-1.5 focus:outline-none focus:border-emerald-600"
                >
                  <option value={1}>1 day</option>
                  <option value={2}>2 days</option>
                  <option value={3}>3 days</option>
                  <option value={5}>5 days</option>
                  <option value={7}>7 days</option>
                </select>
              </label>
            </div>
          </section>

          {/* Revenue */}
          {revenue && (
            <section className="space-y-3">
              <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wider">
                Revenue
              </h3>
              <div className="grid grid-cols-3 gap-2">
                <div className="bg-zinc-800/50 rounded-lg p-2 text-center">
                  <p className="text-lg font-semibold text-zinc-100">{revenue.subscriber_count}</p>
                  <p className="text-xs text-zinc-500">Subscribers</p>
                </div>
                <div className="bg-zinc-800/50 rounded-lg p-2 text-center">
                  <p className="text-lg font-semibold text-emerald-400">
                    ${(revenue.mrr_cents / 100).toFixed(2)}
                  </p>
                  <p className="text-xs text-zinc-500">MRR</p>
                </div>
                <div className="bg-zinc-800/50 rounded-lg p-2 text-center">
                  <p className="text-lg font-semibold text-zinc-100">
                    ${(revenue.total_revenue_cents / 100).toFixed(2)}
                  </p>
                  <p className="text-xs text-zinc-500">Total</p>
                </div>
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  )
}
