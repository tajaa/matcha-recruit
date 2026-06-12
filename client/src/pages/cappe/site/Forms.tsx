import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Plus, Trash2, Inbox, ChevronDown, ChevronRight, X } from 'lucide-react'
import { cappeApi } from '../../../api/cappeClient'
import SurfaceShell from '../../../components/cappe/SurfaceShell'
import type { CappeForm, CappeFormField, CappeFormSubmission } from '../../../types/cappe'

const FIELD_TYPES = ['text', 'email', 'textarea', 'number', 'tel', 'date']

function keyFromLabel(label: string): string {
  return label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'field'
}

export default function Forms() {
  const { siteId } = useParams<{ siteId: string }>()
  const [forms, setForms] = useState<CappeForm[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [fields, setFields] = useState<CappeFormField[]>([{ key: '', label: '', type: 'text', required: false }])
  const [saving, setSaving] = useState(false)
  const [openId, setOpenId] = useState<string | null>(null)
  const [subs, setSubs] = useState<Record<string, CappeFormSubmission[]>>({})

  useEffect(() => {
    cappeApi
      .get<CappeForm[]>(`/sites/${siteId}/forms`)
      .then(setForms)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load forms'))
  }, [siteId])

  function setField(i: number, patch: Partial<CappeFormField>) {
    setFields((f) => f.map((x, idx) => (idx === i ? { ...x, ...patch } : x)))
  }

  async function create(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setSaving(true)
    setError(null)
    try {
      const cleanFields = fields
        .filter((f) => f.label.trim())
        .map((f) => ({ ...f, key: keyFromLabel(f.label) }))
      const created = await cappeApi.post<CappeForm>(`/sites/${siteId}/forms`, {
        name: name.trim(),
        fields: cleanFields,
        status: 'active',
      })
      setForms((list) => [created, ...(list || [])])
      setName('')
      setFields([{ key: '', label: '', type: 'text', required: false }])
      setCreating(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create form')
    } finally {
      setSaving(false)
    }
  }

  async function toggle(form: CappeForm) {
    if (openId === form.id) { setOpenId(null); return }
    setOpenId(form.id)
    if (!subs[form.id]) {
      const rows = await cappeApi.get<CappeFormSubmission[]>(`/sites/${siteId}/forms/${form.id}/submissions`)
      setSubs((s) => ({ ...s, [form.id]: rows }))
    }
  }

  async function removeForm(id: string) {
    await cappeApi.delete(`/sites/${siteId}/forms/${id}`)
    setForms((f) => (f || []).filter((x) => x.id !== id))
  }

  return (
    <SurfaceShell
      title="Forms"
      subtitle="Contact and lead-capture forms."
      actions={
        <button onClick={() => setCreating((v) => !v)} className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400">
          <Plus className="h-4 w-4" /> New form
        </button>
      }
    >
      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}

      {creating && (
        <form onSubmit={create} className="mb-6 space-y-3 rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-sm">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Form name (e.g. Contact us)"
            className="w-full rounded-lg border border-zinc-700 bg-zinc-950 text-zinc-100 placeholder:text-zinc-500 px-3 py-2 text-sm outline-none focus:border-emerald-500"
          />
          <div className="space-y-2">
            {fields.map((f, i) => (
              <div key={i} className="flex items-center gap-2">
                <input
                  value={f.label}
                  onChange={(e) => setField(i, { label: e.target.value })}
                  placeholder="Field label"
                  className="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 text-zinc-100 placeholder:text-zinc-500 px-3 py-1.5 text-sm outline-none focus:border-emerald-500"
                />
                <select value={f.type} onChange={(e) => setField(i, { type: e.target.value })} className="rounded-lg border border-zinc-700 bg-zinc-950 text-zinc-100 placeholder:text-zinc-500 px-2 py-1.5 text-sm">
                  {FIELD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
                <label className="flex items-center gap-1 text-xs text-zinc-500">
                  <input type="checkbox" checked={f.required} onChange={(e) => setField(i, { required: e.target.checked })} /> req
                </label>
                <button type="button" onClick={() => setFields((fs) => fs.filter((_, idx) => idx !== i))} className="text-zinc-400 hover:text-red-400">
                  <X className="h-4 w-4" />
                </button>
              </div>
            ))}
            <button type="button" onClick={() => setFields((f) => [...f, { key: '', label: '', type: 'text', required: false }])} className="text-xs font-medium text-emerald-400 hover:underline">
              + Add field
            </button>
          </div>
          <button type="submit" disabled={saving} className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Create form
          </button>
        </form>
      )}

      {forms === null ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>
      ) : forms.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-700 py-12 text-center text-sm text-zinc-500">
          <Inbox className="mx-auto mb-2 h-7 w-7 text-zinc-300" /> No forms yet.
        </div>
      ) : (
        <div className="space-y-3">
          {forms.map((form) => (
            <div key={form.id} className="rounded-2xl border border-zinc-800 bg-zinc-900">
              <div className="flex items-center gap-3 px-5 py-3">
                <button onClick={() => toggle(form)} className="text-zinc-400 hover:text-zinc-300">
                  {openId === form.id ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                </button>
                <div className="min-w-0 flex-1">
                  <div className="font-medium text-zinc-100">{form.name}</div>
                  <div className="text-xs text-zinc-400">/{form.slug} · {form.fields.length} field(s)</div>
                </div>
                <button onClick={() => removeForm(form.id)} className="text-zinc-400 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
              </div>
              {openId === form.id && (
                <div className="border-t border-zinc-800 bg-zinc-950 px-5 py-3">
                  {!subs[form.id] ? (
                    <Loader2 className="h-4 w-4 animate-spin text-zinc-400" />
                  ) : subs[form.id].length === 0 ? (
                    <p className="text-sm text-zinc-400">No submissions yet.</p>
                  ) : (
                    <ul className="space-y-2">
                      {subs[form.id].map((s) => (
                        <li key={s.id} className="rounded-lg bg-zinc-900 p-3 text-sm shadow-sm">
                          <div className="mb-1 text-xs text-zinc-400">{new Date(s.created_at).toLocaleString()}</div>
                          {Object.entries(s.data).map(([k, v]) => (
                            <div key={k} className="text-zinc-300"><span className="font-medium">{k}:</span> {String(v)}</div>
                          ))}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </SurfaceShell>
  )
}
