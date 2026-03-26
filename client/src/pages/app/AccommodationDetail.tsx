import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../../api/client'
import { Badge, Button, Card } from '../../components/ui'
import { Loader2, Upload, FileText, Brain } from 'lucide-react'
import { NoteThread } from '../../components/NoteThread'

type AccommodationCase = {
  id: string; case_number: string; org_id: string; employee_id: string
  title: string; description: string | null; disability_category: string | null
  status: string; requested_accommodation: string | null
  approved_accommodation: string | null; denial_reason: string | null
  undue_hardship_analysis: string | null; assigned_to: string | null
  document_count: number; created_at: string; updated_at: string; closed_at: string | null
}

type Doc = { id: string; document_type: string; filename: string; file_url: string | null; created_at: string }
type Analysis = { analysis_type: string; analysis_data: Record<string, unknown>; generated_at: string }

const STATUS_BADGE: Record<string, 'success' | 'warning' | 'danger' | 'neutral'> = {
  requested: 'warning', interactive_process: 'warning', medical_review: 'warning',
  approved: 'success', implemented: 'success', review: 'neutral', denied: 'danger', closed: 'neutral',
}
const STATUS_LABEL: Record<string, string> = {
  requested: 'Requested', interactive_process: 'Interactive Process', medical_review: 'Medical Review',
  approved: 'Approved', implemented: 'Implemented', review: 'Under Review', denied: 'Denied', closed: 'Closed',
}
const STEPS = ['Requested', 'Medical Review', 'Interactive Process', 'Determination', 'Implementation']

type Tab = 'overview' | 'documents' | 'analysis' | 'notes'

