import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft, Check, FileText, Loader2, MapPin, Paperclip, Plus, Trash2, Upload, User,
} from 'lucide-react'
import SurfaceShell from '../../../components/cappe/SurfaceShell'
import { useCappeMe } from '../../../hooks/useCappeMe'
import {
  CAPPE_IR_ACTION_PRIORITIES,
  CAPPE_IR_SEVERITIES,
  CAPPE_IR_STATUSES,
  cappeIr,
  isIrFeatureDisabledError,
} from '../../../api/cappeIr'
import type {
  CappeIrActionPriority,
  CappeIrActionStatus,
  CappeIrCorrectiveAction,
  CappeIrDocument,
  CappeIrDocumentType,
  CappeIrIncident,
  CappeIrSeverity,
  CappeIrStatus,
} from '../../../api/cappeIr'
import {
  FeatureOffPanel, actionStatusStyle, formatBytes, inputCls, labelFor,
  severityStyle, statusStyle, typeStyle,
} from './shared'

const DOCUMENT_TYPES: CappeIrDocumentType[] = ['photo', 'form', 'statement', 'other']
const ACTION_STATUSES: CappeIrActionStatus[] = ['open', 'in_progress', 'completed', 'verified', 'cancelled']

const selectCls =
  'rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-100'

type ActionDraft = {
  description: string
  assignee_name: string
  due_date: string
  priority: CappeIrActionPriority
}

function blankAction(): ActionDraft {
  return { description: '', assignee_name: '', due_date: '', priority: 'short_term' }
}

