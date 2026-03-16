import { useEffect, useState, useCallback } from 'react'
import type { FormEvent } from 'react'
import { api } from '../../api/client'
import { Button, Input, Modal } from '../../components/ui'
import JurisdictionDetailPanel from '../../components/admin/JurisdictionDetailPanel'

// ── Types ──────────────────────────────────────────────────────────────────────

type Jurisdiction = {
  id: string
  city: string
  state: string
  county: string | null
  parent_id: string | null
  parent_city: string | null
  parent_state: string | null
  children_count: number
  requirement_count: number
  legislation_count: number
  location_count: number
  auto_check_count: number
  inherits_from_parent: boolean
  last_verified_at: string | null
  created_at: string | null
}

type ListResponse = {
  jurisdictions: Jurisdiction[]
  totals: { total_jurisdictions: number; total_requirements: number; total_legislation: number }
}

type ResearchItem = {
  jurisdiction_id: string
  city: string
  state: string
  county: string | null
  repo_count: number
  location_count: number
  company_count: number
  status: string
  created_at: string | null
}

type CoverageRequest = {
  id: string
  city: string
  state: string
  county: string | null
  status: string
  company_name: string
  employee_count: number
  admin_notes: string | null
  created_at: string | null
}

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

type Tab = 'jurisdictions' | 'research_queue' | 'coverage_requests' | 'activity' | 'jobs'

