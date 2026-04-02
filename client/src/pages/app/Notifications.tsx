import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Bell } from 'lucide-react'
import { api } from '../../api/client'

interface NotificationItem {
  id: string
  type: string
  title: string
  subtitle: string | null
  severity: string | null
  status: string | null
  created_at: string
  link: string | null
}

interface NotificationsResponse {
  items: NotificationItem[]
  total: number
}

const SEV_DOT: Record<string, string> = {
  critical: 'bg-red-500',
  expired: 'bg-red-500',
  high: 'bg-orange-500',
  warning: 'bg-amber-500',
  medium: 'bg-yellow-500',
  low: 'bg-blue-400',
  info: 'bg-zinc-500',
}

const TYPE_LABEL: Record<string, { text: string; color: string }> = {
  incident: { text: 'Incident', color: 'bg-red-900/30 text-red-400 border-red-800/40' },
  er_case: { text: 'ER Case', color: 'bg-blue-900/30 text-blue-400 border-blue-800/40' },
  compliance_alert: { text: 'Compliance', color: 'bg-amber-900/30 text-amber-400 border-amber-800/40' },
  credential_expiry: { text: 'Credential', color: 'bg-orange-900/30 text-orange-400 border-orange-800/40' },
  employee: { text: 'Employee', color: 'bg-emerald-900/30 text-emerald-400 border-emerald-800/40' },
  offer_letter: { text: 'Offer', color: 'bg-violet-900/30 text-violet-400 border-violet-800/40' },
  handbook: { text: 'Handbook', color: 'bg-cyan-900/30 text-cyan-400 border-cyan-800/40' },
}

function relativeTime(iso: string): string {
  const now = Date.now()
  const then = new Date(iso).getTime()
  const diffSec = Math.floor((now - then) / 1000)
  if (diffSec < 60) return 'Just now'
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`
  const days = Math.floor(diffSec / 86400)
  if (days === 1) return 'Yesterday'
  if (days < 30) return `${days}d ago`
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export default function Notifications() {
  const navigate = useNavigate()
  const [items, setItems] = useState<NotificationItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)

  const load = useCallback(async (offset = 0) => {
    const isInitial = offset === 0
    if (isInitial) setLoading(true)
    else setLoadingMore(true)
    try {
      const data = await api.get<NotificationsResponse>(`/dashboard/notifications?limit=30&offset=${offset}`)
      if (isInitial) {
        setItems(data.items)
      } else {
        setItems((prev) => [...prev, ...data.items])
      }
      setTotal(data.total)
    } catch {}
    setLoading(false)
    setLoadingMore(false)
  }, [])

  useEffect(() => { load() }, [load])

  return (
    <div className="max-w-2xl mx-auto py-8 px-6">
      <div className="flex items-center gap-3 mb-6">
        <Bell className="w-5 h-5 text-zinc-400" />
        <h1 className="text-xl font-semibold text-zinc-100">Notifications</h1>
        <span className="text-xs text-zinc-500">{total} total</span>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-5 h-5 text-zinc-500 animate-spin" />
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-16">
          <Bell className="w-8 h-8 text-zinc-700 mx-auto mb-3" />
          <p className="text-sm text-zinc-500">No recent activity</p>
        </div>
      ) : (
        <div className="space-y-px rounded-xl border border-zinc-800 overflow-hidden">
          {items.map((item) => {
            const typeMeta = TYPE_LABEL[item.type] ?? { text: item.type, color: 'bg-zinc-800 text-zinc-400 border-zinc-700' }
            return (
              <button
                key={`${item.type}-${item.id}`}
                onClick={() => item.link && navigate(item.link)}
                disabled={!item.link}
                className="flex items-start gap-3 w-full px-4 py-3 text-left bg-zinc-900 hover:bg-zinc-800/70 transition-colors disabled:cursor-default"
              >
                <span className={`mt-1.5 h-2 w-2 rounded-full shrink-0 ${SEV_DOT[item.severity ?? 'info'] ?? SEV_DOT.info}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border ${typeMeta.color}`}>
                      {typeMeta.text}
                    </span>
                    {item.status && (
                      <span className="text-[10px] text-zinc-500">{item.status}</span>
                    )}
                  </div>
                  <p className="text-sm text-zinc-200 truncate">{item.title}</p>
                  {item.subtitle && (
                    <p className="text-xs text-zinc-500 truncate mt-0.5">{item.subtitle}</p>
                  )}
                </div>
                <span className="text-[10px] text-zinc-600 shrink-0 mt-1">{relativeTime(item.created_at)}</span>
              </button>
            )
          })}
        </div>
      )}

      {!loading && items.length < total && (
        <div className="flex justify-center mt-4">
          <button
            onClick={() => load(items.length)}
            disabled={loadingMore}
            className="text-xs text-zinc-400 hover:text-zinc-200 transition-colors flex items-center gap-1.5"
          >
            {loadingMore && <Loader2 className="w-3 h-3 animate-spin" />}
            {loadingMore ? 'Loading...' : `Load more (${total - items.length} remaining)`}
          </button>
        </div>
      )}
    </div>
  )
}
