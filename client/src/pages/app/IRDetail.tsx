import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Badge, Button, Card, Select } from '../../components/ui'
import { useIRIncident } from '../../hooks/ir/useIRIncident'
import { IRCategorizationPanel } from '../../components/ir/IRCategorizationPanel'
import { IRRootCausePanel } from '../../components/ir/IRRootCausePanel'
import { IRRecommendationsPanel } from '../../components/ir/IRRecommendationsPanel'
import { IRSimilarIncidentsPanel } from '../../components/ir/IRSimilarIncidentsPanel'
import { IRPolicyMappingPanel } from '../../components/ir/IRPolicyMappingPanel'
import { IRConsistencyGuidancePanel } from '../../components/ir/IRConsistencyGuidancePanel'
import { IRDocumentPanel } from '../../components/ir/IRDocumentPanel'
import { IRInterviewScheduler } from '../../components/ir/IRInterviewScheduler'
import { IREscalationForm } from '../../components/ir/IREscalationForm'
import { IRCategoryDataDisplay } from '../../components/ir/IRCategoryDataDisplay'
import {
  typeLabel, statusLabel, severityLabel,
  SEVERITY_BADGE, STATUS_BADGE, SEVERITY_OPTIONS,
  type IRCategorizationAnalysis,
  type IRRootCauseAnalysis,
  type IRRecommendationsAnalysis,
} from '../../types/ir'

const STATUS_OPTIONS = [
  { value: 'reported', label: 'Reported' },
  { value: 'investigating', label: 'Investigating' },
  { value: 'action_required', label: 'Action Required' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'closed', label: 'Closed' },
]

type Tab = 'overview' | 'documents' | 'analysis' | 'interviews'

