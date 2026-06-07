import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { Badge, Button, Card, Input, Modal, PillTabs, Select, Textarea } from '../../components/ui'
import { ArrowLeft, ExternalLink, Loader2, Plus, Trash2 } from 'lucide-react'
import {
  fractionalHr,
  BILLING_LABELS,
  serviceLabel,
  SERVICE_LABELS,
  type AssignmentRole,
  type BillingModel,
  type ClientDetail,
  type FractionalClient,
  type Pro,
  type ScopeItem,
  type Task,
  type TaskStatus,
  type TimeEntry,
} from '../../api/fractionalHr'

const STATUS_VARIANT: Record<string, 'success' | 'warning' | 'neutral' | 'danger'> = {
  active: 'success', prospect: 'neutral', paused: 'warning', offboarded: 'danger',
}
const TASK_STATUS_LABEL: Record<TaskStatus, string> = {
  todo: 'To do', in_progress: 'In progress', blocked: 'Blocked', review: 'Review', done: 'Done',
}
const SERVICE_OPTS = Object.keys(SERVICE_LABELS).map((k) => ({ value: k, label: SERVICE_LABELS[k] }))
const PRIORITY_OPTS = [
  { value: 'low', label: 'Low' }, { value: 'medium', label: 'Medium' }, { value: 'high', label: 'High' },
]

type Tab = 'scope' | 'tasks' | 'time' | 'team' | 'settings'

function HoursPanel({ d }: { d: ClientDetail }) {
  const s = d.hours_summary
  const pct = s.utilization_pct
  const over = pct != null && pct > 100
  return (
    <Card className="p-4">
      <div className="text-xs uppercase tracking-wide text-zinc-500 mb-2">
        {BILLING_LABELS[s.billing_model as BillingModel]}
        {s.basis === 'period' && s.retainer_period ? ` · ${s.retainer_period}` : ''}
      </div>
      <div className="flex items-end gap-2">
        <span className={`text-3xl font-semibold ${over ? 'text-rose-400' : 'text-zinc-100'}`}>{s.used ?? s.total_logged}</span>
        <span className="text-zinc-500 mb-1">{s.budget != null ? `/ ${s.budget} h` : 'h logged'}</span>
      </div>
      {pct != null && (
        <div className="mt-2">
          <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
            <div className={`h-full ${over ? 'bg-rose-500' : pct > 80 ? 'bg-amber-500' : 'bg-emerald-500'}`} style={{ width: `${Math.min(pct, 100)}%` }} />
          </div>
          <div className="flex justify-between text-[11px] text-zinc-500 mt-1">
            <span>{pct}% used</span>
            {s.remaining != null && <span>{s.remaining}h {s.remaining < 0 ? 'over' : 'left'}</span>}
          </div>
        </div>
      )}
      {s.billable_amount != null && <div className="text-xs text-zinc-400 mt-2">Billable: ${s.billable_amount.toLocaleString()}</div>}
      {s.project_fee != null && <div className="text-xs text-zinc-400 mt-2">Project fee: ${s.project_fee.toLocaleString()}</div>}
      <div className="text-[11px] text-zinc-600 mt-2">{s.total_logged}h logged all-time</div>
    </Card>
  )
}

