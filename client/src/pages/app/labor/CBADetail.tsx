import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Badge, Button, Card, FileUpload, Input, Modal, Select, Textarea } from '../../../components/ui'
import {
  ArrowLeft, Loader2, Upload, Download, Sparkles, Plus, Trash2, Check, ShieldCheck, AlertTriangle,
} from 'lucide-react'
import { laborApi } from '../../../api/hr/laborClient'
import type { CBADetail as CBADetailType, Clause, ClauseCategory } from '../../../api/hr/laborClient'
import { CBA_STATUS_VARIANT, CLAUSE_CATEGORY_LABEL, CLAUSE_CATEGORY_OPTIONS } from '../../../data/laborLabels'

export default function CBADetail() {
  const { cbaId } = useParams<{ cbaId: string }>()
  const navigate = useNavigate()
  const [cba, setCba] = useState<CBADetailType | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [showAddClause, setShowAddClause] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback(async () => {
    if (!cbaId) return
    try {
      setCba(await laborApi.getCba(cbaId))
    } catch {
      setError('Could not load CBA.')
    } finally {
      setLoading(false)
    }
  }, [cbaId])

  useEffect(() => { load() }, [load])

  // Poll while extraction is running.
  useEffect(() => {
    if (cba?.extraction_status === 'processing') {
      pollRef.current = setInterval(load, 4000)
      return () => { if (pollRef.current) clearInterval(pollRef.current) }
    }
    if (pollRef.current) clearInterval(pollRef.current)
  }, [cba?.extraction_status, load])

  async function handleUpload(file: File) {
    if (!cbaId) return
    setBusy(true); setError('')
    try {
      await laborApi.uploadCbaDocument(cbaId, file)
      await load()
    } catch {
      setError('Upload failed.')
    } finally {
      setBusy(false)
    }
  }

  async function handleDownload() {
    if (!cbaId) return
    try {
      const { url } = await laborApi.getCbaDocumentUrl(cbaId)
      window.open(url, '_blank', 'noopener')
    } catch {
      setError('No document available.')
    }
  }

  async function handleReextract() {
    if (!cbaId) return
    setBusy(true)
    try {
      await laborApi.extractClauses(cbaId)
      await load()
    } catch {
      setError('Could not start extraction.')
    } finally {
      setBusy(false)
    }
  }

  async function confirmProcedure() {
    if (!cbaId) return
    try {
      await laborApi.updateCba(cbaId, { grievance_steps_confirmed: true })
      await load()
    } catch {
      setError('Could not confirm procedure.')
    }
  }

  if (loading) {
    return <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-zinc-500" /></div>
  }
  if (!cba) {
    return <Card className="p-8 text-center text-sm text-zinc-500">{error || 'CBA not found.'}</Card>
  }

  const steps = cba.grievance_step_config ?? []

  return (
    <div className="space-y-6">
      <button onClick={() => navigate('/app/labor')} className="flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-300">
        <ArrowLeft className="w-4 h-4" /> Labor Relations
      </button>

      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">
            {cba.union_name}{cba.union_local ? ` · ${cba.union_local}` : ''}
          </h1>
          <p className="text-sm text-zinc-500 mt-1">
            {cba.effective_date ? `Effective ${cba.effective_date}` : 'No effective date'}
            {cba.expiration_date ? ` – expires ${cba.expiration_date}` : ''}
          </p>
        </div>
        <Badge variant={CBA_STATUS_VARIANT[cba.status]}>{cba.status.replace(/_/g, ' ')}</Badge>
      </div>

      {error && <Card className="p-4 border border-red-900/50 text-sm text-red-300">{error}</Card>}

      {/* Document */}
      <Card className="p-4 space-y-3">
        <h2 className="text-sm font-medium text-zinc-200">Agreement document</h2>
        <div className="flex flex-wrap items-center gap-2">
          <FileUpload onFiles={(files) => files[0] && handleUpload(files[0])} accept=".pdf,.docx,.txt">
            <Button variant="ghost" disabled={busy}>
              <Upload className="w-4 h-4" /><span className="ml-2">{cba.document_filename ? 'Replace' : 'Upload'} PDF</span>
            </Button>
          </FileUpload>
          {cba.document_filename && (
            <>
              <Button variant="ghost" onClick={handleDownload}>
                <Download className="w-4 h-4" /><span className="ml-2">Download</span>
              </Button>
              <Button variant="ghost" onClick={handleReextract} disabled={busy || cba.extraction_status === 'processing'}>
                <Sparkles className="w-4 h-4" /><span className="ml-2">Re-extract clauses</span>
              </Button>
            </>
          )}
          <ExtractionStatusBadge status={cba.extraction_status} />
        </div>
        {cba.document_filename && <p className="text-xs text-zinc-500">{cba.document_filename}</p>}
      </Card>

      {/* Grievance procedure */}
      <Card className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-zinc-200">Grievance procedure</h2>
          {steps.length > 0 && (cba.grievance_steps_confirmed
            ? <Badge variant="success"><ShieldCheck className="w-3 h-3 mr-1" />Confirmed</Badge>
            : <Button variant="ghost" onClick={confirmProcedure}><Check className="w-4 h-4" /><span className="ml-2">Confirm procedure</span></Button>
          )}
        </div>
        {!cba.grievance_steps_confirmed && steps.length > 0 && (
          <div className="flex items-start gap-2 text-xs text-amber-300 bg-amber-950/30 border border-amber-900/40 rounded p-2">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            These steps were AI-extracted. Confirm they match the contract before relying on the computed deadlines.
          </div>
        )}
        {steps.length === 0 ? (
          <p className="text-xs text-zinc-500">No grievance procedure parsed. Grievances use a default schedule until one is set.</p>
        ) : (
          <ol className="space-y-1">
            {steps.map((s) => (
              <li key={s.step} className="text-sm text-zinc-300 flex items-center gap-2">
                <span className="text-xs font-mono text-zinc-500 w-6">{s.step}</span>
                <span className="flex-1">{s.name}</span>
                <span className="text-xs text-zinc-500">
                  file {s.file_within_days}d · respond {s.respond_within_days}d ({s.day_basis})
                </span>
              </li>
            ))}
          </ol>
        )}
      </Card>

      {/* Clauses */}
      <Card className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-zinc-200">Clause library ({cba.clauses.length})</h2>
          <Button variant="ghost" onClick={() => setShowAddClause(true)}>
            <Plus className="w-4 h-4" /><span className="ml-2">Add clause</span>
          </Button>
        </div>
        {cba.clauses.length === 0 ? (
          <p className="text-xs text-zinc-500">No clauses yet. Upload the agreement to auto-extract, or add manually.</p>
        ) : (
          <div className="divide-y divide-zinc-800">
            {cba.clauses.map((c) => (
              <ClauseRow key={c.id} cbaId={cba.id} clause={c} onChange={load} />
            ))}
          </div>
        )}
      </Card>

      {showAddClause && cbaId && (
        <AddClauseModal cbaId={cbaId} onClose={() => setShowAddClause(false)} onAdded={() => { setShowAddClause(false); load() }} />
      )}
    </div>
  )
}

