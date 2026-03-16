import { useEffect, useState, useCallback } from 'react'
import type { FormEvent } from 'react'
import { api } from '../../api/client'
import { Button, Input, Modal } from '../../components/ui'
import { categoryLabel } from '../../types/compliance'
import type { RequirementCategory } from '../../types/compliance'

// --- Types ---
type BusinessLocation = {
  id: string; name: string | null; city: string; state: string
  requirements_count: number; unread_alerts_count: number
  employee_count: number; data_status: string; created_at: string
}
type ComplianceRequirement = {
  id: string; category: string; jurisdiction_level: string; jurisdiction_name: string
  title: string; description: string | null; current_value: string | null
  effective_date: string | null; is_pinned: boolean
}
type ComplianceAlert = {
  id: string; alert_type: string; title: string; message: string
  severity: string; status: string; created_at: string
}
type ComplianceSummary = {
  total_locations: number; total_requirements: number
  unread_alerts: number; critical_alerts: number
}

type Tab = 'overview' | 'locations' | 'alerts'

const SUMMARY_LABELS = ['Locations', 'Requirements', 'Unread Alerts', 'Critical'] as const
const summaryKeys: Record<typeof SUMMARY_LABELS[number], keyof ComplianceSummary> = {
  Locations: 'total_locations', Requirements: 'total_requirements',
  'Unread Alerts': 'unread_alerts', Critical: 'critical_alerts',
}

function getCategoryLabel(cat: string): string {
  return categoryLabel[cat as RequirementCategory] ?? cat
}