export default function FractionalClientDetail() {
  const { clientId } = useParams<{ clientId: string }>()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<ClientDetail | null>(null)
  const [scope, setScope] = useState<ScopeItem[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [time, setTime] = useState<TimeEntry[]>([])
  const [pros, setPros] = useState<Pro[]>([])
  const [tab, setTab] = useState<Tab>('scope')
  const [loading, setLoading] = useState(true)

  async function loadAll() {
    if (!clientId) return
    const [d, sc, tk, tm, pr] = await Promise.all([
      fractionalHr.getClient(clientId),
      fractionalHr.listScope(clientId),
      fractionalHr.listTasks(clientId),
      fractionalHr.listTime(clientId),
      fractionalHr.pros(),
    ])
    setDetail(d); setScope(sc.scope_items); setTasks(tk.tasks); setTime(tm.time_entries); setPros(pr.pros)
  }

  useEffect(() => {
    setLoading(true)
    loadAll().finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId])

  const refreshHeader = async () => { if (clientId) setDetail(await fractionalHr.getClient(clientId)) }
  const proOpts = [{ value: '', label: 'Unassigned' }, ...pros.map((p) => ({ value: p.id, label: p.email }))]

  if (loading || !detail) {
    return <div className="flex items-center justify-center h-64 text-zinc-500"><Loader2 className="animate-spin" /></div>
  }
  const c = detail.client

  return (
    <div className="p-6 space-y-5">
      <Link to="/admin/fractional-hr" className="inline-flex items-center gap-1 text-sm text-zinc-400 hover:text-zinc-200">
        <ArrowLeft size={14} /> Book of business
      </Link>

      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100 flex items-center gap-2">
            {c.name}
            <Badge variant={STATUS_VARIANT[c.status] ?? 'neutral'}>{c.status}</Badge>
          </h1>
          <div className="text-sm text-zinc-500 mt-1 flex flex-wrap gap-x-4 gap-y-1">
            {c.industry && <span>{c.industry}</span>}
            {c.headcount != null && <span>{c.headcount} employees</span>}
            {detail.lead_pro && <span>Lead: {detail.lead_pro.email}</span>}
            {detail.company ? (
              <Link to={`/admin/companies/${detail.company.id}`} className="inline-flex items-center gap-1 text-emerald-400 hover:text-emerald-300">
                <ExternalLink size={12} /> {detail.company.name} (tenant)
              </Link>
            ) : (
              <span className="text-zinc-600">No platform tenant</span>
            )}
          </div>
        </div>
        <div className="w-64 shrink-0"><HoursPanel d={detail} /></div>
      </div>

      <PillTabs<Tab>
        value={tab}
        onChange={setTab}
        options={[
          { value: 'scope', label: `Scope (${scope.length})` },
          { value: 'tasks', label: `Tasks (${detail.task_counts.open_tasks} open)` },
          { value: 'time', label: 'Hours' },
          { value: 'team', label: `Team (${detail.assignments.length})` },
          { value: 'settings', label: 'Settings' },
        ]}
      />

      {tab === 'scope' && <ScopeTab clientId={c.id} items={scope} onChange={() => fractionalHr.listScope(c.id).then((r) => setScope(r.scope_items))} />}
      {tab === 'tasks' && (
        <TasksTab
          clientId={c.id} tasks={tasks} scope={scope} proOpts={proOpts}
          onChange={async () => { setTasks((await fractionalHr.listTasks(c.id)).tasks); refreshHeader() }}
        />
      )}
      {tab === 'time' && (
        <TimeTab
          clientId={c.id} entries={time} tasks={tasks} proOpts={proOpts}
          onChange={async () => { setTime((await fractionalHr.listTime(c.id)).time_entries); refreshHeader() }}
        />
      )}
      {tab === 'team' && (
        <TeamTab
          clientId={c.id} assignments={detail.assignments} proOpts={proOpts}
          onChange={refreshHeader}
        />
      )}
      {tab === 'settings' && <SettingsTab client={c} pros={pros} onSaved={refreshHeader} onDeleted={() => navigate('/admin/fractional-hr')} />}
    </div>
  )
}

// --- Scope ---------------------------------------------------------------- //
function ScopeTab({ clientId, items, onChange }: { clientId: string; items: ScopeItem[]; onChange: () => void }) {
  const [adding, setAdding] = useState(false)
  const [title, setTitle] = useState('')
  const [cat, setCat] = useState('policy')
  const add = async () => {
    if (!title.trim()) return
    await fractionalHr.createScope(clientId, { title: title.trim(), service_category: cat })
    setTitle(''); setAdding(false); onChange()
  }
  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-zinc-200">Engagement scope</h2>
        <Button size="sm" variant="secondary" onClick={() => setAdding((v) => !v)}><Plus size={14} className="mr-1" /> Add</Button>
      </div>
      {adding && (
        <div className="flex gap-2 items-end">
          <div className="flex-1"><Input label="Scope item" value={title} onChange={(e) => setTitle(e.target.value)} autoFocus /></div>
          <Select label="Area" value={cat} onChange={(e) => setCat(e.target.value)} options={SERVICE_OPTS} />
          <Button size="sm" onClick={add}>Add</Button>
        </div>
      )}
      <div className="space-y-1.5">
        {items.map((s) => (
          <div key={s.id} className="flex items-center justify-between px-3 py-2 rounded-md bg-zinc-900/50">
            <div className="min-w-0">
              <div className="text-sm text-zinc-200 truncate">{s.title}</div>
              <div className="text-[11px] text-zinc-500">{serviceLabel(s.service_category)}</div>
            </div>
            <div className="flex items-center gap-2">
              <Select
                value={s.status}
                onChange={async (e) => { await fractionalHr.updateScope(s.id, { status: e.target.value as ScopeItem['status'] }); onChange() }}
                options={[
                  { value: 'planned', label: 'Planned' }, { value: 'active', label: 'Active' },
                  { value: 'on_hold', label: 'On hold' }, { value: 'done', label: 'Done' },
                ]}
              />
              <button onClick={async () => { await fractionalHr.deleteScope(s.id); onChange() }} className="text-zinc-600 hover:text-rose-400">
                <Trash2 size={14} />
              </button>
            </div>
          </div>
        ))}
        {items.length === 0 && !adding && <p className="text-sm text-zinc-500">No scope defined yet.</p>}
      </div>
    </Card>
  )
}

