import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import { Badge, Button, Input, Modal, Select, Textarea } from '../../components/ui'
import type { BadgeVariant } from '../../components/ui'

// --- Types ---

type IRIncident = {
  id: string
  incident_number: string
  incident_type: string
  title: string
  description: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  status: 'open' | 'investigating' | 'resolved' | 'closed'
  location: string | null
  reported_by_name: string | null
  is_anonymous: boolean
  date_occurred: string | null
  created_at: string
  updated_at: string
}

type IncidentListResponse = {
  incidents: IRIncident[]
  total: number
}

type AnalyticsSummary = {
  total: number
  open: number
  investigating: number
  resolved: number
  closed: number
  critical: number
  high: number
  medium: number
  low: number
  by_type: Record<string, number>
}

type Tab = 'incidents' | 'analytics'
type SeverityFilter = 'all' | 'low' | 'medium' | 'high' | 'critical'

const SEVERITY_BADGE: Record<IRIncident['severity'], BadgeVariant> = {
  low: 'neutral',
  medium: 'warning',
  high: 'warning',
  critical: 'danger',
}

const STATUS_BADGE: Record<IRIncident['status'], BadgeVariant> = {
  open: 'danger',
  investigating: 'warning',
  resolved: 'success',
  closed: 'neutral',
}

const INCIDENT_TYPE_OPTIONS = [
  { value: 'safety', label: 'Safety' },
  { value: 'behavioral', label: 'Behavioral' },
  { value: 'harassment', label: 'Harassment' },
  { value: 'discrimination', label: 'Discrimination' },
  { value: 'theft', label: 'Theft' },
  { value: 'policy_violation', label: 'Policy Violation' },
  { value: 'other', label: 'Other' },
]

const SEVERITY_OPTIONS = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
]

const EMPTY_FORM = {
  incident_type: 'safety',
  title: '',
  description: '',
  severity: 'medium',
  location: '',
  date_occurred: '',
}

// --- Component ---

export default function IRList() {
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('incidents')

  // Incidents state
  const [incidents, setIncidents] = useState<IRIncident[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all')

  // Analytics state
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null)
  const [loadingSummary, setLoadingSummary] = useState(false)

  // Create form state
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  // Fetch incidents
  useEffect(() => {
    setLoading(true)
    const params = new URLSearchParams()
    if (severityFilter !== 'all') params.set('severity', severityFilter)
    params.set('limit', '100')
    const qs = params.toString()
    api.get<IncidentListResponse>(`/ir/incidents${qs ? `?${qs}` : ''}`)
      .then((res) => setIncidents(res.incidents))
      .catch(() => setIncidents([]))
      .finally(() => setLoading(false))
  }, [severityFilter])

  // Fetch summary for stat boxes (always) and analytics tab
  useEffect(() => {
    setLoadingSummary(true)
    api.get<AnalyticsSummary>('/ir/incidents/analytics/summary')
      .then((res) => setSummary(res))
      .catch(() => setSummary(null))
      .finally(() => setLoadingSummary(false))
  }, [])

  const filtered = incidents.filter((inc) =>
    inc.title.toLowerCase().includes(search.toLowerCase()) ||
    inc.incident_number.toLowerCase().includes(search.toLowerCase())
  )

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      const created = await api.post<IRIncident>('/ir/incidents', {
        incident_type: form.incident_type,
        title: form.title,
        description: form.description || null,
        severity: form.severity,
        location: form.location || null,
        date_occurred: form.date_occurred || null,
      })
      setShowForm(false)
      setForm(EMPTY_FORM)
      navigate(`/app/ir/${created.id}`)
    } finally {
      setSaving(false)
    }
  }

  function formatDate(dateStr: string | null) {
    if (!dateStr) return '\u2014'
    return new Date(dateStr).toLocaleDateString()
  }

  function statusLabel(s: string) {
    return s.charAt(0).toUpperCase() + s.slice(1)
  }

  function typeLabel(t: string) {
    return t.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
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
        <form onSubmit={handleCreate} className="space-y-4">
          <Select
            label="Incident Type"
            options={INCIDENT_TYPE_OPTIONS}
            value={form.incident_type}
            onChange={(e) => setForm({ ...form, incident_type: e.target.value })}
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
            placeholder="Where did the incident occur?"
          />
          <Input
            label="Date Occurred"
            type="date"
            value={form.date_occurred}
            onChange={(e) => setForm({ ...form, date_occurred: e.target.value })}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" type="button" onClick={() => setShowForm(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? 'Submitting...' : 'Submit Report'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Tab nav */}
      <div className="flex items-center gap-1 mt-4 mb-5">
        {(['incidents', 'analytics'] as const).map((t) => (
          <Button
            key={t}
            variant={tab === t ? 'secondary' : 'ghost'}
            size="sm"
            onClick={() => setTab(t)}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </Button>
        ))}
      </div>

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

          {/* Search + severity filters */}
          <div className="flex items-center gap-3">
            <Input
              label=""
              placeholder="Search incidents..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="max-w-xs"
            />
            <div className="flex gap-1 ml-auto">
              {(['all', 'low', 'medium', 'high', 'critical'] as const).map((s) => (
                <Button
                  key={s}
                  variant={severityFilter === s ? 'primary' : 'ghost'}
                  size="sm"
                  onClick={() => setSeverityFilter(s)}
                >
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
                    <tr
                      key={inc.id}
                      className="text-zinc-300 hover:bg-zinc-900/30 transition-colors cursor-pointer"
                      onClick={() => navigate(`/app/ir/${inc.id}`)}
                    >
                      <td className="px-4 py-3 font-mono text-xs text-zinc-400">
                        {inc.incident_number}
                      </td>
                      <td className="px-4 py-3">
                        <p className="font-medium text-zinc-100">{inc.title}</p>
                        {inc.location && (
                          <p className="text-xs text-zinc-500 mt-0.5">{inc.location}</p>
                        )}
                      </td>
                      <td className="px-4 py-3">{typeLabel(inc.incident_type)}</td>
                      <td className="px-4 py-3">
                        <Badge variant={SEVERITY_BADGE[inc.severity]}>
                          {inc.severity.charAt(0).toUpperCase() + inc.severity.slice(1)}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={STATUS_BADGE[inc.status]}>
                          {statusLabel(inc.status)}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-zinc-400 text-xs">
                        {formatDate(inc.date_occurred ?? inc.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
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
                <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">
                  By Status
                </h2>
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
                <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">
                  By Severity
                </h2>
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
                  <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">
                    By Type
                  </h2>
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
            </>
          )}
        </div>
      )}
    </div>
  )
}
