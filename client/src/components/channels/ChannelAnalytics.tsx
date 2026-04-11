import { useState, useEffect } from 'react'
import { X, Users, DollarSign, MessageSquare, TrendingUp, Heart, AlertTriangle, UserMinus } from 'lucide-react'
import { getChannelAnalytics } from '../../api/channels'
import type { ChannelAnalytics as ChannelAnalyticsData } from '../../api/channels'

interface Props {
  channelId: string
  channelName: string
  onClose: () => void
}

function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days === 1) return 'yesterday'
  return `${days}d ago`
}

export default function ChannelAnalytics({ channelId, channelName, onClose }: Props) {
  const [data, setData] = useState<ChannelAnalyticsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true)
    getChannelAnalytics(channelId)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load analytics'))
      .finally(() => setLoading(false))
  }, [channelId])

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-end">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative w-full max-w-lg h-full bg-zinc-900 border-l border-zinc-800 overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-zinc-900 border-b border-zinc-800 px-5 py-4 flex items-center justify-between z-10">
          <div>
            <h2 className="text-white font-semibold text-lg">Channel Analytics</h2>
            <p className="text-zinc-500 text-xs mt-0.5">#{channelName}</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-zinc-800 text-zinc-500 hover:text-white">
            <X size={18} />
          </button>
        </div>

        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="w-5 h-5 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {error && (
          <div className="px-5 py-8 text-center text-red-400 text-sm">{error}</div>
        )}

        {data && (
          <div className="p-5 space-y-6">
            {/* Stat cards */}
            <div className="grid grid-cols-2 gap-3">
              <StatCard
                icon={<Users size={16} />}
                label="Total Subscribers"
                value={String(data.subscribers.total)}
                accent="emerald"
              />
              <StatCard
                icon={<DollarSign size={16} />}
                label="MRR"
                value={formatCents(data.revenue.mrr_cents)}
                accent="emerald"
              />
              <StatCard
                icon={<TrendingUp size={16} />}
                label="Total Revenue"
                value={formatCents(data.revenue.total_cents)}
                accent="blue"
              />
              <StatCard
                icon={<MessageSquare size={16} />}
                label="Messages / mo"
                value={String(data.activity.messages_this_month)}
                accent="violet"
              />
            </div>

            {/* Members section */}
            <Section title="Members">
              {/* Status breakdown bar */}
              {data.subscribers.total > 0 && (
                <div className="space-y-2">
                  <div className="flex h-2.5 rounded-full overflow-hidden bg-zinc-800">
                    {data.subscribers.active > 0 && (
                      <div
                        className="bg-emerald-500 transition-all"
                        style={{ width: `${(data.subscribers.active / data.subscribers.total) * 100}%` }}
                      />
                    )}
                    {data.subscribers.past_due > 0 && (
                      <div
                        className="bg-amber-500 transition-all"
                        style={{ width: `${(data.subscribers.past_due / data.subscribers.total) * 100}%` }}
                      />
                    )}
                    {data.subscribers.canceled > 0 && (
                      <div
                        className="bg-red-500 transition-all"
                        style={{ width: `${(data.subscribers.canceled / data.subscribers.total) * 100}%` }}
                      />
                    )}
                  </div>
                  <div className="flex gap-4 text-xs">
                    <span className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-emerald-500" />
                      <span className="text-zinc-400">Active {data.subscribers.active}</span>
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-amber-500" />
                      <span className="text-zinc-400">Past due {data.subscribers.past_due}</span>
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-red-500" />
                      <span className="text-zinc-400">Canceled {data.subscribers.canceled}</span>
                    </span>
                  </div>
                </div>
              )}

              {/* Most active members */}
              {data.activity.most_active_members.length > 0 && (
                <div className="mt-4">
                  <h4 className="text-xs font-medium text-zinc-500 uppercase mb-2">Most Active (30d)</h4>
                  <div className="space-y-1">
                    {data.activity.most_active_members.map((m, i) => (
                      <div key={m.user_id} className="flex items-center gap-3 py-1.5 px-2 rounded hover:bg-zinc-800/50">
                        <span className="text-xs text-zinc-600 w-4 text-right">{i + 1}</span>
                        <div className="w-6 h-6 rounded-full bg-zinc-700 flex items-center justify-center text-[10px] text-zinc-300 font-medium shrink-0">
                          {m.name.charAt(0).toUpperCase()}
                        </div>
                        <div className="flex-1 min-w-0">
                          <span className="text-sm text-zinc-200 truncate block">{m.name}</span>
                        </div>
                        <span className="text-xs text-emerald-400 font-medium">{m.message_count} msgs</span>
                        <span className="text-[10px] text-zinc-600">{relativeTime(m.last_active)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Section>

            {/* Revenue section */}
            <Section title="Revenue">
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="bg-zinc-800/50 rounded-lg p-3">
                  <p className="text-[10px] uppercase text-zinc-500 mb-1">Subscriptions</p>
                  <p className="text-lg font-semibold text-white">{formatCents(data.revenue.total_subscription_cents)}</p>
                </div>
                <div className="bg-zinc-800/50 rounded-lg p-3">
                  <p className="text-[10px] uppercase text-zinc-500 mb-1">Tips</p>
                  <p className="text-lg font-semibold text-white">{formatCents(data.revenue.total_tips_cents)}</p>
                </div>
              </div>

              {/* Recent tips */}
              {data.tips.recent.length > 0 && (
                <div>
                  <h4 className="text-xs font-medium text-zinc-500 uppercase mb-2">Recent Tips</h4>
                  <div className="space-y-1.5">
                    {data.tips.recent.map((tip, i) => (
                      <div key={i} className="flex items-start gap-2 py-1.5 px-2 rounded bg-zinc-800/30">
                        <Heart size={12} className="text-pink-400 mt-0.5 shrink-0" />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-baseline gap-2">
                            <span className="text-sm text-zinc-200">{tip.sender_name}</span>
                            <span className="text-xs font-medium text-emerald-400">{formatCents(tip.amount_cents)}</span>
                          </div>
                          {tip.message && (
                            <p className="text-xs text-zinc-500 mt-0.5 truncate">{tip.message}</p>
                          )}
                        </div>
                        <span className="text-[10px] text-zinc-600 shrink-0">{relativeTime(tip.created_at)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {data.tips.tip_count === 0 && (
                <p className="text-xs text-zinc-600 text-center py-2">No tips yet</p>
              )}
            </Section>

            {/* Engagement section */}
            <Section title="Engagement">
              <div className="grid grid-cols-3 gap-3">
                <div className="bg-zinc-800/50 rounded-lg p-3 text-center">
                  <p className="text-lg font-semibold text-white">{data.engagement.avg_messages_per_day}</p>
                  <p className="text-[10px] uppercase text-zinc-500 mt-1">Msgs / day</p>
                </div>
                <div className="bg-zinc-800/50 rounded-lg p-3 text-center">
                  <div className="flex items-center justify-center gap-1">
                    <AlertTriangle size={12} className={data.engagement.members_at_risk > 0 ? 'text-amber-400' : 'text-zinc-600'} />
                    <p className={`text-lg font-semibold ${data.engagement.members_at_risk > 0 ? 'text-amber-400' : 'text-white'}`}>
                      {data.engagement.members_at_risk}
                    </p>
                  </div>
                  <p className="text-[10px] uppercase text-zinc-500 mt-1">At Risk</p>
                </div>
                <div className="bg-zinc-800/50 rounded-lg p-3 text-center">
                  <div className="flex items-center justify-center gap-1">
                    <UserMinus size={12} className={data.engagement.recent_removals > 0 ? 'text-red-400' : 'text-zinc-600'} />
                    <p className={`text-lg font-semibold ${data.engagement.recent_removals > 0 ? 'text-red-400' : 'text-white'}`}>
                      {data.engagement.recent_removals}
                    </p>
                  </div>
                  <p className="text-[10px] uppercase text-zinc-500 mt-1">Removed (30d)</p>
                </div>
              </div>

              {/* Message breakdown */}
              <div className="mt-3 flex items-center gap-4 text-xs text-zinc-500">
                <span>Today: <span className="text-zinc-300">{data.activity.messages_today}</span></span>
                <span>This week: <span className="text-zinc-300">{data.activity.messages_this_week}</span></span>
                <span>This month: <span className="text-zinc-300">{data.activity.messages_this_month}</span></span>
              </div>
            </Section>
          </div>
        )}
      </div>
    </div>
  )
}

function StatCard({ icon, label, value, accent }: { icon: React.ReactNode; label: string; value: string; accent: string }) {
  const colors: Record<string, string> = {
    emerald: 'text-emerald-400 bg-emerald-500/10',
    blue: 'text-blue-400 bg-blue-500/10',
    violet: 'text-violet-400 bg-violet-500/10',
  }
  const c = colors[accent] || colors.emerald
  return (
    <div className="bg-zinc-800/50 border border-zinc-800 rounded-lg p-3">
      <div className="flex items-center gap-2 mb-2">
        <div className={`p-1 rounded ${c}`}>{icon}</div>
        <span className="text-[10px] uppercase text-zinc-500">{label}</span>
      </div>
      <p className="text-xl font-semibold text-white">{value}</p>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3">{title}</h3>
      {children}
    </div>
  )
}
