/* eslint-disable react-hooks/set-state-in-effect -- Effects intentionally synchronize this tool with loaded data, URL selections, and preview inputs. */
import { AdminButton as Button, AdminTable } from '../../../components/admin/AdminUI'
import { AdminTab, AdminTabBar } from '../../../components/admin/AdminTabs'
import { AdminWorkspace } from '../../../components/admin/AdminWorkspace'
import { useEffect, useState } from 'react'
import { api } from '../../../api/client'

type ActivityLog = {
  id: string
  location_name: string | null
  check_type: string
  status: string
  started_at: string | null
  new_count: number
  updated_count: number
  alert_count: number
  error_message: string | null
}

type SchedulerSetting = {
  id: string
  task_key: string
  display_name: string
  description: string | null
  enabled: boolean
  max_per_cycle: number
  stats: Record<string, unknown>
}

function fmtRelative(iso: string | null): string {
  if (!iso) return '—'
  const diffMs = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diffMs / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

type Tab = 'jobs' | 'activity'

// Platform infra — all scheduled Celery jobs (not just compliance-library
// ones) + their recent-run logs. Deliberately kept OUT of Compliance Studio so
// that page stays scoped to the two library-growth funnels.
export default function Automation() {
  const [tab, setTab] = useState<Tab>('jobs')

  const [schedulers, setSchedulers] = useState<SchedulerSetting[]>([])
  const [loadingJobs, setLoadingJobs] = useState(true)
  const [triggeringKey, setTriggeringKey] = useState<string | null>(null)

  const [activity, setActivity] = useState<ActivityLog[]>([])
  const [activityStats, setActivityStats] = useState<{ checks_24h: number; failed_24h: number } | null>(null)
  const [loadingActivity, setLoadingActivity] = useState(false)

  const fetchJobs = async () => {
    setLoadingJobs(true)
    try { setSchedulers(await api.get<SchedulerSetting[]>('/admin/schedulers')) }
    catch { setSchedulers([]) }
    finally { setLoadingJobs(false) }
  }

  const fetchActivity = async () => {
    setLoadingActivity(true)
    try {
      const data = await api.get<{ overview: { checks_24h: number; failed_24h: number }; recent_logs: ActivityLog[] }>('/admin/schedulers/stats')
      setActivity(data.recent_logs); setActivityStats(data.overview)
    } catch { setActivity([]) }
    finally { setLoadingActivity(false) }
  }

  useEffect(() => { fetchJobs() }, [])
  useEffect(() => { if (tab === 'activity' && activity.length === 0) fetchActivity() }, [tab]) // eslint-disable-line react-hooks/exhaustive-deps

  async function toggleScheduler(taskKey: string, currentEnabled: boolean) {
    await api.patch(`/admin/schedulers/${taskKey}`, { enabled: !currentEnabled })
    setSchedulers((prev) => prev.map((s) => s.task_key === taskKey ? { ...s, enabled: !s.enabled } : s))
  }

  async function triggerScheduler(taskKey: string) {
    setTriggeringKey(taskKey)
    try { await api.post(`/admin/schedulers/${taskKey}/trigger`, {}) }
    finally { setTriggeringKey(null) }
  }

  return (
    <AdminWorkspace title="Automation" description="Scheduled jobs across the platform and their recent run logs.">
      <AdminTabBar>
        {([['jobs', 'Scheduled Jobs', schedulers.length], ['activity', 'Recent Activity', undefined]] as const).map(([id, label, count]) => (
          <AdminTab key={id} type="button" onClick={() => setTab(id)}
           active={tab === id}>
            {label}{count !== undefined && count > 0 ? ` (${count})` : ''}
          </AdminTab>
        ))}
      </AdminTabBar>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {tab === 'jobs' && (
          <div>
            {loadingJobs ? (
              <p className="text-sm text-zinc-500">Loading...</p>
            ) : schedulers.length === 0 ? (
              <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
                <p className="text-sm text-zinc-600">No scheduled jobs configured.</p>
              </div>
            ) : (
              <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
                {schedulers.map((sched) => (
                  <div key={sched.id} className="flex items-center gap-4 px-4 py-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className={`w-1.5 h-1.5 rounded-full ${sched.enabled ? 'bg-emerald-400' : 'bg-zinc-600'}`} />
                        <p className="text-sm font-medium text-zinc-200">{sched.display_name}</p>
                      </div>
                      {sched.description && <p className="text-xs text-zinc-500 mt-0.5 ml-3.5">{sched.description}</p>}
                      <p className="text-[11px] text-zinc-600 mt-0.5 ml-3.5">Max {sched.max_per_cycle} per cycle</p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <button type="button" onClick={() => toggleScheduler(sched.task_key, sched.enabled)}
                        className={`text-xs px-2 py-1 transition-colors ${sched.enabled ? 'text-zinc-400 hover:text-red-400' : 'text-zinc-600 hover:text-emerald-400'}`}>
                        {sched.enabled ? 'Disable' : 'Enable'}
                      </button>
                      <Button variant="ghost" size="sm" disabled={triggeringKey !== null} onClick={() => triggerScheduler(sched.task_key)}>
                        {triggeringKey === sched.task_key ? 'Running...' : 'Trigger'}
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {tab === 'activity' && (
          <div>
            {activityStats && (
              <div className="grid grid-cols-2 gap-3 mb-4">
                <div className="border border-zinc-800 rounded-lg px-4 py-3 text-center">
                  <p className="text-xl font-semibold text-zinc-100">{activityStats.checks_24h}</p>
                  <p className="text-[11px] text-zinc-500 uppercase tracking-wide mt-0.5">Checks (24h)</p>
                </div>
                <div className="border border-zinc-800 rounded-lg px-4 py-3 text-center">
                  <p className={`text-xl font-semibold ${activityStats.failed_24h > 0 ? 'text-red-400' : 'text-zinc-100'}`}>{activityStats.failed_24h}</p>
                  <p className="text-[11px] text-zinc-500 uppercase tracking-wide mt-0.5">Failed (24h)</p>
                </div>
              </div>
            )}

            {loadingActivity ? (
              <p className="text-sm text-zinc-500">Loading...</p>
            ) : activity.length === 0 ? (
              <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
                <p className="text-sm text-zinc-600">No recent activity</p>
              </div>
            ) : (
              <AdminTable>
                <thead >
                  <tr>
                    <th >Location</th>
                    <th >Type</th>
                    <th >Status</th>
                    <th className="text-right">New</th>
                    <th className="text-right">Updated</th>
                    <th className="text-right">Alerts</th>
                    <th >When</th>
                  </tr>
                </thead>
                <tbody >
                  {activity.map((log) => (
                    <tr key={log.id} className="text-zinc-300">
                      <td className="text-zinc-200">{log.location_name || '—'}</td>
                      <td className="text-zinc-500">{log.check_type}</td>
                      <td >
                        <span className={`text-[11px] ${log.status === 'completed' ? 'text-emerald-400' : log.status === 'failed' ? 'text-red-400' : 'text-zinc-400'}`}>
                          {log.status}
                        </span>
                      </td>
                      <td className="text-right text-zinc-400">{log.new_count || 0}</td>
                      <td className="text-right text-zinc-400">{log.updated_count || 0}</td>
                      <td className="text-right text-zinc-400">{log.alert_count || 0}</td>
                      <td className="text-zinc-500">{fmtRelative(log.started_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </AdminTable>
            )}
          </div>
        )}
      </div>
    </AdminWorkspace>
  )
}
