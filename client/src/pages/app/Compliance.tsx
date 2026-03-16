import { useEffect, useState, useCallback } from 'react'
import type { FormEvent } from 'react'
import { api } from '../../api/client'
import { Button, Input, Modal } from '../../components/ui'

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

const SUMMARY_LABELS = ['Locations', 'Requirements', 'Unread Alerts', 'Critical'] as const
const summaryKeys: Record<typeof SUMMARY_LABELS[number], keyof ComplianceSummary> = {
  Locations: 'total_locations', Requirements: 'total_requirements',
  'Unread Alerts': 'unread_alerts', Critical: 'critical_alerts',
}

// --- Component ---
export default function Compliance() {
  const [locations, setLocations] = useState<BusinessLocation[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [requirements, setRequirements] = useState<ComplianceRequirement[]>([])
  const [alerts, setAlerts] = useState<ComplianceAlert[]>([])
  const [summary, setSummary] = useState<ComplianceSummary | null>(null)
  const [loadingLocs, setLoadingLocs] = useState(true)
  const [loadingReqs, setLoadingReqs] = useState(false)
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null)
  const [scanning, setScanning] = useState(false)
  const [scanMessages, setScanMessages] = useState<string[]>([])
  const [showAddForm, setShowAddForm] = useState(false)
  const [addForm, setAddForm] = useState({ city: '', state: '', name: '' })
  const [saving, setSaving] = useState(false)

  const fetchLocations = useCallback(async () => {
    try {
      const [locs, sum, al] = await Promise.all([
        api.get<BusinessLocation[]>('/compliance/locations'),
        api.get<ComplianceSummary>('/compliance/summary').catch(() => null),
        api.get<ComplianceAlert[]>('/compliance/alerts?status=unread').catch(() => []),
      ])
      setLocations(locs); setSummary(sum); setAlerts(al)
    } catch { setLocations([]) }
    finally { setLoadingLocs(false) }
  }, [])

  useEffect(() => { fetchLocations() }, [fetchLocations])

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
      setAddForm({ city: '', state: '', name: '' }); setShowAddForm(false); fetchLocations()
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
          if (data === '[DONE]') { setScanning(false); fetchRequirements(locationId); fetchLocations(); return }
          try { const ev = JSON.parse(data); if (ev.message) setScanMessages((p) => [...p, ev.message]) } catch {}
        }
      }
      setScanning(false)
    }).catch(() => setScanning(false))
  }

  const categories = [...new Set(requirements.map((r) => r.category))].sort()
  const filtered = categoryFilter ? requirements.filter((r) => r.category === categoryFilter) : requirements
  const filterBtn = (active: boolean) => `shrink-0 px-2.5 py-1 rounded text-xs transition-colors ${active ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`

  if (loadingLocs) return <p className="text-sm text-zinc-500">Loading...</p>

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk]">Compliance</h1>
          <p className="mt-1 text-sm text-zinc-500">Jurisdictional requirements, alerts, and location management.</p>
        </div>
        <Button size="sm" onClick={() => setShowAddForm(true)}>Add Location</Button>
      </div>

      {summary && (
        <div className="mt-4 grid gap-3 grid-cols-4">
          {SUMMARY_LABELS.map((label) => (
            <div key={label} className="border border-zinc-800 rounded-lg px-3 py-3 text-center">
              <p className="text-xl font-semibold text-zinc-100">{summary[summaryKeys[label]]}</p>
              <p className="text-[11px] text-zinc-500 uppercase tracking-wide mt-0.5">{label}</p>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-3 gap-4 mt-5">
        <div className="col-span-2 space-y-4">
          <div>
            <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Locations</h2>
            <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
              {locations.length === 0 && <p className="px-4 py-3 text-sm text-zinc-600">No locations added yet.</p>}
              {locations.map((loc) => (
                <button key={loc.id} type="button" onClick={() => setSelectedId(loc.id === selectedId ? null : loc.id)}
                  className={`w-full flex items-center justify-between px-4 py-2.5 text-left transition-colors ${loc.id === selectedId ? 'bg-zinc-800/50' : 'hover:bg-zinc-800/30'}`}>
                  <p className="text-sm text-zinc-200">
                    {loc.city}, {loc.state}{loc.name && <span className="text-zinc-500 ml-1.5">({loc.name})</span>}
                  </p>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="text-[11px] text-zinc-500">{loc.requirements_count} reqs</span>
                    <span className="text-[11px] text-zinc-500">{loc.employee_count} emp</span>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {selectedId && (
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Requirements</h2>
                <button type="button" disabled={scanning} onClick={() => startComplianceCheck(selectedId)}
                  className="text-xs text-zinc-600 hover:text-zinc-300 transition-colors disabled:opacity-50">
                  {scanning ? 'Scanning...' : 'Run Compliance Check'}
                </button>
              </div>
              {scanning && scanMessages.length > 0 && (
                <div className="border border-zinc-800 rounded-lg px-3 py-2.5 mb-3 max-h-28 overflow-y-auto">
                  {scanMessages.map((msg, i) => <p key={i} className="text-xs text-zinc-500 leading-5">{msg}</p>)}
                </div>
              )}
              {categories.length > 0 && (
                <div className="flex gap-1.5 mb-3 overflow-x-auto pb-1">
                  <button type="button" onClick={() => setCategoryFilter(null)} className={filterBtn(!categoryFilter)}>All</button>
                  {categories.map((cat) => (
                    <button key={cat} type="button" onClick={() => setCategoryFilter(cat)} className={filterBtn(categoryFilter === cat)}>{cat}</button>
                  ))}
                </div>
              )}
              {loadingReqs ? <p className="text-sm text-zinc-600">Loading requirements...</p>
               : filtered.length === 0 ? <p className="text-sm text-zinc-600">No requirements found.</p>
               : (
                <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
                  {filtered.map((req) => (
                    <div key={req.id} className="flex items-start gap-3 px-4 py-2.5">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-zinc-200">{req.title}</p>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-[11px] text-zinc-500">{req.jurisdiction_name}</span>
                          {req.current_value && <span className="text-[11px] text-zinc-500">{req.current_value}</span>}
                          {req.effective_date && <span className="text-[11px] text-zinc-600">eff. {req.effective_date}</span>}
                        </div>
                      </div>
                      <button type="button" onClick={() => togglePin(req)}
                        className="text-xs text-zinc-600 hover:text-zinc-300 px-2 py-1 transition-colors shrink-0">
                        {req.is_pinned ? 'Unpin' : 'Pin'}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <div>
          <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Alerts</h2>
          {alerts.length === 0 ? (
            <div className="border border-zinc-800 rounded-lg px-4 py-6 text-center">
              <p className="text-sm text-zinc-600">No unread alerts</p>
            </div>
          ) : (
            <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
              {alerts.map((alert) => (
                <div key={alert.id} className="px-4 py-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm text-zinc-200">{alert.title}</p>
                    <span className="text-[11px] text-zinc-500 shrink-0">{alert.severity}</span>
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
      </div>

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
