import { useEffect, useMemo, useState, useCallback } from 'react'
import { relativeTime as baseRelativeTime, shortDate } from '../../../utils/format'

// Sentence-cased to match the surrounding labels, and a narrow absolute format
// because this renders inside a dropdown.
const relativeTime = (iso: string) =>
  baseRelativeTime(iso, {
    justNowLabel: 'Just now',
    yesterdayLabel: 'Yesterday',
    absolute: shortDate,
  })
import { useNavigate } from 'react-router-dom'
import { Loader2, Bell } from 'lucide-react'
import { api } from '../../../api/client'

interface NotificationItem {
  id: string
  type: string
  title: string
  subtitle: string | null
  severity: string | null
  status: string | null
  created_at: string
  link: string | null
  workspace_notification_id?: string
}

interface NotificationsResponse {
  items: NotificationItem[]
  total: number
}

interface WorkspaceNotificationsResponse {
  notifications: Array<{
    id: string
    type: string
    title: string
    body: string | null
    link: string | null
    created_at: string
  }>
  total: number
}

const PAGE_SIZE = 30

type LoadResult<T> = { ok: true; data: T } | { ok: false }

async function settle<T>(request: Promise<T>): Promise<LoadResult<T>> {
  try {
    return { ok: true, data: await request }
  } catch {
    return { ok: false }
  }
}

function workspaceItems(response: WorkspaceNotificationsResponse): NotificationItem[] {
  return response.notifications.map((item) => ({
    id: item.id,
    type: item.type,
    title: item.title,
    subtitle: item.body,
    severity: null,
    status: null,
    created_at: item.created_at,
    link: item.link,
    workspace_notification_id: item.id,
  }))
}

function appendUnique(current: NotificationItem[], incoming: NotificationItem[]): NotificationItem[] {
  const existing = new Set(current.map((item) => item.id))
  return [...current, ...incoming.filter((item) => !existing.has(item.id))]
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
  schedule_request_pending: { text: 'Schedule', color: 'bg-sky-900/30 text-sky-400 border-sky-800/40' },
  job_posting_invite: { text: 'Job Invite', color: 'bg-emerald-900/30 text-emerald-400 border-emerald-800/40' },
  job_application_received: { text: 'Application', color: 'bg-blue-900/30 text-blue-400 border-blue-800/40' },
  job_application_status_changed: { text: 'Status Update', color: 'bg-purple-900/30 text-purple-400 border-purple-800/40' },
}

