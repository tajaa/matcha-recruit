import { useEffect, useState, useCallback } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../../api/client'
import { Badge, Button, Card, Select, FileUpload, type BadgeVariant } from '../../components/ui'

// ── Types ──────────────────────────────────────────────────────────────────────

type IRIncidentType = 'safety' | 'behavioral' | 'property' | 'near_miss' | 'other'
type IRSeverity = 'low' | 'medium' | 'high' | 'critical'
type IRStatus = 'reported' | 'investigating' | 'action_required' | 'resolved' | 'closed'

type IRIncident = {
  id: string; incident_number: string; title: string; description: string
  incident_type: IRIncidentType; severity: IRSeverity; status: IRStatus
  location: string | null; reported_by_name: string | null
  is_anonymous: boolean; date_occurred: string | null
  root_cause: string | null; corrective_actions: string | null
  er_case_id: string | null; document_count: number
  created_at: string; updated_at: string
}

type IRDocument = {
  id: string; incident_id: string; document_type: string
  filename: string; file_size: number | null; created_at: string
}

type RootCauseAnalysis = {
  primary_cause: string; contributing_factors: string[]
  prevention_suggestions: string[]; reasoning: string
}

type RecommendationsAnalysis = {
  recommendations: { action: string; priority: string; responsible_party?: string }[]
  summary: string
}

type CategorizationAnalysis = {
  suggested_type: string; confidence: number; reasoning: string
}

type Tab = 'overview' | 'documents' | 'analysis'

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

const severityVariant: Record<string, BadgeVariant> = {
  critical: 'danger', high: 'danger', medium: 'warning', low: 'neutral',
}
const statusVariant: Record<string, BadgeVariant> = {
  reported: 'neutral', investigating: 'warning', action_required: 'danger', resolved: 'success', closed: 'neutral',
}

// ── Component ──────────────────────────────────────────────────────────────────

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

  const [categorization, setCategorization] = useState<CategorizationAnalysis | null>(null)
  const [rootCauseAnalysis, setRootCauseAnalysis] = useState<RootCauseAnalysis | null>(null)
  const [recommendations, setRecommendations] = useState<RecommendationsAnalysis | null>(null)
  const [analysisLoading, setAnalysisLoading] = useState<string | null>(null)

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

  useEffect(() => { fetchIncident() }, [fetchIncident])
  useEffect(() => { if (tab === 'documents') fetchDocs() }, [tab, fetchDocs])

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

  async function runAnalysis(type: 'categorize' | 'root-cause' | 'recommendations') {
    setAnalysisLoading(type)
    try {
      if (type === 'categorize') {
        setCategorization(await api.post<CategorizationAnalysis>(`/ir/incidents/${incidentId}/analyze/categorize`))
      } else if (type === 'root-cause') {
        setRootCauseAnalysis(await api.post<RootCauseAnalysis>(`/ir/incidents/${incidentId}/analyze/root-cause`))
      } else {
        setRecommendations(await api.post<RecommendationsAnalysis>(`/ir/incidents/${incidentId}/analyze/recommendations`))
      }
    } catch { /* silently fail */ }
    finally { setAnalysisLoading(null) }
  }

  async function escalateToER() {
    if (!confirm('Escalate this incident to an ER case?')) return
    const res = await api.post<{ er_case_id: string }>(`/ir/incidents/${incidentId}/er-case`)
    navigate(`/app/er-copilot/${res.er_case_id}`)
  }

  async function handleDelete() {
    if (!confirm('Delete this incident? This cannot be undone.')) return
    await api.delete(`/ir/incidents/${incidentId}`)
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
        <h1 className="text-xl font-semibold text-zinc-100 font-[Space_Grotesk]">{incident.title}</h1>
        <Badge variant={severityVariant[incident.severity] ?? 'neutral'}>{incident.severity}</Badge>
        <Badge variant={statusVariant[incident.status] ?? 'neutral'}>{incident.status.replace(/_/g, ' ')}</Badge>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Main */}
        <div className="col-span-2">
          <div className="flex gap-1 mb-4">
            {(['overview', 'documents', 'analysis'] as const).map((t) => (
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
                  {incident.date_occurred && (
                    <div>
                      <dt className="text-[11px] font-medium uppercase tracking-wide text-zinc-500 mb-1">Date Occurred</dt>
                      <dd className="text-sm text-zinc-200">{new Date(incident.date_occurred).toLocaleDateString()}</dd>
                    </div>
                  )}
                </div>
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

            {/* ── AI Analysis ── */}
            {tab === 'analysis' && (
              <div className="space-y-6">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">AI Categorization</h3>
                    <Button variant="ghost" size="sm" disabled={analysisLoading !== null} onClick={() => runAnalysis('categorize')}>
                      {analysisLoading === 'categorize' ? 'Running...' : 'Run'}
                    </Button>
                  </div>
                  {categorization && (
                    <div className="border border-zinc-800 rounded-lg px-4 py-3 space-y-1.5">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-zinc-200">Suggested: {categorization.suggested_type}</span>
                        <span className="text-[11px] text-zinc-500">{Math.round(categorization.confidence * 100)}% confidence</span>
                      </div>
                      <p className="text-xs text-zinc-500">{categorization.reasoning}</p>
                    </div>
                  )}
                </div>
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">AI Root Cause Analysis</h3>
                    <Button variant="ghost" size="sm" disabled={analysisLoading !== null} onClick={() => runAnalysis('root-cause')}>
                      {analysisLoading === 'root-cause' ? 'Running...' : 'Run'}
                    </Button>
                  </div>
                  {rootCauseAnalysis && (
                    <div className="border border-zinc-800 rounded-lg px-4 py-3 space-y-2">
                      <p className="text-sm text-zinc-200">{rootCauseAnalysis.primary_cause}</p>
                      {rootCauseAnalysis.contributing_factors.length > 0 && (
                        <div>
                          <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-1">Contributing Factors</p>
                          <ul className="space-y-0.5">
                            {rootCauseAnalysis.contributing_factors.map((f, i) => <li key={i} className="text-xs text-zinc-400">- {f}</li>)}
                          </ul>
                        </div>
                      )}
                      {rootCauseAnalysis.prevention_suggestions.length > 0 && (
                        <div>
                          <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-1">Prevention</p>
                          <ul className="space-y-0.5">
                            {rootCauseAnalysis.prevention_suggestions.map((s, i) => <li key={i} className="text-xs text-zinc-400">- {s}</li>)}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </div>
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">AI Recommendations</h3>
                    <Button variant="ghost" size="sm" disabled={analysisLoading !== null} onClick={() => runAnalysis('recommendations')}>
                      {analysisLoading === 'recommendations' ? 'Running...' : 'Run'}
                    </Button>
                  </div>
                  {recommendations && (
                    <div className="border border-zinc-800 rounded-lg px-4 py-3 space-y-2">
                      <p className="text-xs text-zinc-400">{recommendations.summary}</p>
                      <div className="space-y-2">
                        {recommendations.recommendations.map((rec, i) => (
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
                <dd className="text-sm text-zinc-200">{incident.incident_type.replace(/_/g, ' ')}</dd>
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
          <div className="space-y-2 pt-2">
            {!incident.er_case_id && (
              <Button variant="secondary" size="sm" className="w-full" onClick={escalateToER}>Escalate to ER Case</Button>
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
