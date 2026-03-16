import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import { Badge, Button, Input, Modal, Select, Textarea } from '../../components/ui'
import type {
  IRIncident, IRIncidentType, IRAnalyticsSummary, IRTrendPoint, IRLocationData,
  IRConsistencyAnalytics, IRWitness,
} from '../../types/ir'
import { typeLabel, statusLabel, severityLabel, SEVERITY_BADGE, STATUS_BADGE } from '../../types/ir'

// ── Constants ──

const INCIDENT_TYPE_OPTIONS = [
  { value: 'safety', label: 'Safety' },
  { value: 'behavioral', label: 'Behavioral' },
  { value: 'property', label: 'Property Damage' },
  { value: 'near_miss', label: 'Near Miss' },
  { value: 'other', label: 'Other' },
]

const SEVERITY_OPTIONS = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
]

type Tab = 'dashboard' | 'incidents' | 'analytics'
type SeverityFilter = 'all' | 'low' | 'medium' | 'high' | 'critical'
type StatusFilter = 'all' | 'needs_attention' | 'reported' | 'investigating' | 'action_required' | 'resolved' | 'closed'
type TypeFilter = 'all' | IRIncidentType

type IncidentListResponse = { incidents: IRIncident[]; total: number }

const EMPTY_FORM = {
  incident_type: 'safety' as IRIncidentType,
  title: '',
  description: '',
  severity: 'medium',
  location: '',
  date_occurred: '',
  reported_by_name: '',
  reported_by_email: '',
  // category-specific
  injured_person: '',
  body_parts: '',
  injury_type: '',
  treatment: '',
  osha_recordable: false,
  policy_violated: '',
  manager_notified: false,
  asset_damaged: '',
  estimated_cost: '',
  insurance_claim: false,
  potential_outcome: '',
  hazard_identified: '',
}

// ── Component ──