// --- Tasks ---------------------------------------------------------------- //
function TasksTab({
  clientId, tasks, scope, proOpts, onChange,
}: { clientId: string; tasks: Task[]; scope: ScopeItem[]; proOpts: { value: string; label: string }[]; onChange: () => void }) {
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState({ title: '', service_category: 'policy', assignee_pro_id: '', due_date: '', priority: 'medium', scope_item_id: '', estimated_hours: '' })
  const [saving, setSaving] = useState(false)

  const add = async () => {
    if (!form.title.trim()) return
    setSaving(true)
    try {
      await fractionalHr.createTask(clientId, {
        title: form.title.trim(),
        service_category: form.service_category,
        assignee_pro_id: form.assignee_pro_id || null,
        due_date: form.due_date || null,
        priority: form.priority as Task['priority'],
        scope_item_id: form.scope_item_id || null,
        estimated_hours: form.estimated_hours ? Number(form.estimated_hours) : null,
      })
      setShowAdd(false)
      setForm({ title: '', service_category: 'policy', assignee_pro_id: '', due_date: '', priority: 'medium', scope_item_id: '', estimated_hours: '' })
      onChange()
    } finally { setSaving(false) }
  }

  const scopeOpts = [{ value: '', label: 'No scope link' }, ...scope.map((s) => ({ value: s.id, label: s.title }))]
  const today = new Date().toISOString().slice(0, 10)

  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-zinc-200">Tasks</h2>
        <Button size="sm" onClick={() => setShowAdd(true)}><Plus size={14} className="mr-1" /> New task</Button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-zinc-500 border-b border-white/[0.06]">
              <th className="py-2 pr-3 font-medium">Task</th>
              <th className="py-2 px-3 font-medium">Area</th>
              <th className="py-2 px-3 font-medium">Status</th>
              <th className="py-2 px-3 font-medium">Assignee</th>
              <th className="py-2 px-3 font-medium">Due</th>
              <th className="py-2 px-3 font-medium"></th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((t) => {
              const overdue = t.status !== 'done' && t.due_date && t.due_date < today
              return (
                <tr key={t.id} className="border-b border-white/[0.04]">
                  <td className="py-2 pr-3">
                    <div className={`${t.status === 'done' ? 'text-zinc-500 line-through' : 'text-zinc-200'}`}>{t.title}</div>
                    {t.scope_title && <div className="text-[11px] text-zinc-600">↳ {t.scope_title}</div>}
                  </td>
                  <td className="py-2 px-3 text-xs text-zinc-400">{serviceLabel(t.service_category)}</td>
                  <td className="py-2 px-3">
                    <Select
                      value={t.status}
                      onChange={async (e) => { await fractionalHr.updateTask(t.id, { status: e.target.value as TaskStatus }); onChange() }}
                      options={(Object.keys(TASK_STATUS_LABEL) as TaskStatus[]).map((s) => ({ value: s, label: TASK_STATUS_LABEL[s] }))}
                    />
                  </td>
                  <td className="py-2 px-3">
                    <Select
                      value={t.assignee_pro_id ?? ''}
                      onChange={async (e) => { await fractionalHr.updateTask(t.id, { assignee_pro_id: e.target.value || null }); onChange() }}
                      options={proOpts}
                    />
                  </td>
                  <td className={`py-2 px-3 text-xs ${overdue ? 'text-rose-400' : 'text-zinc-400'}`}>{t.due_date ?? '—'}</td>
                  <td className="py-2 px-3">
                    <button onClick={async () => { await fractionalHr.deleteTask(t.id); onChange() }} className="text-zinc-600 hover:text-rose-400"><Trash2 size={14} /></button>
                  </td>
                </tr>
              )
            })}
            {tasks.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-zinc-500 text-sm">No tasks yet.</td></tr>}
          </tbody>
        </table>
      </div>

      <Modal open={showAdd} onClose={() => setShowAdd(false)} title="New task">
        <div className="space-y-3">
          <Input label="Title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} autoFocus />
          <div className="grid grid-cols-2 gap-3">
            <Select label="Service area" value={form.service_category} onChange={(e) => setForm({ ...form, service_category: e.target.value })} options={SERVICE_OPTS} />
            <Select label="Priority" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} options={PRIORITY_OPTS} />
          </div>
          <Select label="Assignee" value={form.assignee_pro_id} onChange={(e) => setForm({ ...form, assignee_pro_id: e.target.value })} options={proOpts} />
          <Select label="Scope item" value={form.scope_item_id} onChange={(e) => setForm({ ...form, scope_item_id: e.target.value })} options={scopeOpts} />
          <div className="grid grid-cols-2 gap-3">
            <Input label="Due date" type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
            <Input label="Est. hours" type="number" value={form.estimated_hours} onChange={(e) => setForm({ ...form, estimated_hours: e.target.value })} />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setShowAdd(false)}>Cancel</Button>
            <Button onClick={add} disabled={saving}>{saving ? <Loader2 size={16} className="animate-spin" /> : 'Create'}</Button>
          </div>
        </div>
      </Modal>
    </Card>
  )
}

