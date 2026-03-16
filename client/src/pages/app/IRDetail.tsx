import { useEffect, useState, useCallback } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../../api/client'
import { Badge, Button, Card, Input, Select, FileUpload } from '../../components/ui'
import { useIRAnalysisStream } from '../../hooks/ir/useIRAnalysisStream'
import type {
  IRIncident, IRDocument, IRCategorizationAnalysis, IRRootCauseAnalysis,
  IRRecommendationsAnalysis, IRPrecedentAnalysis, IRPrecedentMatch, IRScoreBreakdown,
  IRPolicyMappingAnalysis, IRConsistencyGuidance, IRActionProbability,
  InvestigationInterview, InvestigationInterviewCreate,
} from '../../types/ir'
import {
  typeLabel, statusLabel, severityLabel,
  SEVERITY_BADGE, STATUS_BADGE, RELEVANCE_BADGE, IR_TYPE_TO_ER_CATEGORY,
} from '../../types/ir'
import type { BadgeVariant } from '../../components/ui'

// ── Constants ──

const STATUS_OPTIONS = [
  { value: 'reported', label: 'Reported' },
  { value: 'investigating', label: 'Investigating' },
  { value: 'action_required', label: 'Action Required' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'closed', label: 'Closed' },
]

const SEVERITY_OPTIONS = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
]

const DOC_TYPE_OPTIONS = [
  { value: 'photo', label: 'Photo' },
  { value: 'form', label: 'Form' },
  { value: 'statement', label: 'Statement' },
  { value: 'other', label: 'Other' },
]

const ER_CATEGORY_OPTIONS = [
  { value: 'harassment', label: 'Harassment' },
  { value: 'discrimination', label: 'Discrimination' },
  { value: 'safety', label: 'Safety' },
  { value: 'retaliation', label: 'Retaliation' },
  { value: 'policy_violation', label: 'Policy Violation' },
  { value: 'misconduct', label: 'Misconduct' },
  { value: 'wage_hour', label: 'Wage & Hour' },
  { value: 'other', label: 'Other' },
]

const INTERVIEW_ROLE_OPTIONS = [
  { value: 'complainant', label: 'Complainant' },
  { value: 'respondent', label: 'Respondent' },
  { value: 'witness', label: 'Witness' },
  { value: 'manager', label: 'Manager' },
]

type Tab = 'overview' | 'documents' | 'analysis' | 'interviews'

// ── Component ──