export default function IRList() {
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('incidents')

  // Incidents state
  const [incidents, setIncidents] = useState<IRIncident[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all')

  // Analytics / dashboard state
  const [summary, setSummary] = useState<IRAnalyticsSummary | null>(null)
  const [loadingSummary, setLoadingSummary] = useState(false)
  const [trends, setTrends] = useState<IRTrendPoint[]>([])
  const [locations, setLocations] = useState<IRLocationData[]>([])
  const [consistency, setConsistency] = useState<IRConsistencyAnalytics | null>(null)

  // Anonymous reporting
  const [anonStatus, setAnonStatus] = useState<{ enabled: boolean; link?: string } | null>(null)
  const [anonLoading, setAnonLoading] = useState(false)
  const [anonExpanded, setAnonExpanded] = useState(false)

  // Create form
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [witnesses, setWitnesses] = useState<{ name: string; contact: string }[]>([])
  const [saving, setSaving] = useState(false)

  // Fetch incidents
  useEffect(() => {
    setLoading(true)
    const params = new URLSearchParams()
    if (severityFilter !== 'all') params.set('severity', severityFilter)
    if (statusFilter === 'needs_attention') {
      params.set('status', 'reported,action_required')
    } else if (statusFilter !== 'all') {
      params.set('status', statusFilter)
    }
    if (typeFilter !== 'all') params.set('incident_type', typeFilter)
    params.set('limit', '100')
    const qs = params.toString()
    api.get<IncidentListResponse>(`/ir/incidents${qs ? `?${qs}` : ''}`)
      .then((res) => setIncidents(res.incidents))
      .catch(() => setIncidents([]))
      .finally(() => setLoading(false))
  }, [severityFilter, statusFilter, typeFilter])

  // Fetch summary
  useEffect(() => {
    setLoadingSummary(true)
    api.get<IRAnalyticsSummary>('/ir/incidents/analytics/summary')
      .then((res) => setSummary(res))
      .catch(() => setSummary(null))
      .finally(() => setLoadingSummary(false))
  }, [])

  // Fetch dashboard data
  useEffect(() => {
    if (tab === 'dashboard') {
      api.get<{ interval: string; data: IRTrendPoint[] }>('/ir/incidents/analytics/trends?interval=weekly&days=90')
        .then((res) => setTrends(res.data))
        .catch(() => setTrends([]))
      api.get<{ locations: IRLocationData[] }>('/ir/incidents/analytics/locations?limit=5')
        .then((res) => setLocations(res.locations ?? []))
        .catch(() => setLocations([]))
    }
  }, [tab])

  // Fetch consistency analytics
  useEffect(() => {
    if (tab === 'analytics') {
      api.get<IRConsistencyAnalytics>('/ir/incidents/analytics/consistency')
        .then((res) => setConsistency(res))
        .catch(() => setConsistency(null))
    }
  }, [tab])

  // Fetch anonymous reporting status
  useEffect(() => {
    if (anonExpanded && !anonStatus) {
      api.get<{ enabled: boolean; link?: string }>('/ir/incidents/anonymous-reporting/status')
        .then(setAnonStatus)
        .catch(() => setAnonStatus({ enabled: false }))
    }
  }, [anonExpanded, anonStatus])

  const filtered = incidents.filter(
    (inc) =>
      inc.title.toLowerCase().includes(search.toLowerCase()) ||
      inc.incident_number.toLowerCase().includes(search.toLowerCase()),
  )

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      const categoryData: Record<string, unknown> = {}
      if (form.incident_type === 'safety') {
        if (form.injured_person) categoryData.injured_person = form.injured_person
        if (form.body_parts) categoryData.body_parts = form.body_parts.split(',').map((s) => s.trim()).filter(Boolean)
        if (form.injury_type) categoryData.injury_type = form.injury_type
        if (form.treatment) categoryData.treatment = form.treatment
        categoryData.osha_recordable = form.osha_recordable
      } else if (form.incident_type === 'behavioral') {
        if (form.policy_violated) categoryData.policy_violated = form.policy_violated
        categoryData.manager_notified = form.manager_notified
      } else if (form.incident_type === 'property') {
        if (form.asset_damaged) categoryData.asset_damaged = form.asset_damaged
        if (form.estimated_cost) categoryData.estimated_cost = parseFloat(form.estimated_cost)
        categoryData.insurance_claim = form.insurance_claim
      } else if (form.incident_type === 'near_miss') {
        if (form.potential_outcome) categoryData.potential_outcome = form.potential_outcome
        if (form.hazard_identified) categoryData.hazard_identified = form.hazard_identified
      }

      const witnessPayload: IRWitness[] = witnesses
        .filter((w) => w.name.trim())
        .map((w) => ({ name: w.name.trim(), contact: w.contact.trim() || null }))

      const created = await api.post<IRIncident>('/ir/incidents', {
        incident_type: form.incident_type,
        title: form.title,
        description: form.description || null,
        severity: form.severity,
        location: form.location || null,
        occurred_at: form.date_occurred ? new Date(form.date_occurred).toISOString() : new Date().toISOString(),
        reported_by_name: form.reported_by_name || 'Unknown',
        reported_by_email: form.reported_by_email || null,
        witnesses: witnessPayload,
        category_data: Object.keys(categoryData).length > 0 ? categoryData : null,
      })
      setShowForm(false)
      setForm(EMPTY_FORM)
      setWitnesses([])
      navigate(`/app/ir/${created.id}`)
    } finally {
      setSaving(false)
    }
  }

  function formatDate(dateStr: string | null) {
    if (!dateStr) return '\u2014'
    return new Date(dateStr).toLocaleDateString()
  }

  async function generateAnonLink() {
    setAnonLoading(true)
    try {
      const res = await api.post<{ link: string }>('/ir/incidents/anonymous-reporting/generate')
      setAnonStatus({ enabled: true, link: res.link })
    } catch { /* ignore */ }
    finally { setAnonLoading(false) }
  }

  async function disableAnon() {
    setAnonLoading(true)
    try {
      await api.delete('/ir/incidents/anonymous-reporting/disable')
      setAnonStatus({ enabled: false })
    } catch { /* ignore */ }
    finally { setAnonLoading(false) }
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk]">
            Incident Reporting
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            Track and manage workplace incidents.
          </p>
        </div>
        <Button onClick={() => setShowForm(true)}>Report Incident</Button>
      </div>

      {/* Create incident modal */}
      <Modal open={showForm} onClose={() => setShowForm(false)} title="Report Incident">
        <form onSubmit={handleCreate} className="space-y-4 max-h-[70vh] overflow-y-auto pr-1">
          <Select
            label="Incident Type"
            options={INCIDENT_TYPE_OPTIONS}
            value={form.incident_type}
            onChange={(e) => setForm({ ...form, incident_type: e.target.value as IRIncidentType })}
          />
          <Input
            label="Title"
            required
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="Brief description of the incident"
          />
          <Textarea
            label="Description"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="What happened? Include relevant details."
          />
          <div className="grid grid-cols-2 gap-3">
            <Select
              label="Severity"
              options={SEVERITY_OPTIONS}
              value={form.severity}
              onChange={(e) => setForm({ ...form, severity: e.target.value })}
            />
            <Input
              label="Location"
              value={form.location}
              onChange={(e) => setForm({ ...form, location: e.target.value })}
              placeholder="Where did it occur?"
            />
          </div>
          <Input
            label="Date & Time Occurred"
            type="datetime-local"
            value={form.date_occurred}
            onChange={(e) => setForm({ ...form, date_occurred: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Reporter Name"
              required
              value={form.reported_by_name}
              onChange={(e) => setForm({ ...form, reported_by_name: e.target.value })}
              placeholder="Who is reporting?"
            />
            <Input
              label="Reporter Email"
              type="email"
              value={form.reported_by_email}
              onChange={(e) => setForm({ ...form, reported_by_email: e.target.value })}
              placeholder="Optional"
            />
          </div>

          {/* Category-specific fields */}
          {form.incident_type === 'safety' && (
            <div className="border border-zinc-800 rounded-lg p-3 space-y-3">
              <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Safety Details</p>
              <Input label="Injured Person" value={form.injured_person} onChange={(e) => setForm({ ...form, injured_person: e.target.value })} placeholder="Name of injured person" />
              <Input label="Body Parts (comma-separated)" value={form.body_parts} onChange={(e) => setForm({ ...form, body_parts: e.target.value })} placeholder="e.g. hand, wrist" />
              <div className="grid grid-cols-2 gap-3">
                <Input label="Injury Type" value={form.injury_type} onChange={(e) => setForm({ ...form, injury_type: e.target.value })} placeholder="e.g. cut, burn, strain" />
                <Select label="Treatment" options={[{ value: '', label: 'Select...' }, { value: 'first_aid', label: 'First Aid' }, { value: 'medical', label: 'Medical' }, { value: 'er', label: 'Emergency Room' }, { value: 'hospitalization', label: 'Hospitalization' }]} value={form.treatment} onChange={(e) => setForm({ ...form, treatment: e.target.value })} />
              </div>
              <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
                <input type="checkbox" checked={form.osha_recordable} onChange={(e) => setForm({ ...form, osha_recordable: e.target.checked })} className="rounded border-zinc-700 bg-zinc-900" />
                OSHA Recordable
              </label>
            </div>
          )}
          {form.incident_type === 'behavioral' && (
            <div className="border border-zinc-800 rounded-lg p-3 space-y-3">
              <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Behavioral Details</p>
              <Input label="Policy Violated" value={form.policy_violated} onChange={(e) => setForm({ ...form, policy_violated: e.target.value })} placeholder="Which policy was violated?" />
              <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
                <input type="checkbox" checked={form.manager_notified} onChange={(e) => setForm({ ...form, manager_notified: e.target.checked })} className="rounded border-zinc-700 bg-zinc-900" />
                Manager Notified
              </label>
            </div>
          )}
          {form.incident_type === 'property' && (
            <div className="border border-zinc-800 rounded-lg p-3 space-y-3">
              <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Property Details</p>
              <Input label="Asset Damaged" value={form.asset_damaged} onChange={(e) => setForm({ ...form, asset_damaged: e.target.value })} placeholder="What was damaged?" />
              <Input label="Estimated Cost ($)" type="number" value={form.estimated_cost} onChange={(e) => setForm({ ...form, estimated_cost: e.target.value })} placeholder="0.00" />
              <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
                <input type="checkbox" checked={form.insurance_claim} onChange={(e) => setForm({ ...form, insurance_claim: e.target.checked })} className="rounded border-zinc-700 bg-zinc-900" />
                Insurance Claim Filed
              </label>
            </div>
          )}
          {form.incident_type === 'near_miss' && (
            <div className="border border-zinc-800 rounded-lg p-3 space-y-3">
              <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Near Miss Details</p>
              <Input label="Potential Outcome" value={form.potential_outcome} onChange={(e) => setForm({ ...form, potential_outcome: e.target.value })} placeholder="What could have happened?" />
              <Input label="Hazard Identified" value={form.hazard_identified} onChange={(e) => setForm({ ...form, hazard_identified: e.target.value })} placeholder="What hazard was found?" />
            </div>
          )}

          {/* Witnesses */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Witnesses</p>
              <button type="button" onClick={() => setWitnesses([...witnesses, { name: '', contact: '' }])} className="text-xs text-emerald-400 hover:text-emerald-300">+ Add Witness</button>
            </div>
            {witnesses.map((w, i) => (
              <div key={i} className="flex items-center gap-2 mb-2">
                <Input label="" placeholder="Name" value={w.name} onChange={(e) => { const copy = [...witnesses]; copy[i] = { ...copy[i], name: e.target.value }; setWitnesses(copy) }} className="flex-1" />
                <Input label="" placeholder="Contact" value={w.contact} onChange={(e) => { const copy = [...witnesses]; copy[i] = { ...copy[i], contact: e.target.value }; setWitnesses(copy) }} className="flex-1" />
                <button type="button" onClick={() => setWitnesses(witnesses.filter((_, j) => j !== i))} className="text-xs text-zinc-600 hover:text-red-400">&times;</button>
              </div>
            ))}
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" type="button" onClick={() => setShowForm(false)}>Cancel</Button>
            <Button type="submit" disabled={saving}>{saving ? 'Submitting...' : 'Submit Report'}</Button>
          </div>
        </form>
      </Modal>

      {/* Tab nav */}
      <div className="flex items-center gap-1 mt-4 mb-5">
        {(['dashboard', 'incidents', 'analytics'] as const).map((t) => (
          <Button key={t} variant={tab === t ? 'secondary' : 'ghost'} size="sm" onClick={() => setTab(t)}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </Button>
        ))}
      </div>

      {/* ── Tab: Dashboard ── */}
      {tab === 'dashboard' && (
        <div className="space-y-5">
          {/* Key metrics */}
          {summary && (
            <div className="grid gap-3 grid-cols-4">
              {([
                ['Total', summary.total],
                ['Open', summary.open],
                ['Investigating', summary.investigating],
                ['Critical', summary.critical],
              ] as const).map(([label, value]) => (
                <div key={label} className="border border-zinc-800 rounded-lg px-3 py-3 text-center">
                  <p className="text-xl font-semibold text-zinc-100">{value}</p>
                  <p className="text-[11px] text-zinc-500 uppercase tracking-wide mt-0.5">{label}</p>
                </div>
              ))}
            </div>
          )}

          {/* Weekly trends */}
          {trends.length > 0 && (
            <div>
              <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">Weekly Trends (90d)</h2>
              <div className="border border-zinc-800 rounded-lg p-4 space-y-2">
                {(() => {
                  const max = Math.max(...trends.map((t) => t.count), 1)
                  return trends.slice(-12).map((t) => (
                    <div key={t.date} className="flex items-center gap-2">
                      <span className="text-xs text-zinc-500 w-20 shrink-0">{new Date(t.date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span>
                      <div className="flex-1 h-2 rounded-full bg-zinc-800 overflow-hidden">
                        <div className="h-full rounded-full bg-emerald-500/60" style={{ width: `${(t.count / max) * 100}%` }} />
                      </div>
                      <span className="text-[11px] text-zinc-500 w-6 text-right">{t.count}</span>
                    </div>
                  ))
                })()}
              </div>
            </div>
          )}

          {/* Top locations */}
          {locations.length > 0 && (
            <div>
              <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">Top Locations</h2>
              <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
                {locations.map((loc, i) => (
                  <div key={i} className="flex items-center justify-between px-4 py-2.5">
                    <span className="text-sm text-zinc-200">{loc.location || 'Unknown'}</span>
                    <span className="text-sm font-medium text-zinc-400">{loc.count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recent incidents */}
          {incidents.length > 0 && (
            <div>
              <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">Recent Incidents</h2>
              <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
                {incidents.slice(0, 5).map((inc) => (
                  <div key={inc.id} onClick={() => navigate(`/app/ir/${inc.id}`)}
                    className="flex items-center justify-between px-4 py-2.5 hover:bg-zinc-900/30 cursor-pointer transition-colors">
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="text-xs text-zinc-500 font-mono shrink-0">{inc.incident_number}</span>
                      <span className="text-sm text-zinc-200 truncate">{inc.title}</span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Badge variant={SEVERITY_BADGE[inc.severity] ?? 'neutral'}>{severityLabel(inc.severity)}</Badge>
                      <Badge variant={STATUS_BADGE[inc.status] ?? 'neutral'}>{statusLabel(inc.status)}</Badge>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Tab: Incidents ── */}
      {tab === 'incidents' && (
        <div className="space-y-5">
          {/* Summary stats */}
          {summary && (
            <div className="grid gap-3 grid-cols-4">
              {([
                ['Total', summary.total],
                ['Open', summary.open],
                ['Investigating', summary.investigating],
                ['Critical', summary.critical],
              ] as const).map(([label, value]) => (
                <div key={label} className="border border-zinc-800 rounded-lg px-3 py-3 text-center">
                  <p className="text-xl font-semibold text-zinc-100">{value}</p>
                  <p className="text-[11px] text-zinc-500 uppercase tracking-wide mt-0.5">{label}</p>
                </div>
              ))}
            </div>
          )}

          {/* Status filter tabs */}
          <div className="flex items-center gap-1 flex-wrap">
            {([
              ['all', 'All'],
              ['needs_attention', 'Needs Attention'],
              ['reported', 'Reported'],
              ['investigating', 'Investigating'],
              ['action_required', 'Action Required'],
              ['resolved', 'Resolved'],
              ['closed', 'Closed'],
            ] as const).map(([val, label]) => (
              <Button key={val} variant={statusFilter === val ? 'primary' : 'ghost'} size="sm" onClick={() => setStatusFilter(val)}>
                {label}
              </Button>
            ))}
          </div>

          {/* Search + type + severity filters */}
          <div className="flex items-center gap-3">
            <Input
              label=""
              placeholder="Search incidents..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="max-w-xs"
            />
            <div className="w-36">
              <Select
                label=""
                options={[{ value: 'all', label: 'All Types' }, ...INCIDENT_TYPE_OPTIONS]}
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value as TypeFilter)}
              />
            </div>
            <div className="flex gap-1 ml-auto">
              {(['all', 'low', 'medium', 'high', 'critical'] as const).map((s) => (
                <Button key={s} variant={severityFilter === s ? 'primary' : 'ghost'} size="sm" onClick={() => setSeverityFilter(s)}>
                  {s.charAt(0).toUpperCase() + s.slice(1)}
                </Button>
              ))}
            </div>
          </div>

          {/* Incidents table */}
          {loading ? (
            <p className="text-sm text-zinc-500">Loading...</p>
          ) : filtered.length === 0 ? (
            <p className="text-sm text-zinc-500">No incidents found.</p>
          ) : (
            <div className="overflow-hidden rounded-xl border border-zinc-800">
              <table className="w-full text-sm text-left">
                <thead className="bg-zinc-900/50 text-zinc-400">
                  <tr>
                    <th className="px-4 py-3 font-medium">Incident #</th>
                    <th className="px-4 py-3 font-medium">Title</th>
                    <th className="px-4 py-3 font-medium">Type</th>
                    <th className="px-4 py-3 font-medium">Severity</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 font-medium">Date</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800">
                  {filtered.map((inc) => (
                    <tr key={inc.id} className="text-zinc-300 hover:bg-zinc-900/30 transition-colors cursor-pointer" onClick={() => navigate(`/app/ir/${inc.id}`)}>
                      <td className="px-4 py-3 font-mono text-xs text-zinc-400">{inc.incident_number}</td>
                      <td className="px-4 py-3">
                        <p className="font-medium text-zinc-100">{inc.title}</p>
                        {inc.location && <p className="text-xs text-zinc-500 mt-0.5">{inc.location}</p>}
                      </td>
                      <td className="px-4 py-3">{typeLabel(inc.incident_type)}</td>
                      <td className="px-4 py-3">
                        <Badge variant={SEVERITY_BADGE[inc.severity] ?? 'neutral'}>{severityLabel(inc.severity)}</Badge>
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={STATUS_BADGE[inc.status] ?? 'neutral'}>{statusLabel(inc.status)}</Badge>
                      </td>
                      <td className="px-4 py-3 text-zinc-400 text-xs">{formatDate(inc.occurred_at ?? inc.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Anonymous reporting */}
          <div className="border border-zinc-800 rounded-lg">
            <button type="button" onClick={() => setAnonExpanded(!anonExpanded)}
              className="w-full flex items-center justify-between px-4 py-3 text-left">
              <span className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Anonymous Reporting</span>
              <span className="text-xs text-zinc-600">{anonExpanded ? '−' : '+'}</span>
            </button>
            {anonExpanded && (
              <div className="px-4 pb-4 space-y-3">
                {!anonStatus ? (
                  <p className="text-sm text-zinc-500">Loading...</p>
                ) : (
                  <>
                    {anonStatus.link && (
                      <div className="flex items-center gap-2">
                        <input readOnly value={anonStatus.link} className="flex-1 bg-zinc-900 border border-zinc-800 rounded text-xs text-zinc-300 px-2 py-1.5 font-mono" />
                        <Button size="sm" variant="ghost" onClick={() => navigator.clipboard.writeText(anonStatus.link!)}>Copy</Button>
                      </div>
                    )}
                    <div className="flex items-center gap-2">
                      <Button size="sm" disabled={anonLoading} onClick={generateAnonLink}>
                        {anonStatus.link ? 'Regenerate Link' : 'Generate Link'}
                      </Button>
                      {anonStatus.enabled && (
                        <Button size="sm" variant="ghost" disabled={anonLoading} onClick={disableAnon}>Disable</Button>
                      )}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Tab: Analytics ── */}
      {tab === 'analytics' && (
        <div className="space-y-5">
          {loadingSummary ? (
            <p className="text-sm text-zinc-500">Loading...</p>
          ) : !summary ? (
            <p className="text-sm text-zinc-500">Unable to load analytics.</p>
          ) : (
            <>
              {/* Status breakdown */}
              <div>
                <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">By Status</h2>
                <div className="grid gap-3 grid-cols-4">
                  {([
                    ['Open', summary.open],
                    ['Investigating', summary.investigating],
                    ['Resolved', summary.resolved],
                    ['Closed', summary.closed],
                  ] as const).map(([label, value]) => (
                    <div key={label} className="border border-zinc-800 rounded-lg px-3 py-3 text-center">
                      <p className="text-xl font-semibold text-zinc-100">{value}</p>
                      <p className="text-[11px] text-zinc-500 uppercase tracking-wide mt-0.5">{label}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Severity breakdown */}
              <div>
                <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">By Severity</h2>
                <div className="grid gap-3 grid-cols-4">
                  {([
                    ['Critical', summary.critical],
                    ['High', summary.high],
                    ['Medium', summary.medium],
                    ['Low', summary.low],
                  ] as const).map(([label, value]) => (
                    <div key={label} className="border border-zinc-800 rounded-lg px-3 py-3 text-center">
                      <p className="text-xl font-semibold text-zinc-100">{value}</p>
                      <p className="text-[11px] text-zinc-500 uppercase tracking-wide mt-0.5">{label}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* By type */}
              {summary.by_type && Object.keys(summary.by_type).length > 0 && (
                <div>
                  <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">By Type</h2>
                  <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
                    {Object.entries(summary.by_type)
                      .sort(([, a], [, b]) => b - a)
                      .map(([type, count]) => (
                        <div key={type} className="flex items-center justify-between px-4 py-2.5">
                          <span className="text-sm text-zinc-200">{typeLabel(type)}</span>
                          <span className="text-sm font-medium text-zinc-400">{count}</span>
                        </div>
                      ))}
                  </div>
                </div>
              )}

              {/* Consistency analytics */}
              {consistency && (
                <div>
                  <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Consistency Analytics</h2>
                  <div className="border border-zinc-800 rounded-lg p-4 space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div className="text-center">
                        <p className="text-lg font-semibold text-zinc-100">{consistency.total_resolved}</p>
                        <p className="text-[11px] text-zinc-500 uppercase">Resolved</p>
                      </div>
                      <div className="text-center">
                        <p className="text-lg font-semibold text-zinc-100">{consistency.total_with_actions}</p>
                        <p className="text-[11px] text-zinc-500 uppercase">With Actions</p>
                      </div>
                    </div>

                    {/* Action distribution bars */}
                    {consistency.action_distribution.length > 0 && (
                      <div className="space-y-2">
                        <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Action Distribution</p>
                        {(() => {
                          const max = Math.max(...consistency.action_distribution.map((a) => a.probability), 0.01)
                          return consistency.action_distribution.map((a) => (
                            <div key={a.category} className="flex items-center gap-2">
                              <span className="text-xs text-zinc-400 w-28 shrink-0 truncate">{typeLabel(a.category)}</span>
                              <div className="flex-1 h-2 rounded-full bg-zinc-800 overflow-hidden">
                                <div className="h-full rounded-full bg-emerald-500/60" style={{ width: `${(a.probability / max) * 100}%` }} />
                              </div>
                              <span className="text-[11px] text-zinc-500 w-10 text-right">{Math.round(a.probability * 100)}%</span>
                            </div>
                          ))
                        })()}
                      </div>
                    )}

                    {/* By type breakdown */}
                    {consistency.by_incident_type.length > 0 && (
                      <div className="space-y-2">
                        <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide">By Incident Type</p>
                        {consistency.by_incident_type.map((bt) => (
                          <div key={bt.incident_type} className="flex items-center justify-between px-2 py-1">
                            <span className="text-xs text-zinc-300">{typeLabel(bt.incident_type)}</span>
                            <span className="text-xs text-zinc-500">{bt.total} incidents</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* By severity breakdown */}
                    {consistency.by_severity.length > 0 && (
                      <div className="space-y-2">
                        <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide">By Severity</p>
                        {consistency.by_severity.map((bs) => (
                          <div key={bs.severity} className="flex items-center justify-between px-2 py-1">
                            <span className="text-xs text-zinc-300">{severityLabel(bs.severity)}</span>
                            <span className="text-xs text-zinc-500">{bs.total} incidents</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