// --- Time ----------------------------------------------------------------- //
function TimeTab({
  clientId, entries, tasks, proOpts, onChange,
}: { clientId: string; entries: TimeEntry[]; tasks: Task[]; proOpts: { value: string; label: string }[]; onChange: () => void }) {
  const [form, setForm] = useState({ hours: '', note: '', entry_date: new Date().toISOString().slice(0, 10), task_id: '', pro_id: '' })
  const [saving, setSaving] = useState(false)
  const log = async () => {
    if (!form.hours || Number(form.hours) <= 0) return
    setSaving(true)
    try {
      await fractionalHr.logTime(clientId, {
        hours: Number(form.hours), note: form.note || null, entry_date: form.entry_date,
        task_id: form.task_id || null, pro_id: form.pro_id || undefined,
      })
      setForm({ ...form, hours: '', note: '', task_id: '' })
      onChange()
    } finally { setSaving(false) }
  }
  const taskOpts = [{ value: '', label: 'No task' }, ...tasks.map((t) => ({ value: t.id, label: t.title }))]
  return (
    <Card className="p-4 space-y-3">
      <h2 className="text-sm font-medium text-zinc-200">Log hours</h2>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2 items-end">
        <Input label="Hours" type="number" value={form.hours} onChange={(e) => setForm({ ...form, hours: e.target.value })} />
        <Input label="Date" type="date" value={form.entry_date} onChange={(e) => setForm({ ...form, entry_date: e.target.value })} />
        <Select label="Pro" value={form.pro_id} onChange={(e) => setForm({ ...form, pro_id: e.target.value })} options={proOpts} />
        <Select label="Task" value={form.task_id} onChange={(e) => setForm({ ...form, task_id: e.target.value })} options={taskOpts} />
        <Button onClick={log} disabled={saving}>{saving ? <Loader2 size={16} className="animate-spin" /> : 'Log'}</Button>
      </div>
      <Input placeholder="Note (optional)" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
      <div className="space-y-1 pt-1">
        {entries.map((e) => (
          <div key={e.id} className="flex items-center justify-between px-3 py-2 rounded-md bg-zinc-900/50 text-sm">
            <div className="min-w-0">
              <span className="text-zinc-200 font-medium">{e.hours}h</span>
              <span className="text-zinc-500 ml-2">{e.entry_date}</span>
              {e.task_title && <span className="text-zinc-500 ml-2 truncate">· {e.task_title}</span>}
              {e.note && <div className="text-[11px] text-zinc-500 truncate">{e.note}</div>}
            </div>
            <div className="flex items-center gap-3">
              <span className="text-[11px] text-zinc-600 truncate max-w-[140px]">{e.pro_email}</span>
              <button onClick={async () => { await fractionalHr.deleteTime(e.id); onChange() }} className="text-zinc-600 hover:text-rose-400"><Trash2 size={14} /></button>
            </div>
          </div>
        ))}
        {entries.length === 0 && <p className="text-sm text-zinc-500">No time logged yet.</p>}
      </div>
    </Card>
  )
}