export default function IRDetail() {
  const { incidentId } = useParams<{ incidentId: string }>()
  const navigate = useNavigate()
  const [incident, setIncident] = useState<IRIncident | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [tab, setTab] = useState<Tab>('overview')

  const [rootCause, setRootCause] = useState('')
  const [correctiveActions, setCorrectiveActions] = useState('')
  const [savingFields, setSavingFields] = useState(false)

  const [docs, setDocs] = useState<IRDocument[]>([])
  const [loadingDocs, setLoadingDocs] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [docType, setDocType] = useState('other')

  // Sync analysis (categorization only — others are streamed)
  const [categorization, setCategorization] = useState<IRCategorizationAnalysis | null>(null)
  const [catLoading, setCatLoading] = useState(false)

  // Streaming analysis
  const stream = useIRAnalysisStream(incidentId!)
  const [rootCauseResult, setRootCauseResult] = useState<IRRootCauseAnalysis | null>(null)
  const [recsResult, setRecsResult] = useState<IRRecommendationsAnalysis | null>(null)
  const [precedentResult, setPrecedentResult] = useState<IRPrecedentAnalysis | null>(null)
  const [expandedScores, setExpandedScores] = useState<string | null>(null)

  // Sidebar panels
  const [policyMapping, setPolicyMapping] = useState<IRPolicyMappingAnalysis | null>(null)
  const [policyLoading, setPolicyLoading] = useState(false)
  const [consistencyGuidance, setConsistencyGuidance] = useState<IRConsistencyGuidance | null>(null)
  const [consistencyLoading, setConsistencyLoading] = useState(false)

  // Interviews
  const [interviews, setInterviews] = useState<InvestigationInterview[]>([])
  const [interviewsLoading, setInterviewsLoading] = useState(false)
  const [interviewRows, setInterviewRows] = useState<InvestigationInterviewCreate[]>([])
  const [interviewMsg, setInterviewMsg] = useState('')
  const [schedulingInterviews, setSchedulingInterviews] = useState(false)

  // ER escalation
  const [showEscalation, setShowEscalation] = useState(false)
  const [erForm, setErForm] = useState({ title: '', description: '', category: 'other' })
  const [escalating, setEscalating] = useState(false)

  // ── Data fetching ──

  const fetchIncident = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.get<IRIncident>(`/ir/incidents/${incidentId}`)
      setIncident(res)
      setRootCause(res.root_cause || '')
      setCorrectiveActions(res.corrective_actions || '')
    } catch { setError('Failed to load incident') }
    finally { setLoading(false) }
  }, [incidentId])

  const fetchDocs = useCallback(async () => {
    setLoadingDocs(true)
    try { setDocs(await api.get<IRDocument[]>(`/ir/incidents/${incidentId}/documents`)) }
    catch { setDocs([]) }
    finally { setLoadingDocs(false) }
  }, [incidentId])

  const fetchInterviews = useCallback(async () => {
    setInterviewsLoading(true)
    try { setInterviews(await api.get<InvestigationInterview[]>(`/ir/incidents/${incidentId}/investigation-interviews`)) }
    catch { setInterviews([]) }
    finally { setInterviewsLoading(false) }
  }, [incidentId])

  const fetchPolicyMapping = useCallback(async () => {
    setPolicyLoading(true)
    try { setPolicyMapping(await api.get<IRPolicyMappingAnalysis>(`/ir/incidents/${incidentId}/policy-mapping`)) }
    catch { setPolicyMapping(null) }
    finally { setPolicyLoading(false) }
  }, [incidentId])

  const fetchConsistency = useCallback(async () => {
    setConsistencyLoading(true)
    try { setConsistencyGuidance(await api.get<IRConsistencyGuidance>(`/ir/incidents/${incidentId}/consistency-guidance`)) }
    catch { setConsistencyGuidance(null) }
    finally { setConsistencyLoading(false) }
  }, [incidentId])

  useEffect(() => { fetchIncident() }, [fetchIncident])
  useEffect(() => { if (tab === 'documents') fetchDocs() }, [tab, fetchDocs])
  useEffect(() => { if (tab === 'interviews') fetchInterviews() }, [tab, fetchInterviews])
  useEffect(() => { fetchPolicyMapping() }, [fetchPolicyMapping])
  useEffect(() => {
    if (incident && (incident.status === 'investigating' || incident.status === 'action_required')) {
      fetchConsistency()
    }
  }, [incident?.status, fetchConsistency])

  // Capture stream results
  useEffect(() => {
    if (!stream.streaming && stream.result) {
      if (stream.analysisType === 'root-cause') setRootCauseResult(stream.result as IRRootCauseAnalysis)
      else if (stream.analysisType === 'recommendations') setRecsResult(stream.result as IRRecommendationsAnalysis)
      else if (stream.analysisType === 'similar') setPrecedentResult(stream.result as IRPrecedentAnalysis)
    }
  }, [stream.streaming, stream.result, stream.analysisType])

  // ── Handlers ──

  async function updateField(field: string, value: string) {
    setSavingFields(true)
    try {
      const updated = await api.put<IRIncident>(`/ir/incidents/${incidentId}`, { [field]: value })
      setIncident(updated)
    } finally { setSavingFields(false) }
  }

  async function handleStatusChange(status: string) {
    const updated = await api.put<IRIncident>(`/ir/incidents/${incidentId}`, { status })
    setIncident(updated)
  }

  async function handleSeverityChange(severity: string) {
    const updated = await api.put<IRIncident>(`/ir/incidents/${incidentId}`, { severity })
    setIncident(updated)
  }

  async function handleUpload(files: File[]) {
    setUploading(true)
    try {
      for (const file of files) {
        const fd = new FormData()
        fd.append('file', file)
        fd.append('document_type', docType)
        await api.upload(`/ir/incidents/${incidentId}/documents`, fd)
      }
      fetchDocs()
    } finally { setUploading(false) }
  }

  async function handleDeleteDoc(docId: string) {
    await api.delete(`/ir/incidents/${incidentId}/documents/${docId}`)
    setDocs((prev) => prev.filter((d) => d.id !== docId))
  }

  async function runCategorize() {
    setCatLoading(true)
    try { setCategorization(await api.post<IRCategorizationAnalysis>(`/ir/incidents/${incidentId}/analyze/categorize`)) }
    catch { /* silently fail */ }
    finally { setCatLoading(false) }
  }

  async function refreshPolicyMapping() {
    setPolicyLoading(true)
    try { setPolicyMapping(await api.post<IRPolicyMappingAnalysis>(`/ir/incidents/${incidentId}/analyze/policy-mapping`)) }
    catch { /* ignore */ }
    finally { setPolicyLoading(false) }
  }

  async function handleEscalateToER(e: React.FormEvent) {
    e.preventDefault()
    setEscalating(true)
    try {
      const res = await api.post<{ id: string }>('/er/cases', {
        title: erForm.title,
        description: erForm.description || null,
        category: erForm.category,
      })
      // Link the ER case to this incident
      await api.put(`/ir/incidents/${incidentId}`, { er_case_id: res.id })
      navigate(`/app/er-copilot/${res.id}`)
    } finally { setEscalating(false) }
  }

  async function handleDelete() {
    if (!confirm('Delete this incident? This cannot be undone.')) return
    await api.delete(`/ir/incidents/${incidentId}`)
    navigate('/app/ir')
  }

  async function scheduleInterviews() {
    const valid = interviewRows.filter((r) => r.interviewee_name.trim() && r.interviewee_role)
    if (valid.length === 0) return
    setSchedulingInterviews(true)
    try {
      const payload = valid.map((r) => ({
        interviewee_name: r.interviewee_name.trim(),
        interviewee_email: r.interviewee_email?.trim() || null,
        interviewee_role: r.interviewee_role,
        send_invite: !!r.interviewee_email?.trim(),
        custom_message: interviewMsg || null,
      }))
      await api.post(`/ir/incidents/${incidentId}/investigation-interviews/batch`, payload)
      setInterviewRows([])
      setInterviewMsg('')
      fetchInterviews()
    } finally { setSchedulingInterviews(false) }
  }

  async function cancelInterview(id: string) {
    await api.delete(`/ir/incidents/${incidentId}/investigation-interviews/${id}`)
    setInterviews((prev) => prev.filter((i) => i.id !== id))
  }

  async function resendInvite(id: string) {
    await api.post(`/ir/incidents/${incidentId}/investigation-interviews/${id}/resend-invite`)
  }

  function prefillFromWitnesses() {
    if (!incident?.witnesses?.length) return
    const rows: InvestigationInterviewCreate[] = incident.witnesses.map((w) => ({
      interviewee_name: w.name,
      interviewee_email: w.contact || '',
      interviewee_role: 'witness',
    }))
    setInterviewRows(rows)
  }

  // ── Render helpers ──

  function renderCategoryData() {
    if (!incident?.category_data || Object.keys(incident.category_data).length === 0) return null
    const cd = incident.category_data
    const fields: [string, unknown][] = Object.entries(cd).filter(([, v]) => v != null && v !== '' && !(Array.isArray(v) && v.length === 0))
    if (fields.length === 0) return null

    return (
      <div>
        <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">
          {typeLabel(incident.incident_type)} Details
        </h3>
        <div className="grid grid-cols-2 gap-3">
          {fields.map(([key, val]) => (
            <div key={key}>
              <dt className="text-[11px] font-medium uppercase tracking-wide text-zinc-500 mb-1">{typeLabel(key)}</dt>
              <dd className="text-sm text-zinc-200">
                {typeof val === 'boolean' ? (val ? 'Yes' : 'No') : Array.isArray(val) ? val.join(', ') : String(val)}
              </dd>
            </div>
          ))}
        </div>
      </div>
    )
  }

  function renderScoreBreakdown(sb: IRScoreBreakdown) {
    const dims: [string, number][] = [
      ['Type Match', sb.type_match],
      ['Severity', sb.severity_proximity],
      ['Category', sb.category_overlap],
      ['Location', sb.location_similarity],
      ['Temporal', sb.temporal_pattern],
      ['Text', sb.text_similarity],
      ['Root Cause', sb.root_cause_similarity],
    ]
    return (
      <div className="space-y-1 mt-2">
        {dims.map(([label, score]) => (
          <div key={label} className="flex items-center gap-2">
            <span className="text-[11px] text-zinc-500 w-20 shrink-0">{label}</span>
            <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
              <div className="h-full rounded-full bg-emerald-500/60" style={{ width: `${score * 100}%` }} />
            </div>
            <span className="text-[11px] text-zinc-600 w-8 text-right">{Math.round(score * 100)}%</span>
          </div>
        ))}
      </div>
    )
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
        <h1 className="text-xl font-semibold text-zinc-100 font-[Space_Grotesk]">{incident.title}</h1>
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
            {/* ── Overview ── */}
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

                {/* Category-specific data */}
                {renderCategoryData()}

                {/* Witnesses */}
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

                {/* Involved employees */}
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

            {/* ── Documents ── */}
            {tab === 'documents' && (
              <div className="space-y-4">
                <div className="flex items-end gap-3">
                  <div className="w-40">
                    <Select label="Document type" options={DOC_TYPE_OPTIONS} value={docType} onChange={(e) => setDocType(e.target.value)} />
                  </div>
                  <FileUpload onFiles={handleUpload} accept=".pdf,.docx,.doc,.txt,.jpg,.jpeg,.png" disabled={uploading}>
                    {uploading ? 'Uploading...' : 'Drop files here or browse'}
                  </FileUpload>
                </div>
                {loadingDocs ? (
                  <p className="text-sm text-zinc-500">Loading documents...</p>
                ) : docs.length === 0 ? (
                  <p className="text-sm text-zinc-600">No documents uploaded yet.</p>
                ) : (
                  <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
                    {docs.map((doc) => (
                      <div key={doc.id} className="flex items-center justify-between px-4 py-2.5">
                        <div>
                          <p className="text-sm text-zinc-200">{doc.filename}</p>
                          <div className="flex items-center gap-2 mt-0.5">
                            <Badge variant="neutral">{doc.document_type}</Badge>
                            {doc.file_size && <span className="text-[11px] text-zinc-600">{Math.round(doc.file_size / 1024)} KB</span>}
                          </div>
                        </div>
                        <button type="button" onClick={() => handleDeleteDoc(doc.id)}
                          className="text-xs text-zinc-600 hover:text-red-400 transition-colors">Delete</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* ── AI Analysis (streaming) ── */}
            {tab === 'analysis' && (
              <div className="space-y-6">
                {/* Categorization (sync) */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">AI Categorization</h3>
                    <Button variant="ghost" size="sm" disabled={catLoading} onClick={runCategorize}>
                      {catLoading ? 'Running...' : 'Run'}
                    </Button>
                  </div>
                  {categorization && (
                    <div className="border border-zinc-800 rounded-lg px-4 py-3 space-y-1.5">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-zinc-200">Suggested: {typeLabel(categorization.suggested_type)}</span>
                        <span className="text-[11px] text-zinc-500">{Math.round(categorization.confidence * 100)}% confidence</span>
                      </div>
                      <p className="text-xs text-zinc-500">{categorization.reasoning}</p>
                    </div>
                  )}
                </div>

                {/* Root Cause (streaming) */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">AI Root Cause Analysis</h3>
                    <Button variant="ghost" size="sm" disabled={stream.streaming}
                      onClick={() => stream.runAnalysis('root-cause')}>
                      {stream.streaming && stream.analysisType === 'root-cause' ? 'Analyzing...' : 'Run'}
                    </Button>
                  </div>
                  {stream.streaming && stream.analysisType === 'root-cause' && (
                    <div className="border border-zinc-800 rounded-lg px-4 py-3">
                      {stream.messages.map((m, i) => (
                        <p key={i} className="text-xs text-zinc-500">{m}</p>
                      ))}
                    </div>
                  )}
                  {rootCauseResult && (
                    <div className="border border-zinc-800 rounded-lg px-4 py-3 space-y-2">
                      <p className="text-sm text-zinc-200">{rootCauseResult.primary_cause}</p>
                      {rootCauseResult.contributing_factors.length > 0 && (
                        <div>
                          <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-1">Contributing Factors</p>
                          <ul className="space-y-0.5">
                            {rootCauseResult.contributing_factors.map((f, i) => <li key={i} className="text-xs text-zinc-400">- {f}</li>)}
                          </ul>
                        </div>
                      )}
                      {rootCauseResult.prevention_suggestions.length > 0 && (
                        <div>
                          <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-1">Prevention</p>
                          <ul className="space-y-0.5">
                            {rootCauseResult.prevention_suggestions.map((s, i) => <li key={i} className="text-xs text-zinc-400">- {s}</li>)}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Recommendations (streaming) */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">AI Recommendations</h3>
                    <Button variant="ghost" size="sm" disabled={stream.streaming}
                      onClick={() => stream.runAnalysis('recommendations')}>
                      {stream.streaming && stream.analysisType === 'recommendations' ? 'Analyzing...' : 'Run'}
                    </Button>
                  </div>
                  {stream.streaming && stream.analysisType === 'recommendations' && (
                    <div className="border border-zinc-800 rounded-lg px-4 py-3">
                      {stream.messages.map((m, i) => (
                        <p key={i} className="text-xs text-zinc-500">{m}</p>
                      ))}
                    </div>
                  )}
                  {recsResult && (
                    <div className="border border-zinc-800 rounded-lg px-4 py-3 space-y-2">
                      <p className="text-xs text-zinc-400">{recsResult.summary}</p>
                      <div className="space-y-2">
                        {recsResult.recommendations.map((rec, i) => (
                          <div key={i} className="flex items-start gap-2">
                            <Badge variant={rec.priority === 'immediate' ? 'danger' : rec.priority === 'short_term' ? 'warning' : 'neutral'}>
                              {rec.priority.replace(/_/g, ' ')}
                            </Badge>
                            <div>
                              <p className="text-sm text-zinc-200">{rec.action}</p>
                              {rec.responsible_party && <p className="text-[11px] text-zinc-500">{rec.responsible_party}</p>}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {/* Similar Incidents (streaming) */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Similar Incidents</h3>
                    <Button variant="ghost" size="sm" disabled={stream.streaming}
                      onClick={() => stream.runAnalysis('similar')}>
                      {stream.streaming && stream.analysisType === 'similar' ? 'Searching...' : 'Find Similar'}
                    </Button>
                  </div>
                  {stream.streaming && stream.analysisType === 'similar' && (
                    <div className="border border-zinc-800 rounded-lg px-4 py-3">
                      {stream.messages.map((m, i) => (
                        <p key={i} className="text-xs text-zinc-500">{m}</p>
                      ))}
                    </div>
                  )}
                  {precedentResult && (
                    <div className="space-y-3">
                      {precedentResult.pattern_summary && (
                        <div className="rounded-lg bg-zinc-900/50 border border-zinc-800 px-4 py-3">
                          <p className="text-sm text-zinc-300">{precedentResult.pattern_summary}</p>
                        </div>
                      )}
                      {precedentResult.precedents.length === 0 && (
                        <p className="text-sm text-zinc-400 text-center py-4">No similar incidents found.</p>
                      )}
                      {precedentResult.precedents.map((p: IRPrecedentMatch) => (
                        <div key={p.incident_id} className="border border-zinc-800 rounded-lg p-4 space-y-2">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="text-xs font-mono text-zinc-500">{p.incident_number}</span>
                              <h4 className="text-sm font-medium text-zinc-100 truncate">{p.title}</h4>
                            </div>
                            <span className="text-sm font-mono text-emerald-400 shrink-0">{Math.round(p.similarity_score * 100)}%</span>
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            <Badge variant="neutral">{typeLabel(p.incident_type)}</Badge>
                            <Badge variant={SEVERITY_BADGE[p.severity] ?? 'neutral'}>{severityLabel(p.severity)}</Badge>
                            <Badge variant={STATUS_BADGE[p.status] ?? 'neutral'}>{statusLabel(p.status)}</Badge>
                            {p.resolution_days != null && (
                              <span className="text-[11px] text-zinc-500">{p.resolution_days}d to resolve</span>
                            )}
                          </div>
                          {p.common_factors.length > 0 && (
                            <div className="flex flex-wrap gap-1.5">
                              {p.common_factors.map((f, i) => (
                                <span key={i} className="text-[11px] px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400">{f}</span>
                              ))}
                            </div>
                          )}
                          <button type="button" onClick={() => setExpandedScores(expandedScores === p.incident_id ? null : p.incident_id)}
                            className="text-[11px] text-zinc-600 hover:text-zinc-400 transition-colors">
                            {expandedScores === p.incident_id ? 'Hide score breakdown' : 'Show score breakdown'}
                          </button>
                          {expandedScores === p.incident_id && renderScoreBreakdown(p.score_breakdown)}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Stream error */}
                {stream.error && <p className="text-xs text-red-400">{stream.error}</p>}
              </div>
            )}

            {/* ── Interviews ── */}
            {tab === 'interviews' && (
              <div className="space-y-5">
                {/* Existing interviews */}
                {interviewsLoading ? (
                  <p className="text-sm text-zinc-500">Loading interviews...</p>
                ) : interviews.length === 0 ? (
                  <p className="text-sm text-zinc-600">No investigation interviews scheduled yet.</p>
                ) : (
                  <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
                    {interviews.map((iv) => (
                      <div key={iv.id} className="px-4 py-3">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-zinc-200">{iv.interviewee_name}</span>
                            {iv.interviewee_role && <Badge variant="neutral">{iv.interviewee_role}</Badge>}
                            <Badge variant={iv.status === 'completed' ? 'success' : iv.status === 'pending' ? 'warning' : 'neutral' as BadgeVariant}>
                              {iv.status}
                            </Badge>
                          </div>
                          <div className="flex items-center gap-2">
                            {iv.status === 'pending' && iv.interviewee_email && (
                              <button type="button" onClick={() => resendInvite(iv.id)} className="text-xs text-zinc-500 hover:text-zinc-300">Resend</button>
                            )}
                            {iv.status === 'pending' && (
                              <button type="button" onClick={() => cancelInterview(iv.id)} className="text-xs text-zinc-600 hover:text-red-400">Cancel</button>
                            )}
                          </div>
                        </div>
                        {iv.interviewee_email && <p className="text-xs text-zinc-500 mt-0.5">{iv.interviewee_email}</p>}
                        <p className="text-[11px] text-zinc-600 mt-0.5">Created {new Date(iv.created_at).toLocaleDateString()}</p>
                      </div>
                    ))}
                  </div>
                )}

                {/* Schedule new interviews */}
                <div className="border border-zinc-800 rounded-lg p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Schedule Interviews</p>
                    <div className="flex items-center gap-2">
                      {incident.witnesses && incident.witnesses.length > 0 && (
                        <button type="button" onClick={prefillFromWitnesses} className="text-xs text-emerald-400 hover:text-emerald-300">
                          Pre-fill from witnesses
                        </button>
                      )}
                      <button type="button" onClick={() => setInterviewRows([...interviewRows, { interviewee_name: '', interviewee_email: '', interviewee_role: 'witness' }])}
                        className="text-xs text-emerald-400 hover:text-emerald-300">+ Add</button>
                    </div>
                  </div>
                  {interviewRows.map((row, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <Input label="" placeholder="Name" value={row.interviewee_name}
                        onChange={(e) => { const copy = [...interviewRows]; copy[i] = { ...copy[i], interviewee_name: e.target.value }; setInterviewRows(copy) }} className="flex-1" />
                      <Input label="" placeholder="Email" value={row.interviewee_email || ''}
                        onChange={(e) => { const copy = [...interviewRows]; copy[i] = { ...copy[i], interviewee_email: e.target.value }; setInterviewRows(copy) }} className="flex-1" />
                      <div className="w-32">
                        <Select label="" options={INTERVIEW_ROLE_OPTIONS} value={row.interviewee_role}
                          onChange={(e) => { const copy = [...interviewRows]; copy[i] = { ...copy[i], interviewee_role: e.target.value }; setInterviewRows(copy) }} />
                      </div>
                      <button type="button" onClick={() => setInterviewRows(interviewRows.filter((_, j) => j !== i))}
                        className="text-xs text-zinc-600 hover:text-red-400">&times;</button>
                    </div>
                  ))}
                  {interviewRows.length > 0 && (
                    <>
                      <textarea
                        className="w-full bg-zinc-900 border border-zinc-800 rounded-lg text-sm text-zinc-200 px-3 py-2 min-h-[60px] focus:outline-none focus:border-zinc-600"
                        value={interviewMsg}
                        onChange={(e) => setInterviewMsg(e.target.value)}
                        placeholder="Custom message for invite emails (optional)"
                      />
                      <Button size="sm" disabled={schedulingInterviews} onClick={scheduleInterviews}>
                        {schedulingInterviews ? 'Scheduling...' : `Schedule ${interviewRows.filter((r) => r.interviewee_name.trim()).length} Interview(s)`}
                      </Button>
                    </>
                  )}
                </div>
              </div>
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
                <Select label="" options={STATUS_OPTIONS} value={incident.status} onChange={(e) => handleStatusChange(e.target.value)} />
              </div>
              <div>
                <dt className="text-[11px] font-medium uppercase tracking-wide text-zinc-500 mb-1.5">Severity</dt>
                <Select label="" options={SEVERITY_OPTIONS} value={incident.severity} onChange={(e) => handleSeverityChange(e.target.value)} />
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

          {/* Policy Mapping sidebar panel */}
          <Card className="p-0 overflow-hidden">
            <div className="px-5 py-3 border-b border-zinc-800/60 bg-zinc-900/40 flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Policy Mapping</h3>
              <Button variant="ghost" size="sm" disabled={policyLoading} onClick={refreshPolicyMapping}>
                {policyLoading ? '...' : 'Refresh'}
              </Button>
            </div>
            <div className="px-5 py-4">
              {policyLoading && !policyMapping ? (
                <p className="text-xs text-zinc-500">Analyzing policies...</p>
              ) : !policyMapping || policyMapping.no_matching_policies ? (
                <p className="text-xs text-zinc-600">{policyMapping?.summary || 'No policy mapping available.'}</p>
              ) : (
                <div className="space-y-3">
                  <p className="text-xs text-zinc-400">{policyMapping.summary}</p>
                  {policyMapping.matches.map((m) => (
                    <div key={m.policy_id} className="border border-zinc-800 rounded-lg p-3 space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-zinc-200">{m.policy_title}</span>
                        <Badge variant={RELEVANCE_BADGE[m.relevance] ?? 'neutral'}>{m.relevance}</Badge>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                          <div className="h-full rounded-full bg-emerald-500/60" style={{ width: `${m.confidence * 100}%` }} />
                        </div>
                        <span className="text-[11px] text-zinc-500">{Math.round(m.confidence * 100)}%</span>
                      </div>
                      <p className="text-xs text-zinc-500">{m.reasoning}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>

          {/* Consistency Guidance sidebar panel */}
          {(incident.status === 'investigating' || incident.status === 'action_required') && (
            <Card className="p-0 overflow-hidden">
              <div className="px-5 py-3 border-b border-zinc-800/60 bg-zinc-900/40">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Consistency Guidance</h3>
              </div>
              <div className="px-5 py-4">
                {consistencyLoading && !consistencyGuidance ? (
                  <p className="text-xs text-zinc-500">Loading guidance...</p>
                ) : !consistencyGuidance || consistencyGuidance.unprecedented ? (
                  <p className="text-xs text-zinc-600">
                    {consistencyGuidance?.unprecedented ? 'No precedent found for this type of incident.' : 'No consistency guidance available.'}
                  </p>
                ) : (
                  <div className="space-y-3">
                    {/* Action distribution */}
                    {consistencyGuidance.action_distribution && consistencyGuidance.action_distribution.length > 0 && (
                      <div className="space-y-1.5">
                        <p className="text-[11px] text-zinc-500 uppercase tracking-wide">Actions Taken</p>
                        {(() => {
                          const max = Math.max(...consistencyGuidance.action_distribution!.map((a: IRActionProbability) => a.probability), 0.01)
                          return consistencyGuidance.action_distribution!.map((a: IRActionProbability) => (
                            <div key={a.category} className="flex items-center gap-2">
                              <span className="text-[11px] text-zinc-400 w-24 shrink-0 truncate">{typeLabel(a.category)}</span>
                              <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                                <div className="h-full rounded-full bg-emerald-500/60" style={{ width: `${(a.probability / max) * 100}%` }} />
                              </div>
                              <span className="text-[11px] text-zinc-600 w-8 text-right">{Math.round(a.probability * 100)}%</span>
                            </div>
                          ))
                        })()}
                      </div>
                    )}
                    <div className="grid grid-cols-2 gap-3">
                      {consistencyGuidance.weighted_effectiveness_rate != null && (
                        <div className="text-center">
                          <p className="text-sm font-semibold text-zinc-100">{Math.round(consistencyGuidance.weighted_effectiveness_rate * 100)}%</p>
                          <p className="text-[11px] text-zinc-500">Effectiveness</p>
                        </div>
                      )}
                      {consistencyGuidance.weighted_avg_resolution_days != null && (
                        <div className="text-center">
                          <p className="text-sm font-semibold text-zinc-100">{Math.round(consistencyGuidance.weighted_avg_resolution_days)}d</p>
                          <p className="text-[11px] text-zinc-500">Avg Resolution</p>
                        </div>
                      )}
                    </div>
                    {consistencyGuidance.consistency_insight && (
                      <p className="text-xs text-zinc-400 italic">{consistencyGuidance.consistency_insight}</p>
                    )}
                    <p className="text-[11px] text-zinc-600">
                      Confidence: {consistencyGuidance.confidence} ({consistencyGuidance.sample_size} samples)
                    </p>
                  </div>
                )}
              </div>
            </Card>
          )}

          {/* Actions */}
          <div className="space-y-2 pt-2">
            {!incident.er_case_id && !showEscalation && (
              <Button variant="secondary" size="sm" className="w-full" onClick={() => {
                setErForm({
                  title: `ER Escalation: ${incident.title}`,
                  description: incident.description || '',
                  category: IR_TYPE_TO_ER_CATEGORY[incident.incident_type] || 'other',
                })
                setShowEscalation(true)
              }}>
                Escalate to ER Case
              </Button>
            )}
            {showEscalation && !incident.er_case_id && (
              <Card className="p-4">
                <form onSubmit={handleEscalateToER} className="space-y-3">
                  <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Create ER Case</p>
                  <Input label="Title" required value={erForm.title} onChange={(e) => setErForm({ ...erForm, title: e.target.value })} />
                  <textarea
                    className="w-full bg-zinc-900 border border-zinc-800 rounded-lg text-sm text-zinc-200 px-3 py-2 min-h-[60px] focus:outline-none focus:border-zinc-600"
                    value={erForm.description}
                    onChange={(e) => setErForm({ ...erForm, description: e.target.value })}
                    placeholder="Description..."
                  />
                  <Select label="Category" options={ER_CATEGORY_OPTIONS} value={erForm.category} onChange={(e) => setErForm({ ...erForm, category: e.target.value })} />
                  <div className="flex justify-end gap-2">
                    <Button variant="ghost" size="sm" type="button" onClick={() => setShowEscalation(false)}>Cancel</Button>
                    <Button size="sm" type="submit" disabled={escalating}>{escalating ? 'Creating...' : 'Create ER Case'}</Button>
                  </div>
                </form>
              </Card>
            )}
            {incident.er_case_id && (
              <Link to={`/app/er-copilot/${incident.er_case_id}`}>
                <Button variant="ghost" size="sm" className="w-full">View ER Case</Button>
              </Link>
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