export default function AccommodationDetail() {
  const { caseId } = useParams<{ caseId: string }>()
  const [accase, setCase] = useState<AccommodationCase | null>(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<Tab>('overview')
  const [docs, setDocs] = useState<Doc[]>([])
  const [docsLoading, setDocsLoading] = useState(false)
  const [suggestions, setSuggestions] = useState<Analysis | null>(null)
  const [hardship, setHardship] = useState<Analysis | null>(null)
  const [analyzing, setAnalyzing] = useState<string | null>(null)
  const [statusUpdating, setStatusUpdating] = useState(false)

  useEffect(() => {
    if (!caseId) return
    setLoading(true)
    api.get<AccommodationCase>(`/accommodations/${caseId}`)
      .then(setCase)
      .catch(() => setCase(null))
      .finally(() => setLoading(false))
  }, [caseId])

  useEffect(() => {
    if (tab === 'documents' && caseId) {
      setDocsLoading(true)
      api.get<Doc[]>(`/accommodations/${caseId}/documents`)
        .then(setDocs)
        .catch(() => setDocs([]))
        .finally(() => setDocsLoading(false))
    }
  }, [tab, caseId])

  async function updateStatus(newStatus: string) {
    if (!caseId) return
    setStatusUpdating(true)
    try {
      const updated = await api.put<AccommodationCase>(`/accommodations/${caseId}`, { status: newStatus })
      setCase(updated)
    } catch {}
    setStatusUpdating(false)
  }

  async function runAnalysis(type: 'suggestions' | 'hardship' | 'job-functions') {
    if (!caseId) return
    setAnalyzing(type)
    try {
      const res = await api.post<Analysis>(`/accommodations/${caseId}/analysis/${type}`)
      if (type === 'suggestions') setSuggestions(res)
      if (type === 'hardship') setHardship(res)
    } catch {}
    setAnalyzing(null)
  }

  async function uploadDoc(file: File, docType: string) {
    if (!caseId) return
    const form = new FormData()
    form.append('file', file)
    form.append('document_type', docType)
    await api.post(`/accommodations/${caseId}/documents`, form)
    const updated = await api.get<Doc[]>(`/accommodations/${caseId}/documents`)
    setDocs(updated)
  }

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="animate-spin text-zinc-500" size={20} /></div>
  if (!accase) return <div className="text-center py-12 text-zinc-500">Case not found</div>

  const stepIdx = accase.status === 'requested' ? 0
    : accase.status === 'medical_review' ? 1
    : accase.status === 'interactive_process' ? 2
    : ['approved', 'denied', 'review'].includes(accase.status) ? 3
    : ['implemented', 'closed'].includes(accase.status) ? 4 : 0

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <Link to="/app/accommodations" className="text-zinc-500 hover:text-zinc-300">&larr;</Link>
        <span className="text-xs text-zinc-500 font-mono">{accase.case_number}</span>
        <h1 className="text-xl font-semibold text-zinc-100">{accase.title}</h1>
        <Badge variant={STATUS_BADGE[accase.status] ?? 'neutral'}>
          {STATUS_LABEL[accase.status] ?? accase.status}
        </Badge>
      </div>

      {/* Step progress */}
      <div className="flex items-center gap-1 mb-6">
        {STEPS.map((s, i) => (
          <div key={s} className="flex items-center gap-1 flex-1">
            <div className={`h-1.5 flex-1 rounded-full ${i <= stepIdx ? 'bg-emerald-500' : 'bg-zinc-800'}`} />
            <span className={`text-[10px] ${i <= stepIdx ? 'text-emerald-400' : 'text-zinc-600'}`}>{s}</span>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-5">
        {(['overview', 'documents', 'analysis', 'notes'] as const).map((t) => (
          <Button key={t} variant={tab === t ? 'secondary' : 'ghost'} size="sm" onClick={() => setTab(t)}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </Button>
        ))}
      </div>

      {/* Overview tab */}
      {tab === 'overview' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card className="p-4 space-y-3">
            <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wider">Request Details</h3>
            {accase.description && <p className="text-sm text-zinc-300">{accase.description}</p>}
            {accase.disability_category && (
              <div><span className="text-xs text-zinc-500">Category:</span> <span className="text-sm text-zinc-200 capitalize">{accase.disability_category.replace('_', ' ')}</span></div>
            )}
            {accase.requested_accommodation && (
              <div><span className="text-xs text-zinc-500">Requested:</span> <p className="text-sm text-zinc-300 mt-0.5">{accase.requested_accommodation}</p></div>
            )}
            {accase.approved_accommodation && (
              <div><span className="text-xs text-zinc-500">Approved:</span> <p className="text-sm text-emerald-300 mt-0.5">{accase.approved_accommodation}</p></div>
            )}
            {accase.denial_reason && (
              <div><span className="text-xs text-zinc-500">Denial reason:</span> <p className="text-sm text-red-300 mt-0.5">{accase.denial_reason}</p></div>
            )}
          </Card>

          <Card className="p-4 space-y-3">
            <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wider">Workflow Actions</h3>
            <div className="space-y-2">
              {accase.status === 'requested' && (
                <>
                  <Button size="sm" className="w-full" onClick={() => updateStatus('interactive_process')} disabled={statusUpdating}>
                    Begin Interactive Process
                  </Button>
                  <Button size="sm" variant="ghost" className="w-full" onClick={() => updateStatus('medical_review')} disabled={statusUpdating}>
                    Request Medical Documentation
                  </Button>
                </>
              )}
              {accase.status === 'medical_review' && (
                <Button size="sm" className="w-full" onClick={() => updateStatus('interactive_process')} disabled={statusUpdating}>
                  Documentation Received — Begin Interactive Process
                </Button>
              )}
              {accase.status === 'interactive_process' && (
                <>
                  <Button size="sm" className="w-full" onClick={() => updateStatus('approved')} disabled={statusUpdating}>
                    Approve Accommodation
                  </Button>
                  <Button size="sm" variant="ghost" className="w-full" onClick={() => updateStatus('denied')} disabled={statusUpdating}>
                    Deny (Document Reason)
                  </Button>
                </>
              )}
              {accase.status === 'approved' && (
                <Button size="sm" className="w-full" onClick={() => updateStatus('implemented')} disabled={statusUpdating}>
                  Mark as Implemented
                </Button>
              )}
              {accase.status === 'implemented' && (
                <Button size="sm" className="w-full" onClick={() => updateStatus('review')} disabled={statusUpdating}>
                  Schedule 30-Day Review
                </Button>
              )}
              {!['closed', 'denied'].includes(accase.status) && (
                <Button size="sm" variant="ghost" className="w-full text-zinc-500" onClick={() => updateStatus('closed')} disabled={statusUpdating}>
                  Close Case
                </Button>
              )}
            </div>
          </Card>

          {accase.undue_hardship_analysis && (
            <Card className="p-4 md:col-span-2">
              <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wider mb-2">Undue Hardship Analysis</h3>
              <p className="text-sm text-zinc-300 whitespace-pre-wrap">{accase.undue_hardship_analysis}</p>
            </Card>
          )}
        </div>
      )}

      {/* Documents tab */}
      {tab === 'documents' && (
        <div className="space-y-4">
          <div className="flex gap-2">
            {['medical_certification', 'job_description', 'interactive_process_notes', 'other'].map((docType) => (
              <label key={docType} className="cursor-pointer">
                <input
                  type="file"
                  className="hidden"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadDoc(f, docType); e.target.value = '' }}
                />
                <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded border border-zinc-700 bg-zinc-800 text-zinc-400 hover:text-zinc-200 hover:border-zinc-500 transition-colors">
                  <Upload size={10} />
                  {docType.replace(/_/g, ' ')}
                </span>
              </label>
            ))}
          </div>
          {docsLoading ? (
            <p className="text-sm text-zinc-500">Loading...</p>
          ) : docs.length === 0 ? (
            <p className="text-sm text-zinc-500">No documents uploaded yet.</p>
          ) : (
            <div className="space-y-2">
              {docs.map((d) => (
                <div key={d.id} className="flex items-center gap-3 p-3 border border-zinc-800 rounded-lg">
                  <FileText size={16} className="text-zinc-500" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-zinc-200 truncate">{d.filename}</p>
                    <p className="text-[10px] text-zinc-500">{d.document_type.replace(/_/g, ' ')} · {new Date(d.created_at).toLocaleDateString()}</p>
                  </div>
                  {d.file_url && (
                    <a href={d.file_url} target="_blank" rel="noopener noreferrer" className="text-xs text-cyan-500 hover:text-cyan-400">
                      View
                    </a>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Analysis tab */}
      {tab === 'analysis' && (
        <div className="space-y-4">
          <div className="flex gap-2">
            <Button size="sm" variant="ghost" onClick={() => runAnalysis('suggestions')} disabled={!!analyzing}>
              <Brain size={12} className="mr-1" />
              {analyzing === 'suggestions' ? 'Analyzing...' : 'AI Accommodation Suggestions'}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => runAnalysis('hardship')} disabled={!!analyzing}>
              <Brain size={12} className="mr-1" />
              {analyzing === 'hardship' ? 'Analyzing...' : 'Undue Hardship Assessment'}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => runAnalysis('job-functions')} disabled={!!analyzing}>
              <Brain size={12} className="mr-1" />
              {analyzing === 'job-functions' ? 'Analyzing...' : 'Job Function Analysis'}
            </Button>
          </div>
          {suggestions && (
            <Card className="p-4">
              <h4 className="text-xs font-medium text-zinc-400 uppercase tracking-wider mb-2">Accommodation Suggestions</h4>
              <pre className="text-sm text-zinc-300 whitespace-pre-wrap">{JSON.stringify(suggestions.analysis_data, null, 2)}</pre>
            </Card>
          )}
          {hardship && (
            <Card className="p-4">
              <h4 className="text-xs font-medium text-zinc-400 uppercase tracking-wider mb-2">Hardship Assessment</h4>
              <pre className="text-sm text-zinc-300 whitespace-pre-wrap">{JSON.stringify(hardship.analysis_data, null, 2)}</pre>
            </Card>
          )}
        </div>
      )}

      {/* Notes tab */}
      {tab === 'notes' && caseId && (
        <NoteThread endpoint={`/accommodations/${caseId}/audit-log`} />
      )}
    </div>
  )
}
