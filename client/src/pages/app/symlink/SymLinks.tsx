import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Copy, HelpCircle, KeyRound, Link2, Plus } from 'lucide-react'
import { createSymlink, listKinds, listSymlinks, searchEmployees } from '../../../api/symlink/symlink'
import { Badge, Button, Input, LABEL, Modal, PillTabs, Select, Textarea } from '../../../components/ui'
import { HowItWorksModal } from '../../../components/ui/HowItWorksModal'
import { useAsync } from '../../../hooks/useAsync'
import { useMe } from '../../../hooks/useMe'
import { useShowOnce } from '../../../hooks/useShowOnce'
import type {
  BadgeVariant,
} from '../../../components/ui'
import type {
  EmployeeOption,
  KindCatalogEntry,
  SpecAttachmentOverride,
  SpecFieldOverride,
  Symlink,
  SymlinkKind,
  SymlinkStatus,
} from '../../../types/symlink'
import { SYMLINK_HOW_IT_WORKS_STEPS } from './howItWorksSteps'

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

const STATUS_VARIANT: Record<SymlinkStatus, BadgeVariant> = {
  pending: 'neutral',
  in_progress: 'neutral',
  submitted: 'warning',
  applied: 'success',
  rejected: 'danger',
  revoked: 'neutral',
  expired: 'neutral',
}

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
  const [showHelp, setShowHelp] = useShowOnce('symlink')

  const visible = useMemo(() => links.filter((l) => {
    if (filter === 'open') return l.status === 'pending' || l.status === 'in_progress'
    if (filter === 'submitted') return l.status === 'submitted'
    return true
  }), [links, filter])

  const needsReview = links.filter((l) => l.status === 'submitted').length

  return (
    <div className="space-y-6">
      <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center sm:gap-0">
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">Sym-links</h1>
          <p className="mt-0.5 text-xs text-zinc-500">
            Send a link that walks someone through exactly what you need, then stages the result for your review.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowHelp(true)}
            aria-label="How sym-links work"
            className="rounded p-1.5 text-zinc-400 transition-colors hover:bg-white/[0.04] hover:text-zinc-100"
          >
            <HelpCircle className="h-4 w-4" />
          </button>
          <Link
            to="/app/symlink/settings"
            className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs text-zinc-400 transition-colors hover:bg-white/[0.04] hover:text-zinc-100"
          >
            <KeyRound className="h-3.5 w-3.5" /> Passcode
          </Link>
          <Button size="sm" onClick={() => setShowCreate(true)}>
            <Plus className="h-3.5 w-3.5" /> New sym-link
          </Button>
        </div>
      </div>

      {error && (
        <p className="rounded-lg border border-red-500/20 bg-red-500/[0.06] px-4 py-3 text-sm text-red-300">{error}</p>
      )}

      {created && (
        <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/[0.06] p-4">
          <p className="text-sm font-medium text-emerald-300">Sym-link created for {created.recipient_name}</p>
          <p className="mt-1 text-xs leading-relaxed text-zinc-400">
            {created.email_sent
              ? 'The invite email went out.'
              : created.email_sent === false
                ? 'The email could not be sent (test domains are blocked) — share the link yourself.'
                : 'No email was sent — share the link yourself.'}
            {' '}They will need this week&apos;s passcode from{' '}
            <Link to="/app/symlink/settings" className="text-emerald-400 underline">Passcode</Link>. Send it separately.
          </p>
          <div className="mt-3 flex items-center gap-2">
            <code className="flex-1 truncate rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 font-mono text-[11px] text-zinc-300">{created.link}</code>
            <Button variant="secondary" size="sm" onClick={() => void navigator.clipboard?.writeText(created.link)}>
              <Copy className="h-3.5 w-3.5" /> Copy
            </Button>
          </div>
        </div>
      )}

      <PillTabs
        size="sm"
        value={filter}
        onChange={setFilter}
        options={[
          { value: 'all', label: 'All' },
          { value: 'open', label: 'Open' },
          { value: 'submitted', label: needsReview ? `Needs review (${needsReview})` : 'Needs review' },
        ]}
      />

      <div className="overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900/50">
        {loading ? (
          <p className="px-5 py-6 text-xs uppercase tracking-wider text-zinc-500">Loading sym-links...</p>
        ) : visible.length === 0 ? (
          <div className="flex flex-col items-center px-6 py-14 text-center">
            <span className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg border border-emerald-500/20 bg-emerald-500/[0.06]">
              <Link2 className="h-4 w-4 text-emerald-400" />
            </span>
            <h3 className="text-sm font-medium text-zinc-200">No sym-links yet</h3>
            <p className="mt-1.5 max-w-md text-xs leading-relaxed text-zinc-500">
              Create one to ask a team member for a credential, a manager for a check-in, or anyone for the items
              on a checklist.
            </p>
            <button
              onClick={() => setShowHelp(true)}
              className="mt-4 text-xs font-medium text-emerald-400 transition-colors hover:text-emerald-300"
            >
              See how sym-links work
            </button>
          </div>
        ) : (
          <div className="divide-y divide-zinc-800">
            {visible.map((l) => (
              <button
                key={l.id}
                onClick={() => navigate(`/app/symlink/${l.id}`)}
                className="flex w-full items-center justify-between gap-4 px-5 py-3.5 text-left transition-colors hover:bg-white/[0.02]"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-zinc-100">{l.title}</p>
                  <p className="mt-0.5 truncate text-xs text-zinc-500">
                    {l.recipient_name} · {l.recipient_email}
                    {l.expires_at ? ` · expires ${dateFormat.format(new Date(l.expires_at))}` : ''}
                  </p>
                </div>
                <Badge variant={STATUS_VARIANT[l.status]} className="shrink-0">{STATUS_LABEL[l.status]}</Badge>
              </button>
            ))}
          </div>
        )}
      </div>

      {!hasFeature('matcha_ops') && (
        <p className="text-[11px] text-zinc-600">
          With Matcha Ops enabled, the weekly passcode can be posted to a channel automatically.
        </p>
      )}

      {showCreate && (
        <CreateModal
          onClose={() => setShowCreate(false)}
          onCreated={(l) => { setCreated(l); setShowCreate(false); void reload() }}
        />
      )}

      {showHelp && (
        <HowItWorksModal
          title="Sym-links"
          steps={SYMLINK_HOW_IT_WORKS_STEPS}
          onClose={() => setShowHelp(false)}
        />
      )}
    </div>
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
    <Modal open onClose={onClose} title="New sym-link" width="lg" dismissible={!saving}>
      <div className="max-h-[70vh] space-y-5 overflow-y-auto pr-1">
        <p className="text-xs text-zinc-500">
          Pick what you need; the chat guides the recipient until it has every required item.
        </p>

        <div className="grid gap-2 sm:grid-cols-2">
          {kinds.map((k) => (
            <button
              key={k.kind}
              onClick={() => pickKind(k.kind)}
              className={`rounded-lg border p-3 text-left transition-colors ${
                draft.kind === k.kind
                  ? 'border-emerald-500/40 bg-emerald-500/[0.06]'
                  : 'border-zinc-800 hover:border-zinc-700 hover:bg-white/[0.02]'
              }`}
            >
              <p className="text-sm font-medium text-zinc-100">{k.label}</p>
              <p className="mt-1 text-[11px] leading-relaxed text-zinc-500">{k.description}</p>
            </button>
          ))}
        </div>

        <Input label="Title" value={draft.title} onChange={(e) => update('title', e.target.value)} maxLength={200} placeholder={current?.label} />

        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="Recipient name" value={draft.recipient_name} onChange={(e) => update('recipient_name', e.target.value)} maxLength={255} />
          <Input label="Recipient email" type="email" value={draft.recipient_email} onChange={(e) => update('recipient_email', e.target.value)} maxLength={255} />
        </div>

        <Textarea
          label="Instructions for the recipient (optional)"
          value={draft.instructions}
          onChange={(e) => update('instructions', e.target.value)}
          rows={3}
          maxLength={4000}
          placeholder="Anything the chat should know or relay — deadlines, which side of the card to photograph, who to ask for help."
        />

        <div className="rounded-lg border border-zinc-800 p-3">
          <span className={LABEL}>Link to an employee {draft.kind === 'credential_upload' ? '' : '(optional)'}</span>
          {draft.employee ? (
            <div className="mt-2 flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-200">
              <span>{draft.employee.name} <span className="text-zinc-500">· {draft.employee.email}</span></span>
              <button className="text-[11px] text-zinc-500 underline hover:text-zinc-300" onClick={() => update('employee', null)}>Clear</button>
            </div>
          ) : (
            <div className="mt-2">
              <Input value={employeeQuery} onChange={(e) => setEmployeeQuery(e.target.value)} placeholder="Search the roster by name or email" />
              {employeeOptions.length > 0 && (
                <ul className="mt-2 max-h-40 divide-y divide-zinc-800 overflow-y-auto rounded-md border border-zinc-800">
                  {employeeOptions.map((o) => (
                    <li key={o.id}>
                      <button
                        className="w-full px-3 py-2 text-left text-sm text-zinc-200 transition-colors hover:bg-white/[0.03]"
                        onClick={() => {
                          update('employee', o)
                          if (!draft.recipient_name) update('recipient_name', o.name)
                          if (!draft.recipient_email) update('recipient_email', o.email)
                          setEmployeeQuery('')
                          setEmployeeOptions([])
                        }}
                      >
                        {o.name} <span className="text-zinc-500">· {o.email}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {draft.kind === 'credential_upload' && (
            <p className="mt-2 text-[11px] text-zinc-500">
              When you apply the submission, the document lands on this employee&apos;s credential record.
            </p>
          )}
        </div>

        {draft.kind === 'credential_upload' && current?.credential_document_types && (
          <Select
            label="Credential type"
            value={draft.document_type}
            onChange={(e) => update('document_type', e.target.value)}
            options={current.credential_document_types.map((t) => ({ value: t, label: t.replace(/_/g, ' ') }))}
          />
        )}

        {draft.kind === 'custom' && (
          <Textarea
            label="What do you need?"
            value={draft.goal}
            onChange={(e) => update('goal', e.target.value)}
            rows={3}
            maxLength={1000}
            placeholder="One paragraph. The recipient and the chat both see this."
          />
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

        <div className="grid items-end gap-4 sm:grid-cols-2">
          <Input
            label="Expires in (days)"
            type="number"
            min={1}
            max={30}
            value={draft.expires_in_days}
            onChange={(e) => update('expires_in_days', Math.min(30, Math.max(1, Number(e.target.value) || 14)))}
          />
          <label className="flex items-center gap-2 pb-2.5 text-sm text-zinc-300">
            <input type="checkbox" checked={draft.send_email} onChange={(e) => update('send_email', e.target.checked)} />
            Email the link now
          </label>
        </div>

        {error && (
          <p className="rounded-lg border border-red-500/20 bg-red-500/[0.06] px-3 py-2 text-sm text-red-300">{error}</p>
        )}
      </div>

      <div className="mt-5 flex justify-end gap-2 border-t border-zinc-800 pt-4">
        <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
        <Button size="sm" disabled={saving} onClick={() => void submit()}>
          {saving ? 'Creating…' : 'Create sym-link'}
        </Button>
      </div>
    </Modal>
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
      <div className="flex items-center justify-between">
        <span className={LABEL}>{title}</span>
        <button
          type="button"
          className="text-[11px] font-medium text-emerald-400 transition-colors hover:text-emerald-300"
          onClick={() => onChange([...items, { label: '', required: true }])}
        >
          + Add
        </button>
      </div>
      {items.map((item, i) => (
        <div key={i} className="mt-2 flex items-center gap-2">
          <input
            value={item.label}
            onChange={(e) => onChange(items.map((it, j) => j === i ? { ...it, label: e.target.value } : it))}
            maxLength={120}
            className="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 outline-none transition-colors focus:border-zinc-500"
            placeholder={placeholder}
          />
          <label className="flex items-center gap-1 text-[11px] text-zinc-400">
            <input
              type="checkbox"
              checked={item.required}
              onChange={(e) => onChange(items.map((it, j) => j === i ? { ...it, required: e.target.checked } : it))}
            />
            required
          </label>
          <button
            type="button"
            className="text-[11px] text-zinc-500 transition-colors hover:text-red-400"
            onClick={() => onChange(items.filter((_, j) => j !== i))}
          >
            Remove
          </button>
        </div>
      ))}
    </div>
  )
}