export default function Notifications() {
  const navigate = useNavigate()
  const [dashboardItems, setDashboardItems] = useState<NotificationItem[]>([])
  const [workspaceFeedItems, setWorkspaceFeedItems] = useState<NotificationItem[]>([])
  const [dashboardTotal, setDashboardTotal] = useState<number | null>(null)
  const [workspaceTotal, setWorkspaceTotal] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [loadError, setLoadError] = useState(false)

  const loadInitial = useCallback(async () => {
    setLoading(true)
    setLoadError(false)
    const [dashboard, workspace] = await Promise.all([
      settle(api.get<NotificationsResponse>(`/dashboard/notifications?limit=${PAGE_SIZE}&offset=0`)),
      settle(api.get<WorkspaceNotificationsResponse>(`/matcha-work/notifications?limit=${PAGE_SIZE}&offset=0`)),
    ])
    if (dashboard.ok) {
      setDashboardItems(dashboard.data.items)
      setDashboardTotal(dashboard.data.total)
    } else {
      setDashboardItems([])
      setDashboardTotal(null)
    }
    if (workspace.ok) {
      setWorkspaceFeedItems(workspaceItems(workspace.data))
      setWorkspaceTotal(workspace.data.total)
    } else {
      setWorkspaceFeedItems([])
      setWorkspaceTotal(null)
    }
    setLoadError(!dashboard.ok || !workspace.ok)
    setLoading(false)
  }, [])

  useEffect(() => { void loadInitial() }, [loadInitial])

  const items = useMemo(
    () => [...dashboardItems, ...workspaceFeedItems]
      .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)),
    [dashboardItems, workspaceFeedItems],
  )
  const total = dashboardTotal !== null && workspaceTotal !== null
    ? dashboardTotal + workspaceTotal
    : null
  const hasMore = dashboardTotal === null || dashboardItems.length < dashboardTotal
    || workspaceTotal === null || workspaceFeedItems.length < workspaceTotal

  async function loadMore() {
    setLoadingMore(true)
    const needsDashboard = dashboardTotal === null || dashboardItems.length < dashboardTotal
    const needsWorkspace = workspaceTotal === null || workspaceFeedItems.length < workspaceTotal
    const [dashboard, workspace] = await Promise.all([
      needsDashboard
        ? settle(api.get<NotificationsResponse>(`/dashboard/notifications?limit=${PAGE_SIZE}&offset=${dashboardItems.length}`))
        : Promise.resolve<LoadResult<NotificationsResponse> | null>(null),
      needsWorkspace
        ? settle(api.get<WorkspaceNotificationsResponse>(`/matcha-work/notifications?limit=${PAGE_SIZE}&offset=${workspaceFeedItems.length}`))
        : Promise.resolve<LoadResult<WorkspaceNotificationsResponse> | null>(null),
    ])

    if (dashboard?.ok) {
      setDashboardItems((current) => appendUnique(current, dashboard.data.items))
      setDashboardTotal(dashboard.data.total)
    }
    if (workspace?.ok) {
      setWorkspaceFeedItems((current) => appendUnique(current, workspaceItems(workspace.data)))
      setWorkspaceTotal(workspace.data.total)
    }
    setLoadError(dashboard?.ok === false || workspace?.ok === false)
    setLoadingMore(false)
  }

  return (
    <div className="max-w-2xl mx-auto py-8 px-6">
      <div className="flex items-center gap-3 mb-6">
        <Bell className="w-5 h-5 text-zinc-400" />
        <h1 className="text-xl font-semibold text-zinc-100">Notifications</h1>
        <span className="text-xs text-zinc-500">
          {total === null ? `${items.length} loaded` : `${total} total`}
        </span>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-5 h-5 text-zinc-500 animate-spin" />
        </div>
      ) : loadError && items.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-sm text-zinc-400">Could not load notifications.</p>
          <button onClick={() => void loadInitial()} className="mt-2 text-xs text-zinc-500 hover:text-zinc-200">
            Try again
          </button>
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-16">
          <Bell className="w-8 h-8 text-zinc-700 mx-auto mb-3" />
          <p className="text-sm text-zinc-500">No recent activity</p>
        </div>
      ) : (
        <>
          {loadError && (
            <div className="mb-3 rounded-lg border border-amber-900/50 bg-amber-950/20 px-3 py-2 text-xs text-amber-300">
              Some notifications could not be loaded. Use Load more to retry.
            </div>
          )}
          <div className="space-y-px rounded-xl border border-zinc-800 overflow-hidden">
            {items.map((item) => {
              const typeMeta = TYPE_LABEL[item.type] ?? { text: item.type, color: 'bg-zinc-800 text-zinc-400 border-zinc-700' }
              return (
                <button
                  key={`${item.type}-${item.id}`}
                  onClick={() => {
                    if (!item.link) return
                    if (item.workspace_notification_id) {
                      api.post('/matcha-work/notifications/mark-read', {
                        notification_ids: [item.workspace_notification_id],
                      }).catch(() => {})
                    }
                    navigate(item.link)
                  }}
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
        </>
      )}

      {!loading && hasMore && items.length > 0 && (
        <div className="flex justify-center mt-4">
          <button
            onClick={() => void loadMore()}
            disabled={loadingMore}
            className="text-xs text-zinc-400 hover:text-zinc-200 transition-colors flex items-center gap-1.5"
          >
            {loadingMore && <Loader2 className="w-3 h-3 animate-spin" />}
            {loadingMore
              ? 'Loading...'
              : total === null ? 'Load more' : `Load more (${Math.max(0, total - items.length)} remaining)`}
          </button>
        </div>
      )}
    </div>
  )
}
