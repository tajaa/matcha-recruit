import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Download } from 'lucide-react'
import { Badge, Button, Select, LABEL, PillTabs } from '../../components/ui'
import { EmployeeMultiSelect } from '../../components/employees/EmployeeMultiSelect'
import { api } from '../../api/client'
import { useIRIncident } from '../../hooks/ir/useIRIncident'
import { IRCategorizationPanel } from '../../components/ir/IRCategorizationPanel'
import { IRRootCausePanel } from '../../components/ir/IRRootCausePanel'
import { IRRecommendationsPanel } from '../../components/ir/IRRecommendationsPanel'
import { IRSimilarIncidentsPanel } from '../../components/ir/IRSimilarIncidentsPanel'
import { IRPolicyMappingPanel } from '../../components/ir/IRPolicyMappingPanel'
import { IRConsistencyGuidancePanel } from '../../components/ir/IRConsistencyGuidancePanel'
import { IRDocumentPanel } from '../../components/ir/IRDocumentPanel'
import { IRCorrectiveActionsPanel } from '../../components/ir/IRCorrectiveActionsPanel'
import { IRInterviewScheduler } from '../../components/ir/IRInterviewScheduler'
import { IREscalationForm } from '../../components/ir/IREscalationForm'
import { IRCategoryDataDisplay } from '../../components/ir/IRCategoryDataDisplay'
import IRCopilotPanel from '../../components/ir/IRCopilotPanel'
import { UpgradeUpsellCard } from '../../components/UpgradeUpsellCard'
import { useMe } from '../../hooks/useMe'
import { isIrOnlyTier, isMatchaX } from '../../utils/tier'
import {
  typeLabel, statusLabel, severityLabel,
  SEVERITY_BADGE, STATUS_BADGE, SEVERITY_OPTIONS, PERSON_ROLE_LABEL,
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

const WC_CLAIM_TYPE_OPTIONS = [
  { value: '', label: '— Not classified —' },
  { value: 'acute', label: 'Acute (single event)' },
  { value: 'cumulative_trauma', label: 'Cumulative trauma (CT)' },
  { value: 'unknown', label: 'Unknown' },
]

type Tab = 'copilot' | 'overview' | 'documents' | 'analysis' | 'interviews'

const FULL_TABS = ['copilot', 'overview', 'documents', 'analysis', 'interviews'] as const
const LITE_TABS = ['copilot', 'overview', 'documents'] as const

export default function IRDetail() {
  const { incidentId } = useParams<{ incidentId: string }>()
  const { me, hasFeature } = useMe()
  const hasRoster = hasFeature('employees')
  const showPolicyMapping = hasFeature('policies')
  const showERFeatures = hasFeature('er_copilot')
  const showUpsell = !showPolicyMapping || !showERFeatures
  // Matcha-X is at Lite parity for IR — same restricted tab set.
  const liteTier = isIrOnlyTier(me?.profile) || isMatchaX(me?.profile)
  const tabs: readonly Tab[] = liteTier ? LITE_TABS : FULL_TABS
  const tabOptions = tabs.map((t) => ({
    value: t,
    label: t === 'analysis' ? 'AI Analysis' : t === 'copilot' ? 'Copilot' : t.charAt(0).toUpperCase() + t.slice(1),
  }))
  const navigate = useNavigate()
  const { incident, loading, error, updateIncident, deleteIncident, refetch } = useIRIncident(incidentId!)
  const [tab, setTab] = useState<Tab>('copilot')

  const [rootCause, setRootCause] = useState('')
  const [correctiveActions, setCorrectiveActions] = useState('')
  const [involvedEmpIds, setInvolvedEmpIds] = useState<string[]>([])
  const [savingFields, setSavingFields] = useState(false)
  const [savingEmployees, setSavingEmployees] = useState(false)
  const [initialized, setInitialized] = useState(false)

  // WC classification (wcdeep01) — feeds the broker WC analytics.
  const [wcClaimType, setWcClaimType] = useState('')
  const [wcPostTerm, setWcPostTerm] = useState(false)
  const [wcRtwDate, setWcRtwDate] = useState('')
  const [savingWc, setSavingWc] = useState(false)

  // Persist AI analysis results across tab switches
  const [categorizationResult, setCategorizationResult] = useState<IRCategorizationAnalysis | null>(null)
  const [rootCauseResult, setRootCauseResult] = useState<IRRootCauseAnalysis | null>(null)
  const [recommendationsResult, setRecommendationsResult] = useState<IRRecommendationsAnalysis | null>(null)

  // Bounce stale URL/tab state when tier-restricted tabs aren't available.
  useEffect(() => {
    if (!tabs.includes(tab)) setTab('copilot')
  }, [tabs, tab])

  // Sync local textarea state from incident on first load
  if (incident && !initialized) {
    setRootCause(incident.root_cause || '')
    setCorrectiveActions(incident.corrective_actions || '')
    setInvolvedEmpIds(incident.involved_employee_ids || [])
    setWcClaimType(incident.wc_claim_type || '')
    setWcPostTerm(incident.post_termination || false)
    setWcRtwDate(incident.return_to_work_date || '')
    setInitialized(true)
  }

  // UUID → display name for already-linked employees, so the picker's pills
  // render names immediately (seeded from the hydrated involved_employees).
  const employeeLabels: Record<string, string> = {}
  for (const e of incident?.involved_employees || []) {
    employeeLabels[e.id] = [e.first_name, e.last_name].filter(Boolean).join(' ').trim() || `${e.id.slice(0, 8)}…`
  }

  async function saveInvolvedEmployees() {
    setSavingEmployees(true)
    try { await updateIncident({ involved_employee_ids: involvedEmpIds } as never) }
    finally { setSavingEmployees(false) }
  }

  async function updateField(field: string, value: string) {
    setSavingFields(true)
    try { await updateIncident({ [field]: value } as never) }
    finally { setSavingFields(false) }
  }

  // WC classification goes through the dedicated OSHA endpoint (not the generic
  // incident update). Keeps osha_recordable true while typing the claim.
  async function saveWcClassification() {
    setSavingWc(true)
    try {
      await api.put(`/ir/incidents/${incidentId}/osha`, {
        osha_recordable: true,
        wc_claim_type: wcClaimType || undefined,
        post_termination: wcPostTerm,
        return_to_work_date: wcRtwDate || undefined,
      })
      await refetch()
    } finally { setSavingWc(false) }
  }

  async function handleDelete() {
    if (!confirm('Delete this incident? This cannot be undone.')) return
    await deleteIncident()
    navigate('/app/ir')
  }

  function handleExport() {
    // Goes through api.download so the Authorization header is attached —
    // the backend PDF endpoint uses require_admin_or_client (header JWT).
    api.download(`/ir/incidents/${incidentId}/pdf`, `incident-${incident?.incident_number}.pdf`)
      .catch(() => {})
  }

  if (loading) return <p className="text-sm text-zinc-500">Loading incident...</p>
  if (error) return <p className="text-sm text-red-400">{error}</p>
  if (!incident) return <p className="text-sm text-zinc-500">Incident not found.</p>

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col overflow-hidden rounded-xl border border-white/[0.06] bg-zinc-950">
      {/* Header */}
      <div className="shrink-0 border-b border-white/[0.06] px-5 pt-4 pb-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <Link to="/app/ir" className="text-zinc-500 hover:text-zinc-300 transition-colors">&larr;</Link>
          <span className="text-xs text-zinc-500 font-mono">{incident.incident_number}</span>
          <h1 className="text-xl font-semibold text-zinc-100 min-w-0">{incident.title}</h1>
          <Badge variant={SEVERITY_BADGE[incident.severity] ?? 'neutral'}>{severityLabel(incident.severity)}</Badge>
          <Badge variant={STATUS_BADGE[incident.status] ?? 'neutral'}>{statusLabel(incident.status)}</Badge>
        </div>
        <div className="mt-3">
          <PillTabs options={tabOptions} value={tab} onChange={setTab} />
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        {/* Main */}
        <div className="min-w-0 flex-1">
          {tab === 'copilot' ? (
            <IRCopilotPanel
              incidentId={incidentId!}
              incidentStatus={incident.status}
              reportedByName={incident.reported_by_name}
              reportedByEmail={incident.reported_by_email}
              onIncidentChanged={refetch}
              onOpenDocuments={() => setTab('documents')}
            />
          ) : (
            <div className="h-full overflow-y-auto px-5 py-4">
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

                {incident.involved_people && incident.involved_people.length > 0 && (
                  <div>
                    <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">People Involved</h3>
                    <div className="flex flex-wrap gap-1.5">
                      {incident.involved_people.map((p) => (
                        <Link
                          key={`${p.id}-${p.role}`}
                          to={`/app/ir/people/${p.id}`}
                          className="text-xs px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-200 hover:bg-zinc-700 transition-colors"
                          title={`View ${p.display_name}'s incident history`}
                        >
                          {p.display_name}
                          <span className="ml-1 text-zinc-500">· {PERSON_ROLE_LABEL[p.role]}</span>
                        </Link>
                      ))}
                    </div>
                  </div>
                )}

                {/* Roster path (employees table). Editable picker for tenants
                    with a roster; read-only hydrated names otherwise. */}
                {hasRoster ? (
                  <div>
                    <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Involved Employees</h3>
                    <EmployeeMultiSelect
                      label=""
                      value={involvedEmpIds}
                      onChange={setInvolvedEmpIds}
                      initialLabels={employeeLabels}
                      placeholder="Search employees…"
                    />
                    {[...involvedEmpIds].sort().join(',') !== [...(incident.involved_employee_ids || [])].sort().join(',') && (
                      <Button size="sm" className="mt-1" disabled={savingEmployees} onClick={saveInvolvedEmployees}>
                        {savingEmployees ? 'Saving...' : 'Save'}
                      </Button>
                    )}
                  </div>
                ) : (incident.involved_employees && incident.involved_employees.length > 0) ? (
                  <div>
                    <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Involved Employees</h3>
                    <div className="flex flex-wrap gap-1.5">
                      {incident.involved_employees.map((e) => (
                        <span key={e.id} className="text-xs px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-200">
                          {[e.first_name, e.last_name].filter(Boolean).join(' ') || `${e.id.slice(0, 8)}…`}
                          {e.job_title && <span className="ml-1 text-zinc-500">· {e.job_title}</span>}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}

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
                {/* Structured, accountable corrective actions (CAPA). The
                    free-text notes below stay as an optional catch-all. */}
                <IRCorrectiveActionsPanel incidentId={incidentId!} />

                <details className="group">
                  <summary className="text-xs font-medium text-zinc-500 uppercase tracking-wide cursor-pointer select-none hover:text-zinc-400">
                    Corrective action notes (free text)
                  </summary>
                  <div className="mt-1.5">
                    <textarea className="w-full bg-zinc-900 border border-zinc-800 rounded-lg text-sm text-zinc-200 px-3 py-2 min-h-[80px] focus:outline-none focus:border-zinc-600"
                      value={correctiveActions} onChange={(e) => setCorrectiveActions(e.target.value)} placeholder="Optional free-text notes (the tracked actions above are the record of accountability)..." />
                    {correctiveActions !== (incident.corrective_actions || '') && (
                      <Button size="sm" className="mt-1" disabled={savingFields} onClick={() => updateField('corrective_actions', correctiveActions)}>
                        {savingFields ? 'Saving...' : 'Save'}
                      </Button>
                    )}
                  </div>
                </details>

                {/* WC Classification — only for OSHA-recordable injuries; feeds broker WC analytics. */}
                {incident.osha_recordable && (
                  <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
                    <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1">WC Classification</h3>
                    <p className="text-[11px] text-zinc-600 mb-3">
                      Feeds your broker&rsquo;s Workers&rsquo; Comp analytics &mdash; claim mix, post-termination, and return-to-work.
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      <div>
                        <label className="block text-[11px] font-medium uppercase tracking-wide text-zinc-500 mb-1.5">Claim type</label>
                        <Select label="" options={WC_CLAIM_TYPE_OPTIONS} value={wcClaimType} onChange={(e) => setWcClaimType(e.target.value)} />
                      </div>
                      <div>
                        <label className="block text-[11px] font-medium uppercase tracking-wide text-zinc-500 mb-1.5">Return to work</label>
                        <input
                          type="date"
                          value={wcRtwDate}
                          onChange={(e) => setWcRtwDate(e.target.value)}
                          className="w-full bg-zinc-900 border border-zinc-800 rounded-lg text-sm text-zinc-200 px-3 py-2 focus:outline-none focus:border-zinc-600"
                        />
                      </div>
                      <div className="flex items-end">
                        <label className="inline-flex items-center gap-2 text-sm text-zinc-300 pb-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={wcPostTerm}
                            onChange={(e) => setWcPostTerm(e.target.checked)}
                            className="h-4 w-4 rounded border-zinc-700 bg-zinc-900"
                          />
                          Post-termination claim
                        </label>
                      </div>
                    </div>
                    {((wcClaimType || '') !== (incident.wc_claim_type || '') ||
                      wcPostTerm !== (incident.post_termination || false) ||
                      (wcRtwDate || '') !== (incident.return_to_work_date || '')) && (
                      <Button size="sm" className="mt-3" disabled={savingWc} onClick={saveWcClassification}>
                        {savingWc ? 'Saving...' : 'Save classification'}
                      </Button>
                    )}
                  </div>
                )}
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
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="flex w-80 shrink-0 flex-col overflow-y-auto border-l border-white/[0.06]">
          <div>
            <div className="px-5 py-3 border-b border-white/[0.06] bg-white/[0.02]">
              <h3 className={LABEL}>Incident Details</h3>
            </div>
            <div className="px-5 py-4 space-y-4">
              <div>
                <dt className={`${LABEL} mb-1.5`}>Status</dt>
                <Select label="" options={STATUS_OPTIONS} value={incident.status} onChange={(e) => updateIncident({ status: e.target.value } as never)} />
              </div>
              <div>
                <dt className={`${LABEL} mb-1.5`}>Severity</dt>
                <Select label="" options={SEVERITY_OPTIONS} value={incident.severity} onChange={(e) => updateIncident({ severity: e.target.value } as never)} />
              </div>
              <div>
                <dt className={`${LABEL} mb-1`}>Type</dt>
                <dd className="text-sm text-zinc-200">{typeLabel(incident.incident_type)}</dd>
              </div>
            </div>
          </div>

          <div className="border-t border-white/[0.06] px-5 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <dt className={`${LABEL} mb-1`}>Created</dt>
                <dd className="text-sm text-zinc-200">{new Date(incident.created_at).toLocaleDateString()}</dd>
              </div>
              <div>
                <dt className={`${LABEL} mb-1`}>Updated</dt>
                <dd className="text-sm text-zinc-200">{new Date(incident.updated_at).toLocaleDateString()}</dd>
              </div>
            </div>
            <div className="mt-4 flex items-center justify-between">
              <dt className={LABEL}>Documents</dt>
              <dd className="text-sm font-medium text-zinc-200">{incident.document_count}</dd>
            </div>
          </div>

          {showPolicyMapping && <IRPolicyMappingPanel incidentId={incidentId!} />}
          {showERFeatures && (
            <IRConsistencyGuidancePanel incidentId={incidentId!} status={incident.status} />
          )}
          {showUpsell && (
            <UpgradeUpsellCard
              source="ir_detail_upsell"
              pitch="Auto-map this incident against your handbook policies, escalate to ER Copilot, and trigger progressive discipline workflows."
              bullets={[
                'Policies + handbook mapping',
                'ER Copilot case management',
                'Progressive discipline + e-signature',
              ]}
            />
          )}

          <div className="border-t border-white/[0.06] px-5 py-4 space-y-2">
            <Button size="sm" variant="secondary" className="w-full" onClick={handleExport}>
              <Download size={12} className="mr-1.5" /> Export PDF
            </Button>
            <Button size="sm" variant="secondary" className="w-full"
              onClick={() => api.download(`/ir/incidents/${incidentId}/claims-readiness.pdf`, `claims-readiness-${incident?.incident_number}.pdf`)}>
              <Download size={12} className="mr-1.5" /> Claims-readiness packet
            </Button>
            {showERFeatures && (
              <IREscalationForm incidentId={incidentId!} incident={incident} onEscalated={(id) => navigate(`/app/er-copilot/${id}`)} />
            )}
            <button type="button" className="text-xs text-zinc-600 hover:text-red-400 transition-colors" onClick={handleDelete}>
              Delete incident
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
