import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import { Badge, Button, Input, Select } from '../../components/ui'
import { IRCreateIncidentModal } from '../../components/ir/IRCreateIncidentModal'
import { IRDashboardTab } from '../../components/ir/IRDashboardTab'
import { IRConsistencyAnalyticsPanel } from '../../components/ir/IRConsistencyAnalyticsPanel'
import { IRAnonymousReportingPanel } from '../../components/ir/IRAnonymousReportingPanel'
import { IRRiskInsightsTab } from '../../components/ir/IRRiskInsightsTab'
import { OshaLogsPanel } from '../../components/ir/OshaLogsPanel'
import { IRSecuritySurveyTab } from '../../components/ir/IRSecuritySurveyTab'
import type { IRIncident, IRIncidentType, IRAnalyticsSummary } from '../../types/ir'
import {
  typeLabel, statusLabel, severityLabel,
  SEVERITY_BADGE, STATUS_BADGE, INCIDENT_TYPE_OPTIONS,
} from '../../types/ir'

type Tab = 'dashboard' | 'incidents' | 'risk' | 'analytics' | 'osha' | 'survey'
type SeverityFilter = 'all' | 'low' | 'medium' | 'high' | 'critical'
type StatusFilter = 'all' | 'needs_attention' | 'reported' | 'investigating' | 'action_required' | 'resolved' | 'closed'
type TypeFilter = 'all' | IRIncidentType

type IncidentListResponse = { incidents: IRIncident[]; total: number }

export default function IRList() {
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('incidents')

  const [incidents, setIncidents] = useState<IRIncident[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all')

  const [summary, setSummary] = useState<IRAnalyticsSummary | null>(null)
  const [showForm, setShowForm] = useState(false)

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
    api.get<IRAnalyticsSummary>('/ir/incidents/analytics/summary')
      .then(setSummary)
      .catch(() => setSummary(null))
  }, [])

  const filtered = incidents.filter(
    (inc) =>
      inc.title.toLowerCase().includes(search.toLowerCase()) ||
      inc.incident_number.toLowerCase().includes(search.toLowerCase()),
  )

  function formatDate(dateStr: string | null) {
    if (!dateStr) return '\u2014'
    return new Date(dateStr).toLocaleDateString()
  }

  return (
    <div>
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 sm:gap-0">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">
            Incident Reporting
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            Track and manage workplace incidents.
          </p>
        </div>
        <Button onClick={() => setShowForm(true)}>Report Incident</Button>
      </div>

      <IRCreateIncidentModal
        open={showForm}
        onClose={() => setShowForm(false)}
        onCreated={(inc) => { setShowForm(false); navigate(`/app/ir/${inc.id}`) }}
      />

      {/* Tab nav */}
      <div className="flex items-center gap-1 mt-4 mb-5">
        {(['dashboard', 'incidents', 'risk', 'osha', 'analytics', 'survey'] as const).map((t) => (
          <Button key={t} variant={tab === t ? 'secondary' : 'ghost'} size="sm" onClick={() => setTab(t)}>
            {t === 'osha' ? 'OSHA Logs' : t === 'risk' ? 'Risk Insights' : t === 'survey' ? 'Security Survey' : t.charAt(0).toUpperCase() + t.slice(1)}
          </Button>
        ))}
      </div>

      {tab === 'dashboard' && (
        <IRDashboardTab incidents={incidents} summary={summary} onNavigate={(id) => navigate(`/app/ir/${id}`)} />
      )}

      {tab === 'incidents' && (
        <div className="space-y-5">
          {/* Summary stats */}
          {summary && (
            <div className="grid gap-3 grid-cols-1 md:grid-cols-2 lg:grid-cols-4">
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
            <div className="flex gap-1 w-full sm:w-auto sm:ml-auto overflow-x-auto pb-2 sm:pb-0">
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
            <div className="overflow-x-auto rounded-xl border border-zinc-800">
              <table className="w-full text-sm text-left min-w-[800px]">
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

          <IRAnonymousReportingPanel />
        </div>
      )}

      {tab === 'risk' && (
        <IRRiskInsightsTab onNavigateIncident={(id) => navigate(`/app/ir/${id}`)} />
      )}

      {tab === 'osha' && <OshaLogsPanel />}

      {tab === 'analytics' && <IRConsistencyAnalyticsPanel />}

      {tab === 'survey' && <IRSecuritySurveyTab />}
    </div>
  )
}