export default function IncidentDetail() {
  const { incidentId } = useParams<{ incidentId: string }>()
  const navigate = useNavigate()
  const { account, loading: meLoading } = useCappeMe()
  const featureOn = account?.matcha_features?.incidents === true

  const [incident, setIncident] = useState<CappeIrIncident | null>(null)
  const [actions, setActions] = useState<CappeIrCorrectiveAction[] | null>(null)
  const [documents, setDocuments] = useState<CappeIrDocument[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [featureOff, setFeatureOff] = useState(false)

  // Notes editing (root cause + corrective-action notes)
  const [rootCause, setRootCause] = useState('')
  const [actionNotes, setActionNotes] = useState('')
  const [savingNotes, setSavingNotes] = useState(false)

  // Corrective-action add form
  const [showAddAction, setShowAddAction] = useState(false)
  const [actionDraft, setActionDraft] = useState<ActionDraft>(blankAction())
  const [savingAction, setSavingAction] = useState(false)

  // Documents
  const fileInput = useRef<HTMLInputElement | null>(null)
  const [docType, setDocType] = useState<CappeIrDocumentType>('other')
  const [uploading, setUploading] = useState(false)

  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    if (meLoading || !featureOn || !incidentId) return
    let cancelled = false
    const fail = (e: unknown, fallback: string) => {
      if (cancelled) return
      if (isIrFeatureDisabledError(e)) setFeatureOff(true)
      else setError(e instanceof Error ? e.message : fallback)
    }
    cappeIr.getIncident(incidentId)
      .then((inc) => {
        if (cancelled) return
        setIncident(inc)
        setRootCause(inc.root_cause ?? '')
        setActionNotes(inc.corrective_actions ?? '')
      })
      .catch((e) => fail(e, 'Failed to load incident'))
    cappeIr.listActions(incidentId)
      .then((res) => { if (!cancelled) setActions(res.actions) })
      .catch((e) => fail(e, 'Failed to load corrective actions'))
    cappeIr.listDocuments(incidentId)
      .then((docs) => { if (!cancelled) setDocuments(docs) })
      .catch((e) => fail(e, 'Failed to load documents'))
    return () => { cancelled = true }
  }, [meLoading, featureOn, incidentId])

  async function patchIncident(patch: { status?: CappeIrStatus; severity?: CappeIrSeverity }) {
    if (!incidentId) return
    try {
      const updated = await cappeIr.updateIncident(incidentId, patch)
      setIncident((cur) => (cur ? { ...updated, involved_people: updated.involved_people.length ? updated.involved_people : cur.involved_people } : updated))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update incident')
    }
  }

  async function saveNotes() {
    if (!incidentId || !incident) return
    setSavingNotes(true)
    setError(null)
    try {
      const updated = await cappeIr.updateIncident(incidentId, {
        root_cause: rootCause,
        corrective_actions: actionNotes,
      })
      setIncident((cur) => (cur ? { ...updated, involved_people: updated.involved_people.length ? updated.involved_people : cur.involved_people } : updated))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save notes')
    } finally {
      setSavingNotes(false)
    }
  }

  async function addAction() {
    if (!incidentId) return
    if (!actionDraft.description.trim()) { setError('The corrective action needs a description.'); return }
    setSavingAction(true)
    setError(null)
    try {
      const created = await cappeIr.createAction(incidentId, {
        description: actionDraft.description.trim(),
        priority: actionDraft.priority,
        ...(actionDraft.assignee_name.trim() ? { assignee_name: actionDraft.assignee_name.trim() } : {}),
        ...(actionDraft.due_date ? { due_date: actionDraft.due_date } : {}),
      })
      setActions((xs) => [...(xs ?? []), created])
      setActionDraft(blankAction())
      setShowAddAction(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add corrective action')
    } finally {
      setSavingAction(false)
    }
  }

  async function setActionStatus(action: CappeIrCorrectiveAction, status: CappeIrActionStatus) {
    try {
      const updated = await cappeIr.updateAction(action.id, { status })
      setActions((xs) => (xs ?? []).map((a) => (a.id === action.id ? updated : a)))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update corrective action')
    }
  }

  async function removeAction(action: CappeIrCorrectiveAction) {
    if (!window.confirm('Delete this corrective action?')) return
    try {
      await cappeIr.deleteAction(action.id)
      setActions((xs) => (xs ?? []).filter((a) => a.id !== action.id))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete corrective action')
    }
  }

  async function uploadFile(file: File) {
    if (!incidentId) return
    setUploading(true)
    setError(null)
    try {
      const res = await cappeIr.uploadDocument(incidentId, file, docType)
      setDocuments((docs) => [...(docs ?? []), res.document])
      setIncident((cur) => (cur ? { ...cur, document_count: cur.document_count + 1 } : cur))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to upload document')
    } finally {
      setUploading(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  async function removeDocument(doc: CappeIrDocument) {
    if (!incidentId) return
    if (!window.confirm(`Delete "${doc.filename}"?`)) return
    try {
      await cappeIr.deleteDocument(incidentId, doc.id)
      setDocuments((docs) => (docs ?? []).filter((d) => d.id !== doc.id))
      setIncident((cur) => (cur ? { ...cur, document_count: Math.max(0, cur.document_count - 1) } : cur))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete document')
    }
  }

  async function deleteIncident() {
    if (!incidentId) return
    if (!window.confirm('Delete this incident and its records? This cannot be undone.')) return
    setDeleting(true)
    try {
      await cappeIr.deleteIncident(incidentId)
      navigate('/cappe/incidents')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete incident')
      setDeleting(false)
    }
  }

  if (meLoading || (featureOn && !featureOff && incident === null && !error)) {
    return (
      <SurfaceShell title="Incident">
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>
      </SurfaceShell>
    )
  }

  if (!featureOn || featureOff) {
    return (
      <SurfaceShell title="Incident">
        <FeatureOffPanel />
      </SurfaceShell>
    )
  }

  if (!incident) {
    return (
      <SurfaceShell title="Incident">
        <Link to="/cappe/incidents" className="mb-4 inline-flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-200">
          <ArrowLeft className="h-4 w-4" /> All incidents
        </Link>
        {error && <p className="text-sm text-red-400">{error}</p>}
      </SurfaceShell>
    )
  }

  const notesDirty = rootCause !== (incident.root_cause ?? '') || actionNotes !== (incident.corrective_actions ?? '')

  return (
    <SurfaceShell
      title={incident.title}
      subtitle={`${incident.incident_number} — reported ${new Date(incident.reported_at).toLocaleString()}`}
      actions={
        <button onClick={deleteIncident} disabled={deleting} className="flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-800 hover:text-red-400 disabled:opacity-60">
          {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />} Delete
        </button>
      }
    >
      <Link to="/cappe/incidents" className="mb-4 inline-flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-200">
        <ArrowLeft className="h-4 w-4" /> All incidents
      </Link>

      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}

      {/* Badges + inline status/severity editing */}
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${typeStyle[incident.incident_type]}`}>{labelFor(incident.incident_type)}</span>
        <label className="flex items-center gap-1.5 text-xs text-zinc-500">
          Status
          <select value={incident.status} onChange={(e) => patchIncident({ status: e.target.value as CappeIrStatus })} className={`${selectCls} ${statusStyle[incident.status]}`}>
            {CAPPE_IR_STATUSES.map((s) => <option key={s} value={s}>{labelFor(s)}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-1.5 text-xs text-zinc-500">
          Severity
          <select value={incident.severity} onChange={(e) => patchIncident({ severity: e.target.value as CappeIrSeverity })} className={`${selectCls} ${severityStyle[incident.severity]}`}>
            {CAPPE_IR_SEVERITIES.map((s) => <option key={s} value={s}>{labelFor(s)}</option>)}
          </select>
        </label>
      </div>

      {/* Core fields */}
      <div className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-6">
        <div className="grid gap-4 text-sm sm:grid-cols-2">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Occurred</div>
            <div className="mt-0.5 text-zinc-200">{new Date(incident.occurred_at).toLocaleString()}</div>
          </div>
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Location</div>
            <div className="mt-0.5 flex items-center gap-1.5 text-zinc-200">
              <MapPin className="h-3.5 w-3.5 text-zinc-500" />
              {incident.location_name || incident.location || '—'}
              {incident.location_city && <span className="text-zinc-500">({incident.location_city}{incident.location_state ? `, ${incident.location_state}` : ''})</span>}
            </div>
          </div>
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Reported by</div>
            <div className="mt-0.5 flex items-center gap-1.5 text-zinc-200">
              <User className="h-3.5 w-3.5 text-zinc-500" />
              {incident.reported_by_name}
              {incident.reported_by_email && <span className="text-zinc-500">{incident.reported_by_email}</span>}
            </div>
          </div>
          {incident.resolved_at && (
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Resolved</div>
              <div className="mt-0.5 text-zinc-200">{new Date(incident.resolved_at).toLocaleString()}</div>
            </div>
          )}
        </div>

        <div className="mt-5">
          <div className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Description</div>
          <p className="mt-1 whitespace-pre-wrap text-sm text-zinc-200">{incident.description || '—'}</p>
        </div>

        {incident.witnesses.length > 0 && (
          <div className="mt-5">
            <div className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Witnesses</div>
            <ul className="mt-1 space-y-0.5 text-sm text-zinc-200">
              {incident.witnesses.map((w, i) => (
                <li key={i}>
                  {w.name}
                  {w.contact && <span className="text-zinc-500"> — {w.contact}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}

        {incident.involved_people.length > 0 && (
          <div className="mt-5">
            <div className="text-xs font-semibold uppercase tracking-wide text-zinc-500">People involved</div>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {incident.involved_people.map((p) => (
                <span key={`${p.id}-${p.role}`} className="rounded-full bg-zinc-800 px-2 py-0.5 text-xs text-zinc-300">
                  {p.display_name} <span className="text-zinc-500">· {labelFor(p.role)}</span>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Editable notes */}
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-zinc-500">Root cause</label>
            <textarea value={rootCause} onChange={(e) => setRootCause(e.target.value)} rows={3} placeholder="What caused this?" className={inputCls} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-zinc-500">Corrective-action notes</label>
            <textarea value={actionNotes} onChange={(e) => setActionNotes(e.target.value)} rows={3} placeholder="Free-form next steps." className={inputCls} />
          </div>
        </div>
        {notesDirty && (
          <div className="mt-3 flex justify-end">
            <button onClick={saveNotes} disabled={savingNotes} className="flex items-center gap-1.5 rounded-lg bg-lime-500 px-3 py-1.5 text-xs font-semibold text-zinc-950 hover:bg-lime-400 disabled:opacity-60">
              {savingNotes ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Save notes
            </button>
          </div>
        )}
      </div>

      {/* Corrective actions */}
      <div className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-6">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-100">Corrective actions</h2>
          {!showAddAction && (
            <button onClick={() => setShowAddAction(true)} className="inline-flex items-center gap-1 text-xs font-semibold text-lime-400 hover:text-lime-300">
              <Plus className="h-3.5 w-3.5" /> Add action
            </button>
          )}
        </div>

        {showAddAction && (
          <div className="mb-4 rounded-xl border border-zinc-800 bg-zinc-950 p-4">
            <div className="space-y-3">
              <textarea value={actionDraft.description} onChange={(e) => setActionDraft((d) => ({ ...d, description: e.target.value }))} rows={2} placeholder="What needs to happen?" className={inputCls} />
              <div className="grid gap-3 sm:grid-cols-3">
                <input value={actionDraft.assignee_name} onChange={(e) => setActionDraft((d) => ({ ...d, assignee_name: e.target.value }))} placeholder="Owner (optional)" className={inputCls} />
                <input type="date" value={actionDraft.due_date} onChange={(e) => setActionDraft((d) => ({ ...d, due_date: e.target.value }))} className={inputCls} />
                <select value={actionDraft.priority} onChange={(e) => setActionDraft((d) => ({ ...d, priority: e.target.value as CappeIrActionPriority }))} className={inputCls}>
                  {CAPPE_IR_ACTION_PRIORITIES.map((p) => <option key={p} value={p}>{labelFor(p)}</option>)}
                </select>
              </div>
              <div className="flex justify-end gap-2">
                <button onClick={() => { setShowAddAction(false); setActionDraft(blankAction()) }} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800">Cancel</button>
                <button onClick={addAction} disabled={savingAction} className="flex items-center gap-1.5 rounded-lg bg-lime-500 px-3 py-1.5 text-xs font-semibold text-zinc-950 hover:bg-lime-400 disabled:opacity-60">
                  {savingAction ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Add action
                </button>
              </div>
            </div>
          </div>
        )}

        {actions === null ? (
          <div className="flex justify-center py-6"><Loader2 className="h-5 w-5 animate-spin text-zinc-400" /></div>
        ) : actions.length === 0 ? (
          <p className="py-4 text-center text-sm text-zinc-500">No corrective actions yet.</p>
        ) : (
          <div className="space-y-2">
            {actions.map((a) => (
              <div key={a.id} className="flex items-start gap-3 rounded-xl border border-zinc-800 bg-zinc-950 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-zinc-200">{a.description}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-zinc-500">
                    <span>{labelFor(a.priority)}</span>
                    {(a.assignee_name || a.assigned_to_name) && <span>Owner: {a.assignee_name || a.assigned_to_name}</span>}
                    {a.due_date && (
                      <span className={a.overdue ? 'font-semibold text-red-400' : ''}>
                        Due {new Date(`${a.due_date}T00:00:00`).toLocaleDateString()}{a.overdue ? ' — overdue' : ''}
                      </span>
                    )}
                  </div>
                </div>
                <select value={a.status} onChange={(e) => setActionStatus(a, e.target.value as CappeIrActionStatus)} className={`${selectCls} ${actionStatusStyle[a.status]}`}>
                  {ACTION_STATUSES.map((s) => <option key={s} value={s}>{labelFor(s)}</option>)}
                </select>
                <button onClick={() => removeAction(a)} className="mt-0.5 text-zinc-500 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Documents */}
      <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-6">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-zinc-100">Documents</h2>
          <div className="flex items-center gap-2">
            <select value={docType} onChange={(e) => setDocType(e.target.value as CappeIrDocumentType)} className={selectCls}>
              {DOCUMENT_TYPES.map((t) => <option key={t} value={t}>{labelFor(t)}</option>)}
            </select>
            <input
              ref={fileInput}
              type="file"
              className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void uploadFile(f) }}
            />
            <button onClick={() => fileInput.current?.click()} disabled={uploading} className="flex items-center gap-1.5 rounded-lg border border-zinc-700 px-2.5 py-1 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60">
              {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />} Upload
            </button>
          </div>
        </div>

        {documents === null ? (
          <div className="flex justify-center py-6"><Loader2 className="h-5 w-5 animate-spin text-zinc-400" /></div>
        ) : documents.length === 0 ? (
          <p className="py-4 text-center text-sm text-zinc-500">
            <Paperclip className="mx-auto mb-1 h-5 w-5 text-zinc-600" /> No documents attached.
          </p>
        ) : (
          <div className="divide-y divide-zinc-800">
            {documents.map((doc) => (
              <div key={doc.id} className="flex items-center gap-3 py-2.5">
                <FileText className="h-4 w-4 shrink-0 text-zinc-500" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm text-zinc-200">{doc.filename}</div>
                  <div className="text-xs text-zinc-500">
                    {labelFor(doc.document_type)}
                    {doc.file_size != null && ` · ${formatBytes(doc.file_size)}`}
                    {` · ${new Date(doc.created_at).toLocaleString()}`}
                  </div>
                </div>
                <button onClick={() => removeDocument(doc)} className="text-zinc-500 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
              </div>
            ))}
          </div>
        )}
      </div>
    </SurfaceShell>
  )
}