// --- Team ----------------------------------------------------------------- //
function TeamTab({
  clientId, assignments, proOpts, onChange,
}: { clientId: string; assignments: ClientDetail['assignments']; proOpts: { value: string; label: string }[]; onChange: () => void }) {
  const [pro, setPro] = useState('')
  const [role, setRole] = useState<AssignmentRole>('consultant')
  const [err, setErr] = useState('')
  const add = async () => {
    if (!pro) return
    setErr('')
    try { await fractionalHr.addAssignment(clientId, { pro_user_id: pro, role }); setPro(''); onChange() }
    catch (e) { setErr(e instanceof Error ? e.message : 'Failed') }
  }
  return (
    <Card className="p-4 space-y-3">
      <h2 className="text-sm font-medium text-zinc-200">Engagement team</h2>
      <div className="flex gap-2 items-end">
        <div className="flex-1"><Select label="Pro" value={pro} onChange={(e) => setPro(e.target.value)} options={proOpts} /></div>
        <Select
          label="Role" value={role} onChange={(e) => setRole(e.target.value as AssignmentRole)}
          options={[{ value: 'lead', label: 'Lead' }, { value: 'consultant', label: 'Consultant' }, { value: 'jr', label: 'Junior' }]}
        />
        <Button size="sm" onClick={add}>Add</Button>
      </div>
      {err && <p className="text-sm text-rose-400">{err}</p>}
      <div className="space-y-1.5">
        {assignments.map((a) => (
          <div key={a.id} className="flex items-center justify-between px-3 py-2 rounded-md bg-zinc-900/50 text-sm">
            <span className="text-zinc-200">{a.email}</span>
            <div className="flex items-center gap-3">
              <Badge variant="neutral">{a.role}</Badge>
              <button onClick={async () => { await fractionalHr.removeAssignment(a.id); onChange() }} className="text-zinc-600 hover:text-rose-400"><Trash2 size={14} /></button>
            </div>
          </div>
        ))}
        {assignments.length === 0 && <p className="text-sm text-zinc-500">No team members assigned.</p>}
      </div>
    </Card>
  )
}

