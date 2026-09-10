import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Copy, KeyRound, Link2, Plus, Settings2 } from 'lucide-react'
import { createSymlink, listKinds, listSymlinks, searchEmployees } from '../../../api/symlink/symlink'
import { useAsync } from '../../../hooks/useAsync'
import { useMe } from '../../../hooks/useMe'
import type {
  EmployeeOption,
  KindCatalogEntry,
  SpecAttachmentOverride,
  SpecFieldOverride,
  Symlink,
  SymlinkKind,
  SymlinkStatus,
} from '../../../types/symlink'

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })

const STATUS_LABEL: Record<SymlinkStatus, string> = {
  pending: 'Sent',
  in_progress: 'In progress',
  submitted: 'Needs review',
  applied: 'Applied',
  rejected: 'Rejected',
  revoked: 'Revoked',
  expired: 'Expired',
}

const STATUS_CLASS: Record<SymlinkStatus, string> = {
  pending: 'bg-slate-100 text-slate-700',
  in_progress: 'bg-sky-50 text-sky-700',
  submitted: 'bg-amber-50 text-amber-800',
  applied: 'bg-emerald-50 text-emerald-700',
  rejected: 'bg-red-50 text-red-700',
  revoked: 'bg-zinc-100 text-zinc-600',
  expired: 'bg-zinc-100 text-zinc-600',
}

const INPUT = 'mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-emerald-600 focus:outline-none'
const LABEL = 'block text-xs font-semibold uppercase tracking-wide text-slate-500'

function slugKey(label: string) {
  return label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').replace(/^[^a-z]/, 'x$&').slice(0, 40) || 'item'
}