// --- Component ---
export default function Compliance() {
  const [tab, setTab] = useState<Tab>('overview')
  const [locations, setLocations] = useState<BusinessLocation[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [requirements, setRequirements] = useState<ComplianceRequirement[]>([])
  const [alerts, setAlerts] = useState<ComplianceAlert[]>([])
  const [pinnedReqs, setPinnedReqs] = useState<ComplianceRequirement[]>([])
  const [summary, setSummary] = useState<ComplianceSummary | null>(null)
  const [loadingLocs, setLoadingLocs] = useState(true)
  const [loadingReqs, setLoadingReqs] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [scanMessages, setScanMessages] = useState<string[]>([])
  const [showAddForm, setShowAddForm] = useState(false)
  const [addForm, setAddForm] = useState({ city: '', state: '', name: '' })
  const [saving, setSaving] = useState(false)

  const fetchAll = useCallback(async () => {
    try {
      const [locs, sum, al, pinned] = await Promise.all([
        api.get<BusinessLocation[]>('/compliance/locations'),
        api.get<ComplianceSummary>('/compliance/summary').catch(() => null),
        api.get<ComplianceAlert[]>('/compliance/alerts?status=unread').catch(() => []),
        api.get<ComplianceRequirement[]>('/compliance/pinned-requirements').catch(() => []),
      ])
      setLocations(locs); setSummary(sum); setAlerts(al); setPinnedReqs(pinned)
    } catch { setLocations([]) }
    finally { setLoadingLocs(false) }
  }, [])

  useEffect(() => { fetchAll() }, [fetchAll])

  const fetchRequirements = useCallback(async (locId: string) => {
    setLoadingReqs(true)
    try { setRequirements(await api.get<ComplianceRequirement[]>(`/compliance/locations/${locId}/requirements`)) }
    catch { setRequirements([]) }
    finally { setLoadingReqs(false) }
  }, [])

  useEffect(() => {
    if (selectedId) fetchRequirements(selectedId); else setRequirements([])
  }, [selectedId, fetchRequirements])

  async function handleAddLocation(e: FormEvent) {
    e.preventDefault(); setSaving(true)
    try {
      await api.post<BusinessLocation>('/compliance/locations', {
        city: addForm.city, state: addForm.state, name: addForm.name || null,
      })
      setAddForm({ city: '', state: '', name: '' }); setShowAddForm(false); fetchAll()
    } finally { setSaving(false) }
  }

  async function togglePin(req: ComplianceRequirement) {
    await api.post(`/compliance/requirements/${req.id}/pin`, { is_pinned: !req.is_pinned })
    setRequirements((prev) => prev.map((r) => (r.id === req.id ? { ...r, is_pinned: !r.is_pinned } : r)))
  }

  async function handleAlertAction(alertId: string, action: 'read' | 'dismiss') {
    await api.put(`/compliance/alerts/${alertId}/${action === 'read' ? 'read' : 'dismiss'}`)
    setAlerts((prev) => prev.filter((a) => a.id !== alertId))
    if (summary) setSummary({ ...summary, unread_alerts: Math.max(0, summary.unread_alerts - 1) })
  }

  function startComplianceCheck(locationId: string) {
    setScanning(true); setScanMessages([])
    const token = localStorage.getItem('matcha_access_token')
    const base = import.meta.env.VITE_API_URL || '/api'
    fetch(`${base}/compliance/locations/${locationId}/check`, {
      method: 'POST', headers: { Authorization: `Bearer ${token}` },
    }).then(async (res) => {
      const reader = res.body?.getReader()
      const decoder = new TextDecoder()
      if (!reader) return
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        for (const line of decoder.decode(value).split('\n')) {
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6)
          if (data === '[DONE]') { setScanning(false); fetchRequirements(locationId); fetchAll(); return }
          try { const ev = JSON.parse(data); if (ev.message) setScanMessages((p) => [...p, ev.message]) } catch {}
        }
      }
      setScanning(false)
    }).catch(() => setScanning(false))
  }

  // Group requirements by category, pinned items first within each group
  const groupedReqs = requirements.reduce<Record<string, ComplianceRequirement[]>>((acc, req) => {
    if (!acc[req.category]) acc[req.category] = []
    acc[req.category].push(req)
    return acc
  }, {})
  Object.values(groupedReqs).forEach((group) =>
    group.sort((a, b) => (b.is_pinned ? 1 : 0) - (a.is_pinned ? 1 : 0))
  )

  const selectedLoc = locations.find((l) => l.id === selectedId)
  const criticalAlerts = alerts.filter((a) => a.severity === 'critical').slice(0, 3)
  const topAlerts = criticalAlerts.length > 0 ? criticalAlerts : alerts.slice(0, 3)

  if (loadingLocs) return <p className="text-sm text-zinc-500">Loading...</p>

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk]">Compliance</h1>
          <p className="mt-1 text-sm text-zinc-500">Jurisdictional requirements, alerts, and location management.</p>
        </div>
      </div>

      {/* Tab nav */}
      <div className="flex items-center gap-1 mt-4 mb-5">
        {(['overview', 'locations', 'alerts'] as const).map((t) => (
          <Button
            key={t}
            variant={tab === t ? 'secondary' : 'ghost'}
            size="sm"
            onClick={() => setTab(t)}
          >
            {t === 'overview' ? 'Overview' : t === 'locations' ? 'Locations' : `Alerts${alerts.length > 0 ? ` (${alerts.length})` : ''}`}
          </Button>
        ))}
      </div>

      {/* ── Tab: Overview ── */}
      {tab === 'overview' && (
        <div className="space-y-5">
          {/* Summary stats */}
          {summary && (
            <div className="grid gap-3 grid-cols-4">
              {SUMMARY_LABELS.map((label) => (
                <div key={label} className="border border-zinc-800 rounded-lg px-3 py-3 text-center">
                  <p className="text-xl font-semibold text-zinc-100">{summary[summaryKeys[label]]}</p>
                  <p className="text-[11px] text-zinc-500 uppercase tracking-wide mt-0.5">{label}</p>
                </div>
              ))}
            </div>
          )}

          {/* Critical alerts */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Recent Alerts</h2>
              {alerts.length > 3 && (
                <button type="button" onClick={() => setTab('alerts')}
                  className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors">
                  View all alerts →
                </button>
              )}
            </div>
            {topAlerts.length === 0 ? (
              <div className="border border-zinc-800 rounded-lg px-4 py-4">
                <p className="text-sm text-zinc-600">No unread alerts</p>
              </div>
            ) : (
              <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
                {topAlerts.map((alert) => (
                  <div key={alert.id} className="px-4 py-2.5">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm text-zinc-200">{alert.title}</p>
                      <span className={`text-[11px] shrink-0 ${alert.severity === 'critical' ? 'text-red-400' : alert.severity === 'warning' ? 'text-amber-400' : 'text-zinc-500'}`}>
                        {alert.severity}
                      </span>
                    </div>
                    <p className="text-xs text-zinc-500 mt-0.5 line-clamp-2">{alert.message}</p>
                    <div className="flex items-center justify-between mt-1.5">
                      <span className="text-[11px] text-zinc-600">{new Date(alert.created_at).toLocaleDateString()}</span>
                      <div className="flex gap-1">
                        <button type="button" onClick={() => handleAlertAction(alert.id, 'read')}
                          className="text-xs text-zinc-600 hover:text-zinc-300 px-1.5 py-0.5 transition-colors">Mark Read</button>
                        <button type="button" onClick={() => handleAlertAction(alert.id, 'dismiss')}
                          className="text-xs text-zinc-600 hover:text-zinc-300 px-1.5 py-0.5 transition-colors">Dismiss</button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Pinned requirements */}
          <div>
            <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Pinned Requirements</h2>
            {pinnedReqs.length === 0 ? (
              <div className="border border-zinc-800 rounded-lg px-4 py-4">
                <p className="text-sm text-zinc-600">
                  {alerts.length === 0 && pinnedReqs.length === 0
                    ? 'All clear — no alerts or pinned requirements.'
                    : 'No pinned requirements. Pin requirements in the Locations tab.'}
                </p>
              </div>
            ) : (
              <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
                {pinnedReqs.map((req) => (
                  <div key={req.id} className="flex items-start gap-3 px-4 py-2.5">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-zinc-200">{req.title}</p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-[11px] text-zinc-500">{req.jurisdiction_name}</span>
                        <span className="text-[11px] text-zinc-600">{getCategoryLabel(req.category)}</span>
                        {req.current_value && <span className="text-[11px] text-zinc-500">{req.current_value}</span>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Tab: Locations ── */}
      {tab === 'locations' && (
        <div className="grid grid-cols-3 gap-4">
          {/* Left: location list */}
          <div className="col-span-1">
            <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Locations</h2>
            <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
              {locations.length === 0 && (
                <p className="px-4 py-3 text-sm text-zinc-600">No locations added yet.</p>
              )}
              {locations.map((loc) => (
                <button key={loc.id} type="button"
                  onClick={() => setSelectedId(loc.id === selectedId ? null : loc.id)}
                  className={`w-full flex items-center justify-between px-3 py-2.5 text-left transition-colors border-l-2 ${
                    loc.id === selectedId
                      ? 'bg-zinc-800/60 border-zinc-300'
                      : 'hover:bg-zinc-800/30 border-transparent'
                  }`}>
                  <div className="min-w-0">
                    <p className="text-sm text-zinc-200 truncate">
                      {loc.city}, {loc.state}
                      {loc.name && <span className="text-zinc-500 ml-1.5">({loc.name})</span>}
                    </p>
                    <p className="text-[11px] text-zinc-500 mt-0.5">{loc.requirements_count} requirements</p>
                  </div>
                  {loc.unread_alerts_count > 0 && (
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0 ml-2" />
                  )}
                </button>
              ))}
            </div>
            <div className="mt-2">
              <Button variant="ghost" size="sm" onClick={() => setShowAddForm(true)}>+ Add Location</Button>
            </div>
          </div>

          {/* Right: selected location detail */}
          <div className="col-span-2">
            {!selectedId ? (
              <div className="flex items-center justify-center h-40 border border-zinc-800 rounded-lg">
                <p className="text-sm text-zinc-600">Select a location to view requirements</p>
              </div>
            ) : (
              <div>
                {/* Location header */}
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h2 className="text-base font-medium text-zinc-100">
                      {selectedLoc?.city}, {selectedLoc?.state}
                      {selectedLoc?.name && <span className="text-zinc-500 ml-2 text-sm">({selectedLoc.name})</span>}
                    </h2>
                    {selectedLoc && (
                      <p className="text-[11px] text-zinc-500 mt-0.5">{selectedLoc.employee_count} employees</p>
                    )}
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={scanning}
                    onClick={() => startComplianceCheck(selectedId)}
                  >
                    {scanning ? 'Scanning...' : 'Run Compliance Check'}
                  </Button>
                </div>

                {/* SSE scan progress */}
                {scanning && scanMessages.length > 0 && (
                  <div className="border border-zinc-800 rounded-lg px-3 py-2.5 mb-3 max-h-28 overflow-y-auto">
                    {scanMessages.map((msg, i) => (
                      <p key={i} className="text-xs text-zinc-500 leading-5">{msg}</p>
                    ))}
                  </div>
                )}

                {/* Requirements grouped by category */}
                {loadingReqs ? (
                  <p className="text-sm text-zinc-600">Loading requirements...</p>
                ) : Object.keys(groupedReqs).length === 0 ? (
                  <div className="border border-zinc-800 rounded-lg px-4 py-6 text-center">
                    <p className="text-sm text-zinc-600">No requirements found. Run a compliance check to populate.</p>
                  </div>
                ) : (
                  <div className="border border-zinc-800 rounded-lg">
                    {Object.entries(groupedReqs).map(([cat, reqs], catIdx) => (
                      <div key={cat}>
                        {catIdx > 0 && <div className="border-t border-zinc-800/60" />}
                        <div className="px-4 pt-3 pb-1">
                          <p className="text-xs uppercase tracking-wide text-zinc-400">{getCategoryLabel(cat)}</p>
                        </div>
                        {reqs.map((req) => (
                          <div key={req.id} className="flex items-start gap-3 px-4 py-2 border-t border-zinc-800/40 first:border-t-0">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                {req.is_pinned && <span className="text-[10px] text-zinc-500">📌</span>}
                                <p className="text-sm text-zinc-200">{req.title}</p>
                              </div>
                              <div className="flex items-center gap-2 mt-0.5">
                                <span className="text-[11px] text-zinc-500">{req.jurisdiction_level}</span>
                                <span className="text-[11px] text-zinc-600">·</span>
                                <span className="text-[11px] text-zinc-500">{req.jurisdiction_name}</span>
                                {req.current_value && (
                                  <>
                                    <span className="text-[11px] text-zinc-600">·</span>
                                    <span className="text-[11px] text-zinc-400">{req.current_value}</span>
                                  </>
                                )}
                                {req.effective_date && (
                                  <span className="text-[11px] text-zinc-600">eff. {req.effective_date}</span>
                                )}
                              </div>
                            </div>
                            <button type="button" onClick={() => togglePin(req)}
                              className="text-xs text-zinc-600 hover:text-zinc-300 px-2 py-1 transition-colors shrink-0">
                              {req.is_pinned ? 'Unpin' : 'Pin'}
                            </button>
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Tab: Alerts ── */}
      {tab === 'alerts' && (
        <div>
          <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Unread Alerts</h2>
          {alerts.length === 0 ? (
            <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
              <p className="text-sm text-zinc-600">No unread alerts</p>
            </div>
          ) : (
            <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
              {alerts.map((alert) => (
                <div key={alert.id} className="px-4 py-3">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-medium text-zinc-200">{alert.title}</p>
                    <span className={`text-[11px] shrink-0 ${alert.severity === 'critical' ? 'text-red-400' : alert.severity === 'warning' ? 'text-amber-400' : 'text-zinc-500'}`}>
                      {alert.severity}
                    </span>
                  </div>
                  <p className="text-xs text-zinc-400 mt-1 leading-5">{alert.message}</p>
                  <div className="flex items-center justify-between mt-2">
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] text-zinc-600">{alert.alert_type.replace(/_/g, ' ')}</span>
                      <span className="text-[11px] text-zinc-700">·</span>
                      <span className="text-[11px] text-zinc-600">{new Date(alert.created_at).toLocaleDateString()}</span>
                    </div>
                    <div className="flex gap-1">
                      <button type="button" onClick={() => handleAlertAction(alert.id, 'read')}
                        className="text-xs text-zinc-600 hover:text-zinc-300 px-2 py-1 transition-colors">Mark Read</button>
                      <button type="button" onClick={() => handleAlertAction(alert.id, 'dismiss')}
                        className="text-xs text-zinc-600 hover:text-zinc-300 px-2 py-1 transition-colors">Dismiss</button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Add Location modal */}
      <Modal open={showAddForm} onClose={() => setShowAddForm(false)} title="Add Location" width="sm">
        <form onSubmit={handleAddLocation} className="space-y-3">
          <Input id="city" label="City" required value={addForm.city}
            onChange={(e) => setAddForm({ ...addForm, city: e.target.value })} placeholder="e.g. San Francisco" />
          <Input id="state" label="State (2-letter)" required value={addForm.state} maxLength={2}
            onChange={(e) => setAddForm({ ...addForm, state: e.target.value.toUpperCase() })} placeholder="e.g. CA" />
          <Input id="loc-name" label="Name (optional)" value={addForm.name}
            onChange={(e) => setAddForm({ ...addForm, name: e.target.value })} placeholder="e.g. HQ Office" />
          <div className="pt-1">
            <Button type="submit" disabled={saving} size="sm">{saving ? 'Adding...' : 'Add Location'}</Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