function ExtractionStatusBadge({ status }: { status: CBADetailType['extraction_status'] }) {
  if (status === 'processing') {
    return <span className="flex items-center gap-1 text-xs text-amber-300"><Loader2 className="w-3 h-3 animate-spin" /> extracting…</span>
  }
  if (status === 'complete') return <Badge variant="success">extracted</Badge>
  if (status === 'failed') return <Badge variant="danger">extraction failed</Badge>
  return null
}

function ClauseRow({ cbaId, clause, onChange }: { cbaId: string; clause: Clause; onChange: () => void }) {
  const [busy, setBusy] = useState(false)
  async function confirm() {
    setBusy(true)
    try { await laborApi.updateClause(cbaId, clause.id, { confirm: true }); onChange() } finally { setBusy(false) }
  }
  async function remove() {
    setBusy(true)
    try { await laborApi.deleteClause(cbaId, clause.id); onChange() } finally { setBusy(false) }
  }
  return (
    <div className="py-3 flex items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          {clause.article_number && <span className="text-xs font-mono text-zinc-500">{clause.article_number}</span>}
          <span className="text-sm text-zinc-200">{clause.title || 'Untitled clause'}</span>
          {clause.category && <Badge variant="neutral">{CLAUSE_CATEGORY_LABEL[clause.category]}</Badge>}
          {clause.source === 'ai_extracted' && <Badge variant="warning">AI</Badge>}
        </div>
        <p className="text-xs text-zinc-500 mt-1 line-clamp-3">{clause.clause_text}</p>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        {clause.source === 'ai_extracted' && (
          <Button variant="ghost" onClick={confirm} disabled={busy} title="Confirm (mark HR-owned)">
            <Check className="w-4 h-4" />
          </Button>
        )}
        <Button variant="ghost" onClick={remove} disabled={busy} title="Delete">
          <Trash2 className="w-4 h-4" />
        </Button>
      </div>
    </div>
  )
}

function AddClauseModal({ cbaId, onClose, onAdded }: { cbaId: string; onClose: () => void; onAdded: () => void }) {
  const [article, setArticle] = useState('')
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [category, setCategory] = useState<ClauseCategory | ''>('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  async function submit() {
    if (!text.trim()) { setErr('Clause text is required.'); return }
    setSaving(true); setErr('')
    try {
      await laborApi.createClause(cbaId, {
        article_number: article || undefined,
        title: title || undefined,
        clause_text: text.trim(),
        category: category || undefined,
      })
      onAdded()
    } catch {
      setErr('Could not add clause.'); setSaving(false)
    }
  }

  return (
    <Modal open onClose={onClose} title="Add clause">
      <div className="space-y-3">
        <Input label="Article number" value={article} onChange={(e) => setArticle(e.target.value)} placeholder="e.g. Article 12" />
        <Input label="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
        <Select label="Category" value={category} onChange={(e) => setCategory(e.target.value as ClauseCategory)}
          options={[{ value: '', label: 'Select…' }, ...CLAUSE_CATEGORY_OPTIONS]} />
        <Textarea label="Clause text" value={text} onChange={(e) => setText(e.target.value)} rows={5} />
        {err && <p className="text-sm text-red-400">{err}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} disabled={saving}>{saving ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Add'}</Button>
        </div>
      </div>
    </Modal>
  )
}