export default function SymLinks() {
  const navigate = useNavigate()
  const { hasFeature } = useMe()
  const { data, loading, error, reload } = useAsync(() => listSymlinks(), [], { links: [] as Symlink[] })
  const links = data.links
  const [showCreate, setShowCreate] = useState(false)
  const [created, setCreated] = useState<Symlink | null>(null)
  const [filter, setFilter] = useState<'all' | 'open' | 'submitted'>('all')

  const visible = useMemo(() => links.filter((l) => {
    if (filter === 'open') return l.status === 'pending' || l.status === 'in_progress'
    if (filter === 'submitted') return l.status === 'submitted'
    return true
  }), [links, filter])

  const needsReview = links.filter((l) => l.status === 'submitted').length

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <div className="mb-8 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="mb-2 text-sm font-semibold uppercase tracking-[0.18em] text-emerald-700">Guided requests</p>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-950">Sym-links</h1>
          <p className="mt-2 max-w-2xl text-slate-600">Send someone a link that walks them through exactly what you need — a credential, a check-in, an info update — and stages the result for your review.</p>
        </div>
        <div className="flex gap-2">
          <Link to="/app/symlink/settings" className="inline-flex items-center gap-2 rounded-xl border border-slate-300 px-4 py-3 font-semibold text-slate-700 hover:bg-slate-50">
            <KeyRound size={18} /> Passcode
          </Link>
          <button className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-700 px-4 py-3 font-semibold text-white shadow-sm transition hover:bg-emerald-800" onClick={() => setShowCreate(true)}>
            <Plus size={18} /> New sym-link
          </button>
        </div>
      </div>

      {error && <p className="mb-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}

      {created && (
        <div className="mb-6 rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
          <p className="font-semibold text-emerald-900">Sym-link created for {created.recipient_name}</p>
          <p className="mt-1 text-sm text-emerald-800">
            {created.email_sent ? 'The invite email went out.' : created.email_sent === false ? 'The email could not be sent (test domains are blocked) — share the link yourself.' : 'No email was sent — share the link yourself.'}
            {' '}They will need this week&apos;s passcode, which you can find under <Link to="/app/symlink/settings" className="underline">Passcode</Link>.
          </p>
          <div className="mt-3 flex items-center gap-2">
            <code className="flex-1 truncate rounded-lg bg-white px-3 py-2 text-xs text-slate-800">{created.link}</code>
            <button className="inline-flex items-center gap-1 rounded-lg border border-emerald-300 px-3 py-2 text-sm font-medium text-emerald-800 hover:bg-white" onClick={() => void navigator.clipboard?.writeText(created.link)}>
              <Copy size={14} /> Copy
            </button>
          </div>
        </div>
      )}

      <div className="mb-4 flex gap-2 text-sm">
        {(['all', 'open', 'submitted'] as const).map((f) => (
          <button key={f} onClick={() => setFilter(f)} className={`rounded-full px-3 py-1 ${filter === f ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`}>
            {f === 'all' ? 'All' : f === 'open' ? 'Open' : `Needs review${needsReview ? ` (${needsReview})` : ''}`}
          </button>
        ))}
      </div>

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        {loading ? <p className="p-6 text-sm text-slate-500">Loading...</p> : visible.length === 0 ? (
          <div className="flex flex-col items-center px-6 py-16 text-center">
            <div className="mb-4 rounded-2xl bg-emerald-50 p-4 text-emerald-700"><Link2 size={30} /></div>
            <h3 className="font-semibold text-slate-900">No sym-links yet</h3>
            <p className="mt-2 max-w-md text-sm text-slate-500">Create one to ask a team member for a credential, a manager for a check-in, or anyone for the items on a checklist.</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {visible.map((l) => (
              <button key={l.id} onClick={() => navigate(`/app/symlink/${l.id}`)} className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left hover:bg-slate-50">
                <div className="min-w-0">
                  <p className="truncate font-medium text-slate-900">{l.title}</p>
                  <p className="truncate text-sm text-slate-500">{l.recipient_name} · {l.recipient_email}{l.expires_at ? ` · expires ${dateFormat.format(new Date(l.expires_at))}` : ''}</p>
                </div>
                <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${STATUS_CLASS[l.status]}`}>{STATUS_LABEL[l.status]}</span>
              </button>
            ))}
          </div>
        )}
      </section>

      {!hasFeature('matcha_ops') && (
        <p className="mt-4 flex items-center gap-2 text-xs text-slate-500"><Settings2 size={14} /> With Matcha Ops enabled, the weekly passcode can be posted to a channel automatically.</p>
      )}

      {showCreate && (
        <CreateModal
          onClose={() => setShowCreate(false)}
          onCreated={(l) => { setCreated(l); setShowCreate(false); void reload() }}
        />
      )}
    </main>
  )
}

type Draft = {
  kind: SymlinkKind
  title: string
  instructions: string
  recipient_name: string
  recipient_email: string
  employee: EmployeeOption | null
  expires_in_days: number
  goal: string
  document_type: string
  checklist: { label: string; required: boolean }[]
  attachments: { label: string; required: boolean }[]
  send_email: boolean
}

function CreateModal({ onClose, onCreated }: { onClose: () => void; onCreated: (l: Symlink) => void }) {
  const [kinds, setKinds] = useState<KindCatalogEntry[]>([])
  const [draft, setDraft] = useState<Draft>({
    kind: 'credential_upload', title: '', instructions: '', recipient_name: '', recipient_email: '', employee: null,
    expires_in_days: 14, goal: '', document_type: 'other', checklist: [], attachments: [], send_email: true,
  })
  const [employeeQuery, setEmployeeQuery] = useState('')
  const [employeeOptions, setEmployeeOptions] = useState<EmployeeOption[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { listKinds().then((r) => setKinds(r.kinds)).catch(() => setKinds([])) }, [])

  useEffect(() => {
    const q = employeeQuery.trim()
    // The clear for short queries also runs inside the timer so the effect
    // body itself never calls setState (react-hooks/set-state-in-effect).
    const t = setTimeout(() => {
      if (q.length < 2) { setEmployeeOptions([]); return }
      searchEmployees(q).then((r) => setEmployeeOptions(r.employees)).catch(() => setEmployeeOptions([]))
    }, q.length < 2 ? 0 : 250)
    return () => clearTimeout(t)
  }, [employeeQuery])

  const current = kinds.find((k) => k.kind === draft.kind)

  function update<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((d) => ({ ...d, [key]: value }))
  }

  function pickKind(kind: SymlinkKind) {
    const entry = kinds.find((k) => k.kind === kind)
    setDraft((d) => ({ ...d, kind, title: d.title || (entry?.label ?? ''), goal: kind === 'custom' ? d.goal : '' }))
  }

  async function submit() {
    setError('')
    if (!draft.title.trim() || !draft.recipient_name.trim() || !draft.recipient_email.trim()) {
      setError('Title, recipient name, and recipient email are required.')
      return
    }
    if (draft.kind === 'credential_upload' && !draft.employee) {
      setError('Pick the employee this credential belongs to.')
      return
    }
    if (draft.kind === 'custom' && !draft.goal.trim()) {
      setError('Describe what you need for a custom request.')
      return
    }
    const fields: SpecFieldOverride[] = draft.checklist.filter((c) => c.label.trim()).map((c, i) => ({
      key: `${slugKey(c.label)}_${i + 1}`, label: c.label.trim(), type: 'text', required: c.required,
    }))
    const attachments: SpecAttachmentOverride[] = draft.attachments.filter((a) => a.label.trim()).map((a, i) => ({
      slot: `${slugKey(a.label)}_${i + 1}`, label: a.label.trim(), required: a.required,
    }))
    setSaving(true)
    try {
      const link = await createSymlink({
        kind: draft.kind,
        title: draft.title.trim(),
        instructions: draft.instructions.trim() || null,
        recipient_name: draft.recipient_name.trim(),
        recipient_email: draft.recipient_email.trim(),
        employee_id: draft.employee?.id ?? null,
        expires_in_days: draft.expires_in_days,
        send_email: draft.send_email,
        spec_overrides: {
          goal: draft.kind === 'custom' ? draft.goal.trim() : null,
          fields: fields.length ? fields : null,
          attachments: attachments.length ? attachments : null,
          document_type: draft.kind === 'credential_upload' ? draft.document_type : null,
        },
      })
      onCreated(link)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the sym-link.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-xl font-semibold text-slate-900">New sym-link</h2>
        <p className="mt-1 text-sm text-slate-500">Pick what you need; the chat will guide the recipient until it has every required item.</p>

        <div className="mt-5 grid gap-2 sm:grid-cols-2">
          {kinds.map((k) => (
            <button key={k.kind} onClick={() => pickKind(k.kind)} className={`rounded-xl border p-3 text-left ${draft.kind === k.kind ? 'border-emerald-600 bg-emerald-50' : 'border-slate-200 hover:border-slate-300'}`}>
              <p className="font-medium text-slate-900">{k.label}</p>
              <p className="mt-1 text-xs text-slate-500">{k.description}</p>
            </button>
          ))}
        </div>

        <div className="mt-5 space-y-4">
          <label className="block"><span className={LABEL}>Title</span><input value={draft.title} onChange={(e) => update('title', e.target.value)} maxLength={200} className={INPUT} placeholder={current?.label} /></label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block"><span className={LABEL}>Recipient name</span><input value={draft.recipient_name} onChange={(e) => update('recipient_name', e.target.value)} maxLength={255} className={INPUT} /></label>
            <label className="block"><span className={LABEL}>Recipient email</span><input type="email" value={draft.recipient_email} onChange={(e) => update('recipient_email', e.target.value)} maxLength={255} className={INPUT} /></label>
          </div>
          <label className="block"><span className={LABEL}>Instructions for the recipient <span className="normal-case tracking-normal text-slate-400">(optional)</span></span><textarea value={draft.instructions} onChange={(e) => update('instructions', e.target.value)} rows={3} maxLength={4000} className={INPUT} placeholder="Anything the chat should know or relay — deadlines, which side of the card to photograph, who to ask for help." /></label>

          <div className="rounded-xl border border-slate-200 p-3">
            <span className={LABEL}>Link to an employee {draft.kind === 'credential_upload' ? '' : '(optional)'}</span>
            {draft.employee ? (
              <div className="mt-2 flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-sm">
                <span>{draft.employee.name} <span className="text-slate-500">· {draft.employee.email}</span></span>
                <button className="text-xs text-slate-500 underline" onClick={() => update('employee', null)}>Clear</button>
              </div>
            ) : (
              <>
                <input value={employeeQuery} onChange={(e) => setEmployeeQuery(e.target.value)} className={INPUT} placeholder="Search the roster by name or email" />
                {employeeOptions.length > 0 && (
                  <ul className="mt-2 max-h-40 divide-y divide-slate-100 overflow-y-auto rounded-lg border border-slate-200">
                    {employeeOptions.map((o) => (
                      <li key={o.id}>
                        <button className="w-full px-3 py-2 text-left text-sm hover:bg-slate-50" onClick={() => { update('employee', o); if (!draft.recipient_name) update('recipient_name', o.name); if (!draft.recipient_email) update('recipient_email', o.email); setEmployeeQuery(''); setEmployeeOptions([]) }}>
                          {o.name} <span className="text-slate-500">· {o.email}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
            {draft.kind === 'credential_upload' && <p className="mt-2 text-xs text-slate-500">When you apply the submission, the document lands on this employee&apos;s credential record.</p>}
          </div>

          {draft.kind === 'credential_upload' && current?.credential_document_types && (
            <label className="block"><span className={LABEL}>Credential type</span>
              <select value={draft.document_type} onChange={(e) => update('document_type', e.target.value)} className={INPUT}>
                {current.credential_document_types.map((t) => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
              </select>
            </label>
          )}

          {draft.kind === 'custom' && (
            <label className="block"><span className={LABEL}>What do you need?</span><textarea value={draft.goal} onChange={(e) => update('goal', e.target.value)} rows={3} maxLength={1000} className={INPUT} placeholder="One paragraph. The recipient and the chat both see this." /></label>
          )}

          <ChecklistEditor
            title={draft.kind === 'custom' ? 'Items to collect' : 'Extra questions (optional)'}
            items={draft.checklist}
            onChange={(items) => update('checklist', items)}
            placeholder="e.g. Preferred start date"
          />
          <ChecklistEditor
            title={draft.kind === 'custom' ? 'Files to upload' : 'Extra files (optional)'}
            items={draft.attachments}
            onChange={(items) => update('attachments', items)}
            placeholder="e.g. Signed W-4"
          />

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block"><span className={LABEL}>Expires in (days)</span><input type="number" min={1} max={30} value={draft.expires_in_days} onChange={(e) => update('expires_in_days', Math.min(30, Math.max(1, Number(e.target.value) || 14)))} className={INPUT} /></label>
            <label className="mt-6 flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" checked={draft.send_email} onChange={(e) => update('send_email', e.target.checked)} /> Email the link now</label>
          </div>
        </div>

        {error && <p className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

        <div className="mt-6 flex justify-end gap-2">
          <button className="rounded-lg px-4 py-2 text-sm text-slate-600 hover:bg-slate-100" onClick={onClose}>Cancel</button>
          <button disabled={saving} className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-50" onClick={() => void submit()}>{saving ? 'Creating…' : 'Create sym-link'}</button>
        </div>
      </div>
    </div>
  )
}

function ChecklistEditor({ title, items, onChange, placeholder }: {
  title: string
  items: { label: string; required: boolean }[]
  onChange: (items: { label: string; required: boolean }[]) => void
  placeholder: string
}) {
  return (
    <div>
      <div className="flex items-center justify-between"><span className={LABEL}>{title}</span>
        <button type="button" className="text-xs font-medium text-emerald-700" onClick={() => onChange([...items, { label: '', required: true }])}>+ Add</button>
      </div>
      {items.map((item, i) => (
        <div key={i} className="mt-2 flex items-center gap-2">
          <input value={item.label} onChange={(e) => onChange(items.map((it, j) => j === i ? { ...it, label: e.target.value } : it))} maxLength={120} className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm" placeholder={placeholder} />
          <label className="flex items-center gap-1 text-xs text-slate-600"><input type="checkbox" checked={item.required} onChange={(e) => onChange(items.map((it, j) => j === i ? { ...it, required: e.target.checked } : it))} /> required</label>
          <button type="button" className="text-xs text-slate-400 hover:text-red-600" onClick={() => onChange(items.filter((_, j) => j !== i))}>Remove</button>
        </div>
      ))}
    </div>
  )
}