function fmtDate(d: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString()
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

// ── Component ──────────────────────────────────────────────────────────────────

export default function Jurisdictions() {
  const [tab, setTab] = useState<Tab>('jurisdictions')

  // Jurisdictions list
  const [jurisdictions, setJurisdictions] = useState<Jurisdiction[]>([])
  const [totals, setTotals] = useState<ListResponse['totals'] | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [stateFilter, setStateFilter] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [showAddForm, setShowAddForm] = useState(false)
  const [addForm, setAddForm] = useState({ city: '', state: '', county: '' })
  const [saving, setSaving] = useState(false)
  const [cleaning, setCleaning] = useState(false)

  // Research queue
  const [researchQueue, setResearchQueue] = useState<ResearchItem[]>([])
  const [loadingResearch, setLoadingResearch] = useState(false)
  const [researchingId, setResearchingId] = useState<string | null>(null)
  const [researchMessages, setResearchMessages] = useState<string[]>([])

  // Coverage requests
  const [requests, setRequests] = useState<CoverageRequest[]>([])
  const [loadingRequests, setLoadingRequests] = useState(false)

  // Activity
  const [activity, setActivity] = useState<ActivityLog[]>([])
  const [activityStats, setActivityStats] = useState<{ checks_24h: number; failed_24h: number } | null>(null)
  const [loadingActivity, setLoadingActivity] = useState(false)

  // Schedulers
  const [schedulers, setSchedulers] = useState<SchedulerSetting[]>([])
  const [loadingJobs, setLoadingJobs] = useState(false)
  const [triggeringKey, setTriggeringKey] = useState<string | null>(null)

  // ── Fetchers ──

  const fetchJurisdictions = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.get<ListResponse>('/admin/jurisdictions')
      setJurisdictions(res.jurisdictions); setTotals(res.totals)
    } catch { setJurisdictions([]) }
    finally { setLoading(false) }
  }, [])

  const fetchResearchQueue = useCallback(async () => {
    setLoadingResearch(true)
    try { setResearchQueue(await api.get<ResearchItem[]>('/admin/research-queue')) }
    catch { setResearchQueue([]) }
    finally { setLoadingResearch(false) }
  }, [])

  const fetchRequests = useCallback(async () => {
    setLoadingRequests(true)
    try { setRequests(await api.get<CoverageRequest[]>('/admin/jurisdiction-requests?status=pending')) }
    catch { setRequests([]) }
    finally { setLoadingRequests(false) }
  }, [])

  const fetchActivity = useCallback(async () => {
    setLoadingActivity(true)
    try {
      const data = await api.get<{ overview: { checks_24h: number; failed_24h: number }; recent_logs: ActivityLog[] }>('/admin/schedulers/stats')
      setActivity(data.recent_logs); setActivityStats(data.overview)
    } catch { setActivity([]) }
    finally { setLoadingActivity(false) }
  }, [])

  const fetchJobs = useCallback(async () => {
    setLoadingJobs(true)
    try { setSchedulers(await api.get<SchedulerSetting[]>('/admin/schedulers')) }
    catch { setSchedulers([]) }
    finally { setLoadingJobs(false) }
  }, [])

  useEffect(() => { fetchJurisdictions() }, [fetchJurisdictions])

  useEffect(() => {
    if (tab === 'research_queue' && researchQueue.length === 0) fetchResearchQueue()
    if (tab === 'coverage_requests' && requests.length === 0) fetchRequests()
    if (tab === 'activity' && activity.length === 0) fetchActivity()
    if (tab === 'jobs' && schedulers.length === 0) fetchJobs()
  }, [tab, researchQueue.length, requests.length, activity.length, schedulers.length, fetchResearchQueue, fetchRequests, fetchActivity, fetchJobs])

  // ── Actions ──

  async function handleAdd(e: FormEvent) {
    e.preventDefault(); setSaving(true)
    try {
      await api.post('/admin/jurisdictions', {
        city: addForm.city.trim(), state: addForm.state.trim().toUpperCase(), county: addForm.county.trim() || null,
      })
      setAddForm({ city: '', state: '', county: '' }); setShowAddForm(false); fetchJurisdictions()
    } finally { setSaving(false) }
  }

  async function handleDelete(id: string, city: string, state: string) {
    if (!confirm(`Delete ${city}, ${state}? This removes all requirements and legislation.`)) return
    await api.delete(`/admin/jurisdictions/${id}`)
    setJurisdictions((prev) => prev.filter((j) => j.id !== id))
    if (selectedId === id) setSelectedId(null)
  }

  async function handleCleanup() {
    if (!confirm('Run duplicate cleanup? This merges duplicate rows. Cannot be undone.')) return
    setCleaning(true)
    try { await api.post('/admin/jurisdictions/cleanup-duplicates', {}); fetchJurisdictions() }
    finally { setCleaning(false) }
  }

  function startResearch(item: ResearchItem) {
    setResearchingId(item.jurisdiction_id); setResearchMessages([])
    const token = localStorage.getItem('matcha_access_token')
    const base = import.meta.env.VITE_API_URL || '/api'
    fetch(`${base}/admin/research-queue/${item.jurisdiction_id}/research`, {
      method: 'POST', headers: { Authorization: `Bearer ${token}` },
    }).then(async (res) => {
      const reader = res.body?.getReader()
      const decoder = new TextDecoder()
      if (!reader) return
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        for (const line of decoder.decode(value).split('\n')) {
          if (line.startsWith(': ')) continue
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6)
          if (data === '[DONE]') { setResearchingId(null); fetchResearchQueue(); return }
          try {
            const ev = JSON.parse(data)
            if (ev.type === 'error') { setResearchMessages((p) => [...p, `Error: ${ev.message}`]); setResearchingId(null); return }
            if (ev.message) setResearchMessages((p) => [...p, ev.message])
          } catch {}
        }
      }
      setResearchingId(null)
    }).catch(() => setResearchingId(null))
  }

  async function processRequest(req: CoverageRequest) {
    await api.post(`/admin/jurisdiction-requests/${req.id}/process`, {
      has_local_ordinance: false, county: req.county || null, admin_notes: null,
    })
    setRequests((prev) => prev.filter((r) => r.id !== req.id))
  }

  async function dismissRequest(id: string) {
    await api.post(`/admin/jurisdiction-requests/${id}/dismiss`, {})
    setRequests((prev) => prev.filter((r) => r.id !== id))
  }

  async function toggleScheduler(taskKey: string, currentEnabled: boolean) {
    await api.patch(`/admin/schedulers/${taskKey}`, { enabled: !currentEnabled })
    setSchedulers((prev) => prev.map((s) => s.task_key === taskKey ? { ...s, enabled: !s.enabled } : s))
  }

  async function triggerScheduler(taskKey: string) {
    setTriggeringKey(taskKey)
    try { await api.post(`/admin/schedulers/${taskKey}/trigger`, {}) }
    finally { setTriggeringKey(null) }
  }

  // ── Derived data ──

  const states = [...new Set(jurisdictions.map((j) => j.state))].sort()
  const filtered = jurisdictions.filter((j) => {
    const q = search.toLowerCase()
    const matchesSearch = !search || j.city.toLowerCase().includes(q) || j.state.toLowerCase().includes(q)
    return matchesSearch && (!stateFilter || j.state === stateFilter)
  })
  const selectedJurisdiction = jurisdictions.find((j) => j.id === selectedId) ?? null
  const needsResearchCount = researchQueue.filter((r) => r.status === 'needs_research').length
  const pendingRequestCount = requests.filter((r) => r.status === 'pending').length

  const tabItems: { id: Tab; label: string; count?: number }[] = [
    { id: 'jurisdictions', label: 'Jurisdictions', count: jurisdictions.length },
    { id: 'research_queue', label: 'Research Queue', count: needsResearchCount || undefined },
    { id: 'coverage_requests', label: 'Coverage Requests', count: pendingRequestCount || undefined },
    { id: 'activity', label: 'Recent Activity' },
    { id: 'jobs', label: 'Scheduled Jobs', count: schedulers.length || undefined },
  ]

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk]">Jurisdictions</h1>
          <p className="mt-1 text-sm text-zinc-500">Manage the jurisdiction registry — add, research, and remove entries.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" disabled={cleaning} onClick={handleCleanup}>
            {cleaning ? 'Cleaning...' : 'Cleanup Duplicates'}
          </Button>
          <Button variant="secondary" size="sm" onClick={() => setShowAddForm(true)}>+ Add</Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 mt-4 mb-5">
        {tabItems.map((t) => (
          <Button key={t.id} variant={tab === t.id ? 'secondary' : 'ghost'} size="sm" onClick={() => setTab(t.id)}>
            {t.label}{t.count !== undefined ? ` (${t.count})` : ''}
          </Button>
        ))}
      </div>

      {/* ── Jurisdictions ── */}
      {tab === 'jurisdictions' && (
        <>
          {/* Totals */}
          {totals && (
            <div className="grid grid-cols-3 gap-3 mb-4">
              {[
                { label: 'Jurisdictions', value: totals.total_jurisdictions },
                { label: 'Requirements', value: totals.total_requirements },
                { label: 'Legislation', value: totals.total_legislation },
              ].map((s) => (
                <div key={s.label} className="border border-zinc-800 rounded-lg px-4 py-3 text-center">
                  <p className="text-xl font-semibold text-zinc-100">{s.value}</p>
                  <p className="text-[11px] text-zinc-500 uppercase tracking-wide mt-0.5">{s.label}</p>
                </div>
              ))}
            </div>
          )}

          {/* Filters */}
          <div className="flex items-center gap-3 mb-4">
            <Input label="" placeholder="Search city or state..." value={search}
              onChange={(e) => setSearch(e.target.value)} className="max-w-xs" />
            <div className="flex gap-1 overflow-x-auto">
              <Button variant={!stateFilter ? 'secondary' : 'ghost'} size="sm" onClick={() => setStateFilter('')}>All</Button>
              {states.map((s) => (
                <Button key={s} variant={stateFilter === s ? 'secondary' : 'ghost'} size="sm" onClick={() => setStateFilter(s)}>
                  {s}
                </Button>
              ))}
            </div>
          </div>

          {/* List + detail */}
          <div className={selectedId ? 'grid grid-cols-5 gap-4' : ''}>
            <div className={selectedId ? 'col-span-2' : ''}>
              {loading ? (
                <p className="text-sm text-zinc-500">Loading...</p>
              ) : filtered.length === 0 ? (
                <p className="text-sm text-zinc-600">No jurisdictions found.</p>
              ) : (
                <div className="border border-zinc-800 rounded-lg overflow-hidden">
                  <div className="max-h-[65vh] overflow-y-auto">
                    <table className="w-full text-sm text-left">
                      <thead className="bg-zinc-900/50 text-zinc-400 sticky top-0">
                        <tr>
                          <th className="px-3 py-2.5 font-medium">City / State</th>
                          {!selectedId && <th className="px-3 py-2.5 font-medium text-right">Reqs</th>}
                          {!selectedId && <th className="px-3 py-2.5 font-medium text-right">Leg.</th>}
                          {!selectedId && <th className="px-3 py-2.5 font-medium text-right">Locs</th>}
                          {!selectedId && <th className="px-3 py-2.5 font-medium">Verified</th>}
                          <th className="px-3 py-2.5 font-medium text-right" />
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800">
                        {filtered.map((j) => (
                          <tr key={j.id}
                            onClick={() => setSelectedId(j.id === selectedId ? null : j.id)}
                            className={`cursor-pointer transition-colors ${j.id === selectedId ? 'bg-zinc-800/60' : 'hover:bg-zinc-800/30'}`}>
                            <td className="px-3 py-2.5">
                              <div className="flex items-center gap-1.5">
                                {j.inherits_from_parent && <span className="text-[10px] text-zinc-600" title="Inherits">↑</span>}
                                <div>
                                  <p className="text-zinc-200 font-medium">{j.city}, {j.state}</p>
                                  {j.county && <p className="text-[11px] text-zinc-600">{j.county} County</p>}
                                  {j.parent_city && <p className="text-[11px] text-zinc-600">↳ {j.parent_city}, {j.parent_state}</p>}
                                </div>
                              </div>
                            </td>
                            {!selectedId && <td className="px-3 py-2.5 text-right text-zinc-400">{j.requirement_count}</td>}
                            {!selectedId && <td className="px-3 py-2.5 text-right text-zinc-400">{j.legislation_count}</td>}
                            {!selectedId && <td className="px-3 py-2.5 text-right text-zinc-400">{j.location_count}</td>}
                            {!selectedId && <td className="px-3 py-2.5 text-zinc-500 text-[11px]">{fmtDate(j.last_verified_at)}</td>}
                            <td className="px-3 py-2.5 text-right">
                              <button type="button" onClick={(e) => { e.stopPropagation(); handleDelete(j.id, j.city, j.state) }}
                                className="text-xs text-zinc-600 hover:text-red-400 px-1.5 py-0.5 transition-colors">Delete</button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>

            {selectedId && selectedJurisdiction && (
              <div className="col-span-3">
                <JurisdictionDetailPanel
                  id={selectedId}
                  city={selectedJurisdiction.city}
                  state={selectedJurisdiction.state}
                  onCheckComplete={fetchJurisdictions}
                />
              </div>
            )}
          </div>
        </>
      )}

      {/* ── Research Queue ── */}
      {tab === 'research_queue' && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
              Research Queue {needsResearchCount > 0 && <span className="text-zinc-500">· {needsResearchCount} need research</span>}
            </h2>
            <Button variant="ghost" size="sm" onClick={fetchResearchQueue}>Refresh</Button>
          </div>

          {/* SSE progress */}
          {researchingId && researchMessages.length > 0 && (
            <div className="border border-zinc-800 rounded-lg px-3 py-2.5 mb-3 max-h-28 overflow-y-auto">
              {researchMessages.map((msg, i) => (
                <p key={i} className="text-xs text-zinc-500 leading-5">{msg}</p>
              ))}
            </div>
          )}

          {loadingResearch ? (
            <p className="text-sm text-zinc-500">Loading...</p>
          ) : researchQueue.length === 0 ? (
            <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
              <p className="text-sm text-zinc-600">Research queue is empty.</p>
            </div>
          ) : (
            <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60 max-h-[70vh] overflow-y-auto">
              {researchQueue.map((item) => (
                <div key={item.jurisdiction_id} className="flex items-center gap-4 px-4 py-2.5">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-zinc-200">{item.city}, {item.state}</p>
                    <div className="flex items-center gap-3 mt-0.5">
                      <span className={`text-[11px] ${item.status === 'needs_research' ? 'text-amber-400/70' : 'text-zinc-500'}`}>
                        {item.status === 'needs_research' ? 'Needs research' : 'Researched'}
                      </span>
                      <span className="text-[11px] text-zinc-600">{item.repo_count} reqs</span>
                      <span className="text-[11px] text-zinc-600">{item.location_count} locs · {item.company_count} companies</span>
                    </div>
                  </div>
                  {item.status === 'needs_research' && (
                    <Button variant="secondary" size="sm"
                      disabled={researchingId !== null}
                      onClick={() => startResearch(item)}>
                      {researchingId === item.jurisdiction_id ? 'Researching...' : 'Research'}
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Coverage Requests ── */}
      {tab === 'coverage_requests' && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Pending Coverage Requests</h2>
            <Button variant="ghost" size="sm" onClick={fetchRequests}>Refresh</Button>
          </div>

          {loadingRequests ? (
            <p className="text-sm text-zinc-500">Loading...</p>
          ) : requests.length === 0 ? (
            <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
              <p className="text-sm text-zinc-600">No pending requests</p>
            </div>
          ) : (
            <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
              {requests.map((req) => (
                <div key={req.id} className="flex items-center gap-4 px-4 py-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-zinc-200">
                      {req.city}, {req.state}
                      {req.county && <span className="text-zinc-500 ml-1.5">({req.county} County)</span>}
                    </p>
                    <div className="flex items-center gap-3 mt-0.5">
                      <span className="text-[11px] text-zinc-500">{req.company_name}</span>
                      <span className="text-[11px] text-zinc-600">·</span>
                      <span className="text-[11px] text-zinc-500">{req.employee_count} employees</span>
                      {req.created_at && (
                        <>
                          <span className="text-[11px] text-zinc-600">·</span>
                          <span className="text-[11px] text-zinc-600">{fmtDate(req.created_at)}</span>
                        </>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Button variant="secondary" size="sm" onClick={() => processRequest(req)}>Process</Button>
                    <button type="button" onClick={() => dismissRequest(req.id)}
                      className="text-xs text-zinc-600 hover:text-zinc-300 px-2 py-1 transition-colors">Dismiss</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Recent Activity ── */}
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
            <div className="border border-zinc-800 rounded-lg overflow-hidden">
              <table className="w-full text-sm text-left">
                <thead className="bg-zinc-900/50 text-zinc-400">
                  <tr>
                    <th className="px-3 py-2.5 font-medium">Location</th>
                    <th className="px-3 py-2.5 font-medium">Type</th>
                    <th className="px-3 py-2.5 font-medium">Status</th>
                    <th className="px-3 py-2.5 font-medium text-right">New</th>
                    <th className="px-3 py-2.5 font-medium text-right">Updated</th>
                    <th className="px-3 py-2.5 font-medium text-right">Alerts</th>
                    <th className="px-3 py-2.5 font-medium">When</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800">
                  {activity.map((log) => (
                    <tr key={log.id} className="text-zinc-300">
                      <td className="px-3 py-2.5 text-zinc-200">{log.location_name || '—'}</td>
                      <td className="px-3 py-2.5 text-zinc-500 text-[11px]">{log.check_type}</td>
                      <td className="px-3 py-2.5">
                        <span className={`text-[11px] ${log.status === 'completed' ? 'text-emerald-400' : log.status === 'failed' ? 'text-red-400' : 'text-zinc-400'}`}>
                          {log.status}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 text-right text-zinc-400">{log.new_count || 0}</td>
                      <td className="px-3 py-2.5 text-right text-zinc-400">{log.updated_count || 0}</td>
                      <td className="px-3 py-2.5 text-right text-zinc-400">{log.alert_count || 0}</td>
                      <td className="px-3 py-2.5 text-zinc-500 text-[11px]">{fmtRelative(log.started_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Scheduled Jobs ── */}
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

      {/* Add Jurisdiction modal */}
      <Modal open={showAddForm} onClose={() => setShowAddForm(false)} title="Add Jurisdiction" width="sm">
        <form onSubmit={handleAdd} className="space-y-3">
          <Input id="j-city" label="City" required value={addForm.city}
            onChange={(e) => setAddForm({ ...addForm, city: e.target.value })} placeholder="e.g. San Francisco" />
          <Input id="j-state" label="State (2-letter)" required value={addForm.state} maxLength={2}
            onChange={(e) => setAddForm({ ...addForm, state: e.target.value.toUpperCase() })} placeholder="e.g. CA" />
          <Input id="j-county" label="County (optional)" value={addForm.county}
            onChange={(e) => setAddForm({ ...addForm, county: e.target.value })} placeholder="e.g. San Francisco" />
          <div className="pt-1">
            <Button type="submit" disabled={saving} size="sm">{saving ? 'Adding...' : 'Add Jurisdiction'}</Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
