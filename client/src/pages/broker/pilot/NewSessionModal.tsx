import { useEffect, useState } from 'react'
import { Building2, Globe, Loader2, X } from 'lucide-react'
import {
  createPilotSession, listPilotTemplates,
  type PilotSession, type PilotTemplate, type SubjectKind,
} from '../../../api/broker/brokerPilot'
import { fetchBrokerPortfolio, fetchExternalClients } from '../../../api/broker/broker'
import { DOC_TYPE_LABEL } from './shared'

type SubjectOption = { kind: SubjectKind; id: string; name: string }

interface NewSessionModalProps {
  prefill: { kind: SubjectKind; id: string } | null
  onClose: () => void
  onCreated: (session: PilotSession) => void
}

export function NewSessionModal({ prefill, onClose, onCreated }: NewSessionModalProps) {
  const [tab, setTab] = useState<SubjectKind>(prefill?.kind ?? 'company')
  const [options, setOptions] = useState<SubjectOption[]>([])
  const [loading, setLoading] = useState(true)
  const [subjectId, setSubjectId] = useState(prefill?.id ?? '')
  const [title, setTitle] = useState('')
  const [templates, setTemplates] = useState<PilotTemplate[]>([])
  const [templateKey, setTemplateKey] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Starter modes for the picker (best-effort — the modal still works blank).
  useEffect(() => {
    let cancelled = false
    listPilotTemplates()
      .then((t) => { if (!cancelled) setTemplates(t) })
      .catch(() => { /* picker just shows "Open analysis" */ })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    const load = tab === 'company'
      ? fetchBrokerPortfolio().then((r) =>
          r.companies.map((c) => ({ kind: 'company' as SubjectKind, id: c.company_id, name: c.company_name })))
      : fetchExternalClients().then((r) =>
          r.clients.map((c) => ({ kind: 'external' as SubjectKind, id: c.id, name: c.name })))
    load
      .then((opts) => { if (!cancelled) setOptions(opts) })
      .catch(() => { if (!cancelled) setOptions([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [tab])

  const selected = options.find((o) => o.id === subjectId)
  const selectedTemplate = templates.find((t) => t.key === templateKey)
  // What the title will be if left blank — mirrors the backend's derivation, so
  // the placeholder previews the real result.
  const derivedTitle = selectedTemplate
    ? `${selectedTemplate.title} — ${selected?.name ?? 'Client'}`
    : `${selected?.name ?? 'Client'} — analysis`

  const create = async () => {
    if (!subjectId) return
    setCreating(true)
    setError(null)
    try {
      const session = await createPilotSession({
        subject_kind: tab,
        subject_id: subjectId,
        title: title.trim() || undefined,
        template_key: templateKey || undefined,
      })
      onCreated(session)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not create the session')
      setCreating(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-900 p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-zinc-100">New analysis session</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300"><X className="h-4 w-4" /></button>
        </div>

        {/* Subject-kind tabs */}
        <div className="flex gap-1 mb-3 rounded-md bg-zinc-800 p-1">
          {(['company', 'external'] as const).map((k) => (
            <button
              key={k}
              onClick={() => { setTab(k); setSubjectId('') }}
              className={`flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs rounded transition-colors ${
                tab === k ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              {k === 'company' ? <Building2 className="h-3.5 w-3.5" /> : <Globe className="h-3.5 w-3.5" />}
              {k === 'company' ? 'Platform clients' : 'External clients'}
            </button>
          ))}
        </div>

        {/* Subject picker */}
        <label className="block text-xs text-zinc-400 mb-1">Client</label>
        {loading ? (
          <div className="flex items-center gap-2 text-xs text-zinc-500 py-2">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading clients…
          </div>
        ) : (
          <select
            value={subjectId}
            onChange={(e) => setSubjectId(e.target.value)}
            className="w-full bg-zinc-800 border border-zinc-700 rounded-md px-2.5 py-2 text-sm text-zinc-200 focus:outline-none focus:border-zinc-500 mb-3"
          >
            <option value="">Select a client…</option>
            {options.map((o) => (
              <option key={o.id} value={o.id}>{o.name}</option>
            ))}
          </select>
        )}
        {!loading && options.length === 0 && (
          <p className="text-xs text-zinc-600 mb-3">
            {tab === 'company'
              ? 'No platform clients in your book yet.'
              : 'No external clients yet — add them under External Book.'}
          </p>
        )}

        {/* Starter mode picker — "Open analysis" is a synthetic blank entry so
            both it and the catalog modes render from one card block. */}
        <label className="block text-xs text-zinc-400 mb-1">Start from a mode</label>
        <div className="mb-3 space-y-1">
          {[
            { key: '', label: 'Open analysis', description: "Blank session — ask anything about the client's records.", required_docs: [] },
            ...templates,
          ].map((t) => (
            <button
              key={t.key || 'open'}
              type="button"
              onClick={() => setTemplateKey(t.key)}
              className={`block w-full rounded-md border px-3 py-2 text-left transition-colors ${
                templateKey === t.key
                  ? 'border-emerald-600/60 bg-emerald-600/10'
                  : 'border-zinc-700 hover:border-zinc-600'
              }`}
            >
              <div className="text-sm text-zinc-100">{t.label}</div>
              <div className="text-[11px] text-zinc-500">{t.description}</div>
              {/* What the mode analyzes, said before it's chosen rather than
                  discovered later. "Needs" is not a hard block — anything the
                  client already has on the platform comes back covered, and the
                  session prompts only for the rest. */}
              {(t.required_docs ?? []).length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {(t.required_docs ?? []).map((d) => (
                    <span
                      key={d.doc_type}
                      title={d.hint}
                      className={`rounded border px-1.5 py-px text-[10px] ${
                        d.required
                          ? 'border-amber-500/25 bg-amber-500/10 text-amber-300/90'
                          : 'border-white/[0.08] bg-white/[0.03] text-zinc-400'
                      }`}
                    >
                      {d.required ? 'Needs' : 'Helpful'}: {DOC_TYPE_LABEL[d.doc_type]}
                    </span>
                  ))}
                </div>
              )}
            </button>
          ))}
        </div>

        <label className="block text-xs text-zinc-400 mb-1">Session title <span className="text-zinc-600">(optional)</span></label>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={subjectId ? derivedTitle : 'e.g. Renewal review 2026'}
          className="w-full bg-zinc-800 border border-zinc-700 rounded-md px-2.5 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 mb-4"
        />

        {error && <p className="text-xs text-red-400 mb-3">{error}</p>}

        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-xs rounded-md border border-zinc-700 text-zinc-300 hover:text-zinc-100 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => void create()}
            disabled={!subjectId || creating}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md bg-emerald-700 text-white hover:bg-emerald-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {creating && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Start session
          </button>
        </div>
      </div>
    </div>
  )
}
