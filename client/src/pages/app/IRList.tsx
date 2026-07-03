import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Download, Search } from 'lucide-react'
import { api } from '../../api/client'
import { Badge, Button, PillTabs, Select } from '../../components/ui'
import { IRCreateIncidentModal } from '../../components/ir/IRCreateIncidentModal'
import { IRDashboardTab } from '../../components/ir/IRDashboardTab'
import { IRExportModal } from '../../components/ir/IRExportModal'
import { IRStatHero } from '../../components/ir/IRStatHero'
import { formatDate } from '../../utils/dateFormat'
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

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-light text-zinc-50 tracking-tight">Incident Reporting</h1>
          <p className="mt-1.5 text-sm text-zinc-500 font-serif italic" style={{ fontFamily: 'Fraunces, Georgia, serif' }}>
            Track and manage workplace incidents.
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

      <PillTabs
        options={[
          { value: 'dashboard', label: 'Dashboard' },
          { value: 'incidents', label: 'Incidents' },
        ]}
        value={tab}
        onChange={(v) => setTab(v as Tab)}
      />

      {tab === 'dashboard' && (
        <IRDashboardTab incidents={incidents} summary={summary} onNavigate={(id) => navigate(`/app/ir/${id}`)} />
      )}

      {tab === 'incidents' && (
        <div className="space-y-6">
          {summary && <IRStatHero summary={summary} captionLeft="Total Incidents" />}

          {/* Filter bar — flat, no card */}
          <div className="space-y-3">
            <PillTabs
              size="sm"
              options={[
                { value: 'all', label: 'All' },
                { value: 'reported', label: 'Reported' },
                { value: 'investigating', label: 'Investigating' },
                { value: 'action_required', label: 'Action Required' },
                { value: 'closed', label: 'Closed' },
              ]}
              value={statusFilter}
              onChange={(v) => setStatusFilter(v as StatusFilter)}
            />

            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
              <div className="relative flex-1 sm:max-w-xs">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-600 pointer-events-none" strokeWidth={1.6} />
                <input
                  type="text"
                  placeholder="Search incidents…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="w-full pl-8 pr-3 py-2 bg-white/[0.02] border-b border-white/[0.08] text-[12px] text-zinc-200 placeholder:text-zinc-600 outline-none focus:border-white/20 transition-colors"
                />
              </div>
              <div className="w-full sm:w-44">
                <Select
                  options={[{ value: 'all', label: 'All Types' }, ...INCIDENT_TYPE_OPTIONS]}
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value as TypeFilter)}
                />
              </div>
              <div className="sm:ml-auto">
                <PillTabs
                  size="sm"
                  options={[
                    { value: 'all', label: 'All' },
                    { value: 'low', label: 'Low' },
                    { value: 'medium', label: 'Medium' },
                    { value: 'high', label: 'High' },
                    { value: 'critical', label: 'Critical' },
                  ]}
                  value={severityFilter}
                  onChange={(v) => setSeverityFilter(v as SeverityFilter)}
                />
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
                  <thead className="text-zinc-600">
                    <tr>
                      <th className="px-5 py-3 text-[9px] uppercase tracking-[0.16em] font-medium">Incident #</th>
                      <th className="px-5 py-3 text-[9px] uppercase tracking-[0.16em] font-medium">Title</th>
                      <th className="px-5 py-3 text-[9px] uppercase tracking-[0.16em] font-medium">Type</th>
                      <th className="px-5 py-3 text-[9px] uppercase tracking-[0.16em] font-medium">Severity</th>
                      <th className="px-5 py-3 text-[9px] uppercase tracking-[0.16em] font-medium">Status</th>
                      <th className="px-5 py-3 text-[9px] uppercase tracking-[0.16em] font-medium text-right">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((inc) => (
                      <tr
                        key={inc.id}
                        className="group border-t border-white/[0.04] text-zinc-300 hover:bg-white/[0.02] transition-colors cursor-pointer"
                        onClick={() => navigate(`/app/ir/${inc.id}`)}
                      >
                        <td className="px-5 py-3.5 font-mono text-[11px] text-zinc-600 tabular-nums">{inc.incident_number}</td>
                        <td className="px-5 py-3.5">
                          <div className="flex items-center gap-2">
                            <p className="font-normal text-zinc-100 text-[13px]">{inc.title}</p>
                            <ArrowRight className="w-3 h-3 text-zinc-700 opacity-0 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all" strokeWidth={1.6} />
                          </div>
                          {inc.location && <p className="text-[11px] text-zinc-600 mt-0.5">{inc.location}</p>}
                        </td>
                        <td className="px-5 py-3.5 text-[12px] text-zinc-500 font-light">{typeLabel(inc.incident_type)}</td>
                        <td className="px-5 py-3.5">
                          <Badge variant={SEVERITY_BADGE[inc.severity] ?? 'neutral'}>{severityLabel(inc.severity)}</Badge>
                        </td>
                        <td className="px-5 py-3.5">
                          <Badge variant={STATUS_BADGE[inc.status] ?? 'neutral'}>{statusLabel(inc.status)}</Badge>
                        </td>
                        <td className="px-5 py-3.5 text-right text-zinc-500 text-[11px] font-mono tabular-nums">{formatDate(inc.occurred_at ?? inc.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
