import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Download, Search } from 'lucide-react'
import { api } from '../../api/client'
import { Badge, Button, Input, Select } from '../../components/ui'
import { IRCreateIncidentModal } from '../../components/ir/IRCreateIncidentModal'
import { IRDashboardTab } from '../../components/ir/IRDashboardTab'
import { IRAnonymousReportingPanel } from '../../components/ir/IRAnonymousReportingPanel'
import { IRExportModal } from '../../components/ir/IRExportModal'
import { IRStatHero } from '../../components/ir/IRStatHero'
import type { IRIncident, IRIncidentType, IRAnalyticsSummary } from '../../types/ir'
import {
  typeLabel, statusLabel, severityLabel,
  SEVERITY_BADGE, STATUS_BADGE, INCIDENT_TYPE_OPTIONS,
} from '../../types/ir'

type Tab = 'dashboard' | 'incidents'
type SeverityFilter = 'all' | 'low' | 'medium' | 'high' | 'critical'
type StatusFilter = 'all' | 'reported' | 'investigating' | 'action_required' | 'closed'
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
  const [showExport, setShowExport] = useState(false)

  useEffect(() => {
    setLoading(true)
    const params = new URLSearchParams()
    if (severityFilter !== 'all') params.set('severity', severityFilter)
    if (statusFilter !== 'all') params.set('status', statusFilter)
    if (typeFilter !== 'all') params.set('incident_type', typeFilter)
    params.set('limit', '100')
    const qs = params.toString()
    api.get<IncidentListResponse>(`/ir/incidents${qs ? `?${qs}` : ''}`)
      .then((res) => setIncidents(res.incidents))
      .catch(() => setIncidents([]))
      .finally(() => setLoading(false))
  }, [severityFilter, statusFilter, typeFilter])

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
    if (!dateStr) return '—'
    return new Date(dateStr).toLocaleDateString()
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">Incident Reporting</h1>
          <p className="mt-1 text-[10px] text-zinc-500 font-mono uppercase tracking-wider">
            Track and manage workplace incidents
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => setShowExport(true)}>
            <Download className="w-3.5 h-3.5" />
            <span className="ml-2">Export</span>
          </Button>
          <Button onClick={() => setShowForm(true)}>Report Incident</Button>
        </div>
      </div>

      <IRCreateIncidentModal
        open={showForm}
        onClose={() => setShowForm(false)}
        onCreated={(inc) => { setShowForm(false); navigate(`/app/ir/${inc.id}`) }}
      />

      <IRExportModal open={showExport} onClose={() => setShowExport(false)} />

      {/* Tab nav — pill style matching RiskAssessment */}
      <div className="flex gap-0 border border-zinc-700 rounded-xl overflow-hidden w-fit">
        {(['dashboard', 'incidents'] as const).map((t) => (
          <button
            key={t}
            className={`px-5 py-2 text-[11px] uppercase tracking-widest font-bold transition-colors ${
              tab === t
                ? 'bg-zinc-800 text-zinc-50'
                : 'bg-zinc-900 text-zinc-500 hover:text-zinc-300'
            }`}
            onClick={() => setTab(t)}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {tab === 'dashboard' && (
        <IRDashboardTab incidents={incidents} summary={summary} onNavigate={(id) => navigate(`/app/ir/${id}`)} />
      )}

      {tab === 'incidents' && (
        <div className="space-y-6">
          {summary && <IRStatHero summary={summary} captionLeft="Total Incidents" />}

          {/* Filter bar */}
          <div className="bg-zinc-900 border border-white/10 rounded-2xl p-4 space-y-3">
            {/* Status pills */}
            <div className="flex items-center gap-1 flex-wrap">
              {([
                ['all', 'All'],
                ['reported', 'Reported'],
                ['investigating', 'Investigating'],
                ['action_required', 'Action Required'],
                ['closed', 'Closed'],
              ] as const).map(([val, label]) => (
                <button
                  key={val}
                  onClick={() => setStatusFilter(val)}
                  className={`px-3 py-1 text-[10px] uppercase tracking-widest font-bold rounded transition-colors ${
                    statusFilter === val
                      ? 'bg-zinc-700 text-zinc-50'
                      : 'bg-zinc-950/40 text-zinc-500 hover:text-zinc-300'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            {/* Search + type + severity */}
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
              <div className="relative flex-1 sm:max-w-xs">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-600 pointer-events-none" />
                <Input
                  label=""
                  placeholder="Search incidents..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="w-full pl-8"
                />
              </div>
              <div className="w-full sm:w-40">
                <Select
                  label=""
                  options={[{ value: 'all', label: 'All Types' }, ...INCIDENT_TYPE_OPTIONS]}
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value as TypeFilter)}
                />
              </div>
              <div className="flex gap-1 sm:ml-auto overflow-x-auto">
                {(['all', 'low', 'medium', 'high', 'critical'] as const).map((s) => (
                  <button
                    key={s}
                    onClick={() => setSeverityFilter(s)}
                    className={`px-3 py-1.5 text-[10px] uppercase tracking-widest font-bold rounded transition-colors ${
                      severityFilter === s
                        ? 'bg-zinc-700 text-zinc-50'
                        : 'bg-zinc-950/40 text-zinc-500 hover:text-zinc-300'
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Incidents table */}
          <div className="bg-zinc-900 border border-white/10 rounded-2xl overflow-hidden">
            {loading ? (
              <div className="p-8 text-xs text-zinc-500 uppercase tracking-widest font-mono text-center animate-pulse">
                Loading incidents…
              </div>
            ) : filtered.length === 0 ? (
              <div className="p-12 text-center">
                <p className="text-sm text-zinc-400">No incidents found.</p>
                <p className="text-[11px] text-zinc-600 mt-1">Adjust filters or report a new incident.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left min-w-[800px]">
                  <thead className="bg-zinc-950/50 text-zinc-500">
                    <tr>
                      <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Incident #</th>
                      <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Title</th>
                      <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Type</th>
                      <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Severity</th>
                      <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Status</th>
                      <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((inc) => (
                      <tr
                        key={inc.id}
                        className="border-t border-white/5 text-zinc-300 hover:bg-white/[0.02] transition-colors cursor-pointer"
                        onClick={() => navigate(`/app/ir/${inc.id}`)}
                      >
                        <td className="px-4 py-3 font-mono text-[11px] text-zinc-500">{inc.incident_number}</td>
                        <td className="px-4 py-3">
                          <p className="font-medium text-zinc-100 text-[13px]">{inc.title}</p>
                          {inc.location && <p className="text-[11px] text-zinc-500 mt-0.5">{inc.location}</p>}
                        </td>
                        <td className="px-4 py-3 text-[12px] text-zinc-400">{typeLabel(inc.incident_type)}</td>
                        <td className="px-4 py-3">
                          <Badge variant={SEVERITY_BADGE[inc.severity] ?? 'neutral'}>{severityLabel(inc.severity)}</Badge>
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant={STATUS_BADGE[inc.status] ?? 'neutral'}>{statusLabel(inc.status)}</Badge>
                        </td>
                        <td className="px-4 py-3 text-zinc-500 text-[11px] font-mono">{formatDate(inc.occurred_at ?? inc.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <IRAnonymousReportingPanel />
        </div>
      )}
    </div>
  )
}