export default function IRDetail() {
  const { incidentId } = useParams<{ incidentId: string }>()
  const navigate = useNavigate()
  const { incident, loading, error, updateIncident, deleteIncident } = useIRIncident(incidentId!)
  const [tab, setTab] = useState<Tab>('overview')

  const [rootCause, setRootCause] = useState('')
  const [correctiveActions, setCorrectiveActions] = useState('')
  const [savingFields, setSavingFields] = useState(false)
  const [initialized, setInitialized] = useState(false)

  // Persist AI analysis results across tab switches
  const [categorizationResult, setCategorizationResult] = useState<IRCategorizationAnalysis | null>(null)
  const [rootCauseResult, setRootCauseResult] = useState<IRRootCauseAnalysis | null>(null)
  const [recommendationsResult, setRecommendationsResult] = useState<IRRecommendationsAnalysis | null>(null)

  // Sync local textarea state from incident on first load
  if (incident && !initialized) {
    setRootCause(incident.root_cause || '')
    setCorrectiveActions(incident.corrective_actions || '')
    setInitialized(true)
  }

  async function updateField(field: string, value: string) {
    setSavingFields(true)
    try { await updateIncident({ [field]: value } as never) }
    finally { setSavingFields(false) }
  }

  async function handleDelete() {
    if (!confirm('Delete this incident? This cannot be undone.')) return
    await deleteIncident()
    navigate('/app/ir')
  }

  if (loading) return <p className="text-sm text-zinc-500">Loading incident...</p>
  if (error) return <p className="text-sm text-red-400">{error}</p>
  if (!incident) return <p className="text-sm text-zinc-500">Incident not found.</p>

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <Link to="/app/ir" className="text-zinc-500 hover:text-zinc-300 transition-colors">&larr;</Link>
        <span className="text-xs text-zinc-500 font-mono">{incident.incident_number}</span>
        <h1 className="text-xl font-semibold text-zinc-100">{incident.title}</h1>
        <Badge variant={SEVERITY_BADGE[incident.severity] ?? 'neutral'}>{severityLabel(incident.severity)}</Badge>
        <Badge variant={STATUS_BADGE[incident.status] ?? 'neutral'}>{statusLabel(incident.status)}</Badge>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Main */}
        <div className="col-span-2">
          <div className="flex gap-1 mb-4">
            {(['overview', 'documents', 'analysis', 'interviews'] as const).map((t) => (
              <Button key={t} variant={tab === t ? 'secondary' : 'ghost'} size="sm" onClick={() => setTab(t)}>
                {t === 'analysis' ? 'AI Analysis' : t.charAt(0).toUpperCase() + t.slice(1)}
              </Button>
            ))}
          </div>

          <Card className="p-5">
            {/* Overview */}
            {tab === 'overview' && (
              <div className="space-y-5">
                {incident.description && (
                  <div>
                    <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Description</h3>
                    <p className="text-sm text-zinc-300 leading-relaxed whitespace-pre-wrap">{incident.description}</p>
                  </div>
                )}
                <div className="grid grid-cols-2 gap-4">
                  {incident.location && (
                    <div>
                      <dt className="text-[11px] font-medium uppercase tracking-wide text-zinc-500 mb-1">Location</dt>
                      <dd className="text-sm text-zinc-200">{incident.location}</dd>
                    </div>
                  )}
                  {incident.reported_by_name && (
                    <div>
                      <dt className="text-[11px] font-medium uppercase tracking-wide text-zinc-500 mb-1">Reported By</dt>
                      <dd className="text-sm text-zinc-200">{incident.is_anonymous ? 'Anonymous' : incident.reported_by_name}</dd>
                    </div>
                  )}
                  {incident.occurred_at && (
                    <div>
                      <dt className="text-[11px] font-medium uppercase tracking-wide text-zinc-500 mb-1">Date Occurred</dt>
                      <dd className="text-sm text-zinc-200">{new Date(incident.occurred_at).toLocaleDateString()}</dd>
                    </div>
                  )}
                  {incident.reported_by_email && (
                    <div>
                      <dt className="text-[11px] font-medium uppercase tracking-wide text-zinc-500 mb-1">Reporter Email</dt>
                      <dd className="text-sm text-zinc-200">{incident.reported_by_email}</dd>
                    </div>
                  )}
                </div>

                {incident.category_data && Object.keys(incident.category_data).length > 0 && (
                  <IRCategoryDataDisplay incidentType={incident.incident_type} categoryData={incident.category_data} />
                )}

                {incident.witnesses && incident.witnesses.length > 0 && (
                  <div>
                    <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Witnesses</h3>
                    <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
                      {incident.witnesses.map((w, i) => (
                        <div key={i} className="flex items-center justify-between px-4 py-2">
                          <span className="text-sm text-zinc-200">{w.name}</span>
                          {w.contact && <span className="text-xs text-zinc-500">{w.contact}</span>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {incident.involved_employee_ids && incident.involved_employee_ids.length > 0 && (
                  <div>
                    <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Involved Employees</h3>
                    <div className="flex flex-wrap gap-1.5">
                      {incident.involved_employee_ids.map((id) => (
                        <span key={id} className="text-xs px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400 font-mono">{id.slice(0, 8)}...</span>
                      ))}
                    </div>
                  </div>
                )}

                <div>
                  <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Root Cause</h3>
                  <textarea className="w-full bg-zinc-900 border border-zinc-800 rounded-lg text-sm text-zinc-200 px-3 py-2 min-h-[80px] focus:outline-none focus:border-zinc-600"
                    value={rootCause} onChange={(e) => setRootCause(e.target.value)} placeholder="Document the root cause..." />
                  {rootCause !== (incident.root_cause || '') && (
                    <Button size="sm" className="mt-1" disabled={savingFields} onClick={() => updateField('root_cause', rootCause)}>
                      {savingFields ? 'Saving...' : 'Save'}
                    </Button>
                  )}
                </div>
                <div>
                  <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Corrective Actions</h3>
                  <textarea className="w-full bg-zinc-900 border border-zinc-800 rounded-lg text-sm text-zinc-200 px-3 py-2 min-h-[80px] focus:outline-none focus:border-zinc-600"
                    value={correctiveActions} onChange={(e) => setCorrectiveActions(e.target.value)} placeholder="Document corrective actions taken..." />
                  {correctiveActions !== (incident.corrective_actions || '') && (
                    <Button size="sm" className="mt-1" disabled={savingFields} onClick={() => updateField('corrective_actions', correctiveActions)}>
                      {savingFields ? 'Saving...' : 'Save'}
                    </Button>
                  )}
                </div>
              </div>
            )}

            {tab === 'documents' && <IRDocumentPanel incidentId={incidentId!} />}

            {tab === 'analysis' && (
              <div className="space-y-6">
                <IRCategorizationPanel incidentId={incidentId!} result={categorizationResult} onResult={setCategorizationResult} />
                <IRRootCausePanel incidentId={incidentId!} result={rootCauseResult} onResult={setRootCauseResult} />
                <IRRecommendationsPanel incidentId={incidentId!} result={recommendationsResult} onResult={setRecommendationsResult} />
                <IRSimilarIncidentsPanel incidentId={incidentId!} />
              </div>
            )}

            {tab === 'interviews' && (
              <IRInterviewScheduler incidentId={incidentId!} witnesses={incident.witnesses} />
            )}
          </Card>
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          <Card className="p-0 overflow-hidden">
            <div className="px-5 py-3 border-b border-zinc-800/60 bg-zinc-900/40">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Incident Details</h3>
            </div>
            <div className="px-5 py-4 space-y-4">
              <div>
                <dt className="text-[11px] font-medium uppercase tracking-wide text-zinc-500 mb-1.5">Status</dt>
                <Select label="" options={STATUS_OPTIONS} value={incident.status} onChange={(e) => updateIncident({ status: e.target.value } as never)} />
              </div>
              <div>
                <dt className="text-[11px] font-medium uppercase tracking-wide text-zinc-500 mb-1.5">Severity</dt>
                <Select label="" options={SEVERITY_OPTIONS} value={incident.severity} onChange={(e) => updateIncident({ severity: e.target.value } as never)} />
              </div>
              <div>
                <dt className="text-[11px] font-medium uppercase tracking-wide text-zinc-500 mb-1">Type</dt>
                <dd className="text-sm text-zinc-200">{typeLabel(incident.incident_type)}</dd>
              </div>
            </div>
          </Card>

          <Card className="p-0 overflow-hidden">
            <div className="px-5 py-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <dt className="text-[11px] font-medium uppercase tracking-wide text-zinc-500 mb-1">Created</dt>
                  <dd className="text-sm text-zinc-200">{new Date(incident.created_at).toLocaleDateString()}</dd>
                </div>
                <div>
                  <dt className="text-[11px] font-medium uppercase tracking-wide text-zinc-500 mb-1">Updated</dt>
                  <dd className="text-sm text-zinc-200">{new Date(incident.updated_at).toLocaleDateString()}</dd>
                </div>
              </div>
              <div className="mt-4 flex items-center justify-between">
                <dt className="text-[11px] font-medium uppercase tracking-wide text-zinc-500">Documents</dt>
                <dd className="text-sm font-medium text-zinc-200">{incident.document_count}</dd>
              </div>
            </div>
          </Card>

          <IRPolicyMappingPanel incidentId={incidentId!} />
          <IRConsistencyGuidancePanel incidentId={incidentId!} status={incident.status} />

          <div className="space-y-2 pt-2">
            <IREscalationForm incidentId={incidentId!} incident={incident} onEscalated={(id) => navigate(`/app/er-copilot/${id}`)} />
            <button type="button" className="text-xs text-zinc-600 hover:text-red-400 transition-colors" onClick={handleDelete}>
              Delete incident
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
