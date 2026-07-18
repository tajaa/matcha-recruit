import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Badge, Button, Card, FileUpload, Modal, Select, Textarea } from '../../components/ui'
import {
  ArrowLeft, Loader2, Sparkles, AlertTriangle, ChevronRight, FileText, Send, Upload, Download,
} from 'lucide-react'
import { laborApi, streamGrievanceMerit } from '../../api/laborClient'
import type {
  Clause, GrievanceDetail as GrievanceDetailType, GrievanceResolution, GrievanceStep, StepOutcome,
} from '../../api/laborClient'
import {
  GRIEVANCE_STATUS_LABEL, GRIEVANCE_STATUS_VARIANT, RESOLUTION_OPTIONS,
  STEP_OUTCOME_OPTIONS, STEP_STATUS_VARIANT, personName,
} from '../../data/laborLabels'

const TERMINAL = new Set(['resolved', 'withdrawn', 'denied', 'settled'])

export default function GrievanceDetail() {
  const { grievanceId } = useParams<{ grievanceId: string }>()
  const navigate = useNavigate()
  const [g, setG] = useState<GrievanceDetailType | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [respondStep, setRespondStep] = useState<GrievanceStep | null>(null)
  const [showResolve, setShowResolve] = useState(false)
  const [showCitations, setShowCitations] = useState(false)

  const load = useCallback(async () => {
    if (!grievanceId) return
    try {
      setG(await laborApi.getGrievance(grievanceId))
    } catch {
      setError('Could not load grievance.')
    } finally {
      setLoading(false)
    }
  }, [grievanceId])

  useEffect(() => { load() }, [load])

  async function act(fn: () => Promise<GrievanceDetailType>) {
    setBusy(true); setError('')
    try { setG(await fn()) } catch { setError('Action failed.') } finally { setBusy(false) }
  }

  if (loading) {
    return <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-zinc-500" /></div>
  }
  if (!g || !grievanceId) {
    return <Card className="p-8 text-center text-sm text-zinc-500">{error || 'Grievance not found.'}</Card>
  }

  const terminal = TERMINAL.has(g.status)
  const activeStep = g.steps.find((s) => s.status === 'active')
  const unconfirmed = g.used_fallback_steps || (g.cba && !g.cba.grievance_steps_confirmed)

  return (
    <div className="space-y-6">
      <button onClick={() => navigate('/app/labor')} className="flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-300">
        <ArrowLeft className="w-4 h-4" /> Labor Relations
      </button>

      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-zinc-500">{g.grievance_number}</span>
            <Badge variant={GRIEVANCE_STATUS_VARIANT[g.status]}>{GRIEVANCE_STATUS_LABEL[g.status]}</Badge>
          </div>
          <h1 className="text-2xl font-semibold text-zinc-100 mt-1">{g.title}</h1>
          <p className="text-sm text-zinc-500 mt-1">
            {personName(g.grievant, g.is_class_grievance ? 'Class grievance' : 'Unassigned')}
            {g.grievance_type ? ` · ${g.grievance_type.replace(/_/g, ' ')}` : ''}
            {g.cba ? ` · ${g.cba.union_name}` : ''}
            {g.filed_date ? ` · filed ${g.filed_date}` : ''}
          </p>
        </div>
      </div>

      {error && <Card className="p-4 border border-red-900/50 text-sm text-red-300">{error}</Card>}

      {unconfirmed && (
        <div className="flex items-start gap-2 text-xs text-amber-300 bg-amber-950/30 border border-amber-900/40 rounded p-3">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          {g.used_fallback_steps
            ? 'No confirmed CBA grievance procedure — deadlines use a default schedule. Attach a CBA with a confirmed procedure for contractual accuracy.'
            : 'This CBA’s grievance procedure is not yet confirmed. Deadlines are advisory until it is confirmed on the CBA.'}
        </div>
      )}

      {/* Actions */}
      {!terminal && (
        <div className="flex flex-wrap gap-2">
          {g.status === 'draft' && (
            <Button onClick={() => act(() => laborApi.fileGrievance(grievanceId))} disabled={busy}>
              <Send className="w-4 h-4" /><span className="ml-2">File grievance</span>
            </Button>
          )}
          {g.status !== 'draft' && activeStep && (
            <Button onClick={() => setRespondStep(activeStep)} disabled={busy}>
              Record response · {activeStep.step_name}
            </Button>
          )}
          {g.status !== 'draft' && (
            <Button variant="ghost" onClick={() => act(() => laborApi.advanceGrievance(grievanceId))} disabled={busy}>
              <ChevronRight className="w-4 h-4" /><span className="ml-2">Advance</span>
            </Button>
          )}
          {g.status !== 'draft' && (
            <Button variant="ghost" onClick={() => setShowResolve(true)} disabled={busy}>Resolve</Button>
          )}
          <Button variant="ghost" onClick={() => act(() => laborApi.withdrawGrievance(grievanceId))} disabled={busy}>
            Withdraw
          </Button>
        </div>
      )}

      {g.description && (
        <Card className="p-4"><p className="text-sm text-zinc-300 whitespace-pre-wrap">{g.description}</p></Card>
      )}

      {/* Step timeline */}
      <Card className="p-4 space-y-3">
        <h2 className="text-sm font-medium text-zinc-200">Grievance steps</h2>
        <ol className="space-y-3">
          {g.steps.map((s) => (
            <li key={s.id} className="flex gap-3">
              <div className="flex flex-col items-center">
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-mono
                  ${s.status === 'active' ? 'bg-emerald-900/40 text-emerald-300 ring-1 ring-emerald-700'
                    : s.status === 'missed_deadline' ? 'bg-red-900/40 text-red-300'
                    : 'bg-zinc-800 text-zinc-400'}`}>
                  {s.step_number}
                </div>
                {s.step_number < g.steps.length && <div className="w-px flex-1 bg-zinc-800 my-1" />}
              </div>
              <div className="flex-1 pb-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm text-zinc-200">{s.step_name}</span>
                  <Badge variant={STEP_STATUS_VARIANT[s.status]}>{s.status.replace(/_/g, ' ')}</Badge>
                </div>
                <div className="text-xs text-zinc-500 mt-0.5 space-x-3">
                  {s.deadline_to_respond && <span>respond by {s.deadline_to_respond}</span>}
                  {s.deadline_to_advance && <span>advance by {s.deadline_to_advance}</span>}
                  {s.outcome && <span className="text-zinc-400">outcome: {s.outcome.replace(/_/g, ' ')}</span>}
                </div>
                {s.management_response && (
                  <p className="text-xs text-zinc-400 mt-1"><span className="text-zinc-500">Mgmt:</span> {s.management_response}</p>
                )}
                {s.union_position && (
                  <p className="text-xs text-zinc-400 mt-0.5"><span className="text-zinc-500">Union:</span> {s.union_position}</p>
                )}
              </div>
            </li>
          ))}
        </ol>
      </Card>

      {/* Cited clauses */}
      <Card className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-zinc-200">Cited CBA clauses ({g.violated_clauses.length})</h2>
          {g.cba_id && (
            <Button variant="ghost" onClick={() => setShowCitations(true)}>Edit citations</Button>
          )}
        </div>
        {g.violated_clauses.length === 0 ? (
          <p className="text-xs text-zinc-500">No clauses cited.</p>
        ) : (
          <ul className="space-y-2">
            {g.violated_clauses.map((c) => (
              <li key={c.id} className="text-sm text-zinc-300">
                <span className="text-xs font-mono text-zinc-500 mr-2">{c.article_number || '—'}</span>
                {c.title || c.clause_text.slice(0, 80)}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <MeritPanel grievanceId={grievanceId} />

      <DocumentsPanel grievanceId={grievanceId} documents={g.documents ?? []} onUploaded={setG} />

      {respondStep && (
        <RespondModal
          step={respondStep}
          onClose={() => setRespondStep(null)}
          onSubmit={async (body) => {
            await act(() => laborApi.respondStep(grievanceId, respondStep.step_number, body))
            setRespondStep(null)
          }}
        />
      )}
      {showResolve && (
        <ResolveModal
          onClose={() => setShowResolve(false)}
          onSubmit={async (body) => { await act(() => laborApi.resolveGrievance(grievanceId, body)); setShowResolve(false) }}
        />
      )}
      {showCitations && g.cba_id && (
        <CitationsModal
          cbaId={g.cba_id}
          selected={g.violated_clauses.map((c) => c.id)}
          onClose={() => setShowCitations(false)}
          onSave={async (ids) => { await act(() => laborApi.setViolatedClauses(grievanceId, ids)); setShowCitations(false) }}
        />
      )}
    </div>
  )
}

function MeritPanel({ grievanceId }: { grievanceId: string }) {
  const [text, setText] = useState('')
  const [running, setRunning] = useState(false)
  const [err, setErr] = useState('')

  async function run() {
    setRunning(true); setText(''); setErr('')
    try {
      await streamGrievanceMerit(grievanceId, {
        onDelta: (d) => setText((t) => t + d),
        onError: () => setErr('Assessment failed.'),
      })
    } finally {
      setRunning(false)
    }
  }

  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-medium text-zinc-200">
          <Sparkles className="w-4 h-4" /> AI merit assessment
        </h2>
        <Button variant="ghost" onClick={run} disabled={running}>
          {running ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Run assessment'}
        </Button>
      </div>
      {err && <p className="text-sm text-red-400">{err}</p>}
      {text
        ? <div className="text-sm text-zinc-300 whitespace-pre-wrap leading-relaxed">{text}</div>
        : !running && <p className="text-xs text-zinc-500">Grade the grievance against its cited contract language.</p>}
    </Card>
  )
}

function DocumentsPanel({
  grievanceId, documents, onUploaded,
}: {
  grievanceId: string
  documents: Array<Record<string, unknown>>
  onUploaded: (g: GrievanceDetailType) => void
}) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function upload(file: File) {
    setBusy(true); setErr('')
    try { onUploaded(await laborApi.uploadGrievanceDocument(grievanceId, file)) }
    catch { setErr('Upload failed.') }
    finally { setBusy(false) }
  }
  async function download(docId: string) {
    try {
      const { url } = await laborApi.getGrievanceDocumentUrl(grievanceId, docId)
      window.open(url, '_blank', 'noopener')
    } catch { setErr('Could not open document.') }
  }

  return (
    <Card className="p-4 space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-zinc-200">Documents ({documents.length})</h2>
        <FileUpload onFiles={(files) => files[0] && upload(files[0])}>
          <Button variant="ghost" disabled={busy}>
            <Upload className="w-4 h-4" /><span className="ml-2">Upload</span>
          </Button>
        </FileUpload>
      </div>
      {err && <p className="text-xs text-red-400">{err}</p>}
      {documents.length === 0
        ? <p className="text-xs text-zinc-500">No evidence attached.</p>
        : documents.map((d, i) => {
            const id = typeof d.id === 'string' ? d.id : ''
            return (
              <div key={i} className="flex items-center justify-between gap-2 text-xs text-zinc-400">
                <span className="flex items-center gap-2 min-w-0">
                  <FileText className="w-3 h-3 shrink-0" />
                  <span className="truncate">{String(d.filename ?? 'document')}</span>
                </span>
                {id && (
                  <Button variant="ghost" onClick={() => download(id)} title="Download">
                    <Download className="w-4 h-4" />
                  </Button>
                )}
              </div>
            )
          })}
    </Card>
  )
}

function RespondModal({
  step, onClose, onSubmit,
}: {
  step: GrievanceStep
  onClose: () => void
  onSubmit: (body: { outcome: StepOutcome; management_response?: string; union_position?: string }) => Promise<void>
}) {
  const [outcome, setOutcome] = useState<StepOutcome>('denied')
  const [mgmt, setMgmt] = useState('')
  const [union, setUnion] = useState('')
  const [saving, setSaving] = useState(false)

  return (
    <Modal open onClose={onClose} title={`Respond · ${step.step_name}`}>
      <div className="space-y-3">
        <Select label="Outcome" value={outcome} onChange={(e) => setOutcome(e.target.value as StepOutcome)}
          options={STEP_OUTCOME_OPTIONS} />
        <Textarea label="Management response" value={mgmt} onChange={(e) => setMgmt(e.target.value)} rows={3} />
        <Textarea label="Union position" value={union} onChange={(e) => setUnion(e.target.value)} rows={2} />
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button
            disabled={saving}
            onClick={async () => {
              setSaving(true)
              await onSubmit({ outcome, management_response: mgmt || undefined, union_position: union || undefined })
              setSaving(false)
            }}
          >{saving ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Record'}</Button>
        </div>
      </div>
    </Modal>
  )
}

function ResolveModal({
  onClose, onSubmit,
}: {
  onClose: () => void
  onSubmit: (body: { resolution: GrievanceResolution; resolution_summary?: string }) => Promise<void>
}) {
  const [resolution, setResolution] = useState<GrievanceResolution>('denied')
  const [summary, setSummary] = useState('')
  const [saving, setSaving] = useState(false)
  return (
    <Modal open onClose={onClose} title="Resolve grievance">
      <div className="space-y-3">
        <Select label="Resolution" value={resolution} onChange={(e) => setResolution(e.target.value as GrievanceResolution)}
          options={RESOLUTION_OPTIONS} />
        <Textarea label="Summary" value={summary} onChange={(e) => setSummary(e.target.value)} rows={3} />
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button
            disabled={saving}
            onClick={async () => { setSaving(true); await onSubmit({ resolution, resolution_summary: summary || undefined }); setSaving(false) }}
          >{saving ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Resolve'}</Button>
        </div>
      </div>
    </Modal>
  )
}

function CitationsModal({
  cbaId, selected, onClose, onSave,
}: {
  cbaId: string
  selected: string[]
  onClose: () => void
  onSave: (ids: string[]) => Promise<void>
}) {
  const [clauses, setClauses] = useState<Clause[]>([])
  const [picked, setPicked] = useState<Set<string>>(new Set(selected))
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    laborApi.listClauses(cbaId).then((r) => setClauses(r.clauses)).catch(() => setClauses([])).finally(() => setLoading(false))
  }, [cbaId])

  function toggle(id: string) {
    setPicked((p) => {
      const n = new Set(p)
      if (n.has(id)) n.delete(id); else n.add(id)
      return n
    })
  }

  return (
    <Modal open onClose={onClose} title="Cited CBA clauses">
      <div className="space-y-3">
        {loading ? (
          <div className="flex justify-center py-6"><Loader2 className="w-5 h-5 animate-spin text-zinc-500" /></div>
        ) : clauses.length === 0 ? (
          <p className="text-sm text-zinc-500">This CBA has no clauses. Add some on the CBA page.</p>
        ) : (
          <div className="max-h-72 overflow-y-auto divide-y divide-zinc-800">
            {clauses.map((c) => (
              <label key={c.id} className="flex items-start gap-2 py-2 cursor-pointer">
                <input type="checkbox" className="mt-1" checked={picked.has(c.id)} onChange={() => toggle(c.id)} />
                <span className="text-sm text-zinc-300">
                  <span className="text-xs font-mono text-zinc-500 mr-2">{c.article_number || '—'}</span>
                  {c.title || c.clause_text.slice(0, 80)}
                </span>
              </label>
            ))}
          </div>
        )}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button disabled={saving} onClick={async () => { setSaving(true); await onSave([...picked]); setSaving(false) }}>
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Save'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