// --- Settings ------------------------------------------------------------- //
function SettingsTab({ client, pros, onSaved, onDeleted }: { client: FractionalClient; pros: Pro[]; onSaved: () => void; onDeleted: () => void }) {
  const [form, setForm] = useState({
    name: client.name, status: client.status, billing_model: client.billing_model,
    retainer_hours: client.retainer_hours?.toString() ?? '', retainer_period: client.retainer_period,
    billing_rate: client.billing_rate?.toString() ?? '', project_fee: client.project_fee?.toString() ?? '',
    industry: client.industry ?? '', headcount: client.headcount?.toString() ?? '',
    contact_email: client.contact_email ?? '', contact_name: client.contact_name ?? '',
    lead_pro_id: client.lead_pro_id ?? '', notes: client.notes ?? '',
  })
  const [companyQuery, setCompanyQuery] = useState('')
  const [companyResults, setCompanyResults] = useState<{ id: string; name: string }[]>([])
  const [saving, setSaving] = useState(false)
  const [confirmDel, setConfirmDel] = useState(false)

  const save = async () => {
    setSaving(true)
    try {
      await fractionalHr.updateClient(client.id, {
        name: form.name, status: form.status, billing_model: form.billing_model as BillingModel,
        retainer_hours: form.retainer_hours ? Number(form.retainer_hours) : null,
        retainer_period: form.retainer_period as FractionalClient['retainer_period'],
        billing_rate: form.billing_rate ? Number(form.billing_rate) : null,
        project_fee: form.project_fee ? Number(form.project_fee) : null,
        industry: form.industry || null, headcount: form.headcount ? Number(form.headcount) : null,
        contact_email: form.contact_email || null, contact_name: form.contact_name || null,
        lead_pro_id: form.lead_pro_id || null, notes: form.notes || null,
      })
      onSaved()
    } finally { setSaving(false) }
  }

  const searchCompanies = async (q: string) => {
    setCompanyQuery(q)
    if (q.length < 2) { setCompanyResults([]); return }
    const r = await fractionalHr.linkableCompanies(q)
    setCompanyResults(r.companies)
  }
  const linkCompany = async (id: string | null) => {
    await fractionalHr.updateClient(client.id, { company_id: id })
    setCompanyResults([]); setCompanyQuery(''); onSaved()
  }

  const proOpts = [{ value: '', label: 'Unassigned' }, ...pros.map((p) => ({ value: p.id, label: p.email }))]
  const billingOpts = (Object.keys(BILLING_LABELS) as BillingModel[]).map((v) => ({ value: v, label: BILLING_LABELS[v] }))

  return (
    <div className="space-y-4">
      <Card className="p-4 space-y-3">
        <h2 className="text-sm font-medium text-zinc-200">Engagement settings</h2>
        <div className="grid grid-cols-2 gap-3">
          <Input label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Select label="Status" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as FractionalClient['status'] })}
            options={[{ value: 'prospect', label: 'Prospect' }, { value: 'active', label: 'Active' }, { value: 'paused', label: 'Paused' }, { value: 'offboarded', label: 'Offboarded' }]} />
          <Select label="Billing model" value={form.billing_model} onChange={(e) => setForm({ ...form, billing_model: e.target.value as BillingModel })} options={billingOpts} />
          <Select label="Lead pro" value={form.lead_pro_id} onChange={(e) => setForm({ ...form, lead_pro_id: e.target.value })} options={proOpts} />
          <Input label="Retainer / block hours" type="number" value={form.retainer_hours} onChange={(e) => setForm({ ...form, retainer_hours: e.target.value })} />
          <Select label="Period" value={form.retainer_period} onChange={(e) => setForm({ ...form, retainer_period: e.target.value as FractionalClient['retainer_period'] })}
            options={[{ value: 'weekly', label: 'Weekly' }, { value: 'monthly', label: 'Monthly' }, { value: 'quarterly', label: 'Quarterly' }]} />
          <Input label="Rate ($/hr)" type="number" value={form.billing_rate} onChange={(e) => setForm({ ...form, billing_rate: e.target.value })} />
          <Input label="Project fee ($)" type="number" value={form.project_fee} onChange={(e) => setForm({ ...form, project_fee: e.target.value })} />
          <Input label="Industry" value={form.industry} onChange={(e) => setForm({ ...form, industry: e.target.value })} />
          <Input label="Headcount" type="number" value={form.headcount} onChange={(e) => setForm({ ...form, headcount: e.target.value })} />
          <Input label="Contact name" value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} />
          <Input label="Contact email" value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} />
        </div>
        <Textarea label="Notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} rows={3} />
        <div className="flex justify-end"><Button onClick={save} disabled={saving}>{saving ? <Loader2 size={16} className="animate-spin" /> : 'Save changes'}</Button></div>
      </Card>

      <Card className="p-4 space-y-2">
        <h2 className="text-sm font-medium text-zinc-200">Platform tenant link</h2>
        <p className="text-xs text-zinc-500">Link to an existing company to jump into its HR tooling (handbook, compliance, employees).</p>
        {client.company_id ? (
          <div className="flex items-center justify-between">
            <Link to={`/admin/companies/${client.company_id}`} className="text-emerald-400 hover:text-emerald-300 text-sm inline-flex items-center gap-1">
              <ExternalLink size={13} /> {client.company_name ?? 'Open company'}
            </Link>
            <Button size="sm" variant="secondary" onClick={() => linkCompany(null)}>Unlink</Button>
          </div>
        ) : (
          <div className="relative">
            <Input placeholder="Search companies to link…" value={companyQuery} onChange={(e) => searchCompanies(e.target.value)} />
            {companyResults.length > 0 && (
              <div className="absolute z-10 mt-1 w-full bg-zinc-900 border border-white/10 rounded-md max-h-48 overflow-auto">
                {companyResults.map((co) => (
                  <button key={co.id} onClick={() => linkCompany(co.id)} className="w-full text-left px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-800">{co.name}</button>
                ))}
              </div>
            )}
          </div>
        )}
      </Card>

      <Card className="p-4 border-rose-500/20">
        <h2 className="text-sm font-medium text-rose-300 mb-2">Danger zone</h2>
        {confirmDel ? (
          <div className="flex items-center gap-2">
            <span className="text-sm text-zinc-400">Delete this engagement and all its scope, tasks, and time?</span>
            <Button size="sm" variant="secondary" className="!bg-rose-600 !text-white hover:!bg-rose-500" onClick={async () => { await fractionalHr.deleteClient(client.id); onDeleted() }}>Delete</Button>
            <Button size="sm" variant="secondary" onClick={() => setConfirmDel(false)}>Cancel</Button>
          </div>
        ) : (
          <Button size="sm" variant="secondary" className="!bg-rose-600 !text-white hover:!bg-rose-500" onClick={() => setConfirmDel(true)}>Delete engagement</Button>
        )}
      </Card>
    </div>
  )
}
