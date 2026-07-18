import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Badge, Button, Card, Input, Modal, Select } from '../../components/ui'
import { AlertTriangle, Clock, Loader2, Plus, Users } from 'lucide-react'
import {
  fractionalHr,
  BILLING_LABELS,
  serviceLabel,
  type BillingModel,
  type ClientStatus,
  type FractionalClient,
  type Overview,
  type Pro,
} from '../../api/admin/fractionalHr'

const STATUS_VARIANT: Record<string, 'success' | 'warning' | 'neutral' | 'danger'> = {
  active: 'success',
  prospect: 'neutral',
  paused: 'warning',
  offboarded: 'danger',
}

const BILLING_OPTS: { value: BillingModel; label: string }[] = (
  Object.keys(BILLING_LABELS) as BillingModel[]
).map((v) => ({ value: v, label: BILLING_LABELS[v] }))

function Util({ summary }: { summary?: FractionalClient['hours_summary'] }) {
  if (!summary) return <span className="text-zinc-500">—</span>
  if (summary.utilization_pct == null) {
    return (
      <span className="text-zinc-400 text-xs">
        {summary.used ?? 0}h logged{summary.basis === 'project' ? ' (project)' : ''}
      </span>
    )
  }
  const pct = summary.utilization_pct
  const color = pct > 100 ? 'bg-rose-500' : pct > 80 ? 'bg-amber-500' : 'bg-emerald-500'
  return (
    <div className="w-32">
      <div className="flex justify-between text-[10px] text-zinc-400 mb-0.5">
        <span>{summary.used ?? 0}/{summary.budget ?? 0}h</span>
        <span className={pct > 100 ? 'text-rose-400 font-medium' : ''}>{pct}%</span>
      </div>
      <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
    </div>
  )
}

function Kpi({ label, value, sub, icon }: { label: string; value: string | number; sub?: string; icon?: React.ReactNode }) {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs uppercase tracking-wide text-zinc-500">{label}</span>
        {icon}
      </div>
      <div className="mt-2 text-2xl font-semibold text-zinc-100">{value}</div>
      {sub && <div className="text-xs text-zinc-500 mt-0.5">{sub}</div>}
    </Card>
  )
}

const EMPTY_FORM = {
  name: '',
  status: 'prospect' as ClientStatus,
  billing_model: 'monthly_retainer' as BillingModel,
  retainer_hours: '',
  retainer_period: 'monthly',
  billing_rate: '',
  project_fee: '',
  industry: '',
  headcount: '',
  contact_email: '',
  lead_pro_id: '',
}

export default function FractionalHR() {
  const navigate = useNavigate()
  const [overview, setOverview] = useState<Overview | null>(null)
  const [clients, setClients] = useState<FractionalClient[]>([])
  const [pros, setPros] = useState<Pro[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [addError, setAddError] = useState('')

  async function load() {
    setLoading(true)
    try {
      const [ov, cl, pr] = await Promise.all([
        fractionalHr.overview(),
        fractionalHr.listClients(statusFilter ? { status: statusFilter } : undefined),
        fractionalHr.pros(),
      ])
      setOverview(ov)
      setClients(cl.clients)
      setPros(pr.pros)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter])

  const filtered = useMemo(
    () => clients.filter((c) => c.name.toLowerCase().includes(search.toLowerCase())),
    [clients, search],
  )

  async function submitAdd() {
    if (form.name.trim().length < 2) {
      setAddError('Name is required')
      return
    }
    setSaving(true)
    setAddError('')
    try {
      const created = await fractionalHr.createClient({
        name: form.name.trim(),
        status: form.status,
        billing_model: form.billing_model,
        retainer_hours: form.retainer_hours ? Number(form.retainer_hours) : null,
        retainer_period: form.retainer_period as FractionalClient['retainer_period'],
        billing_rate: form.billing_rate ? Number(form.billing_rate) : null,
        project_fee: form.project_fee ? Number(form.project_fee) : null,
        industry: form.industry || null,
        headcount: form.headcount ? Number(form.headcount) : null,
        contact_email: form.contact_email || null,
        lead_pro_id: form.lead_pro_id || null,
      })
      setShowAdd(false)
      setForm(EMPTY_FORM)
      navigate(`/admin/fractional-hr/${created.id}`)
    } catch (e) {
      setAddError(e instanceof Error ? e.message : 'Failed to create client')
    } finally {
      setSaving(false)
    }
  }

  const proOpts = [{ value: '', label: 'Unassigned' }, ...pros.map((p) => ({ value: p.id, label: p.email }))]
  const showRetainer = form.billing_model === 'monthly_retainer' || form.billing_model === 'hours_block'
  const showRate = form.billing_model === 'hourly' || form.billing_model === 'monthly_retainer'

  if (loading && !overview) {
    return (
      <div className="flex items-center justify-center h-64 text-zinc-500">
        <Loader2 className="animate-spin" />
      </div>
    )
  }

  const activeCount = overview?.status_counts.active ?? 0
  const prospectCount = overview?.status_counts.prospect ?? 0

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">Fractional HR</h1>
          <p className="text-sm text-zinc-500">Book of business — engagements we run HR for.</p>
        </div>
        <Button onClick={() => setShowAdd(true)}>
          <Plus size={16} className="mr-1" /> New client
        </Button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <Kpi label="Active clients" value={activeCount} sub={`${prospectCount} prospects`} icon={<Users size={16} className="text-zinc-600" />} />
        <Kpi label="Committed hrs/mo" value={overview?.committed_retainer_hours ?? 0} sub="active retainers" />
        <Kpi label="Logged this month" value={`${overview?.hours_logged_this_month ?? 0}h`} icon={<Clock size={16} className="text-zinc-600" />} />
        <Kpi label="Open tasks" value={overview?.open_tasks ?? 0} />
        <Kpi label="Overdue tasks" value={overview?.overdue_tasks ?? 0} sub="needs attention" icon={<AlertTriangle size={16} className="text-amber-600" />} />
        <Kpi label="Done this month" value={overview?.tasks_completed_this_month ?? 0} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* At-risk */}
        <Card className="p-4 lg:col-span-2">
          <h2 className="text-sm font-medium text-zinc-200 mb-3 flex items-center gap-1.5">
            <AlertTriangle size={14} className="text-amber-500" /> Needs attention
          </h2>
          {overview && overview.at_risk.length === 0 ? (
            <p className="text-sm text-zinc-500">Nothing at risk — over-budget retainers and overdue tasks show here.</p>
          ) : (
            <div className="space-y-1.5">
              {overview?.at_risk.map((r) => (
                <button
                  key={r.id}
                  onClick={() => navigate(`/admin/fractional-hr/${r.id}`)}
                  className="w-full flex items-center justify-between text-left px-3 py-2 rounded-md bg-zinc-900/60 hover:bg-zinc-800 transition"
                >
                  <span className="text-sm text-zinc-200">{r.name}</span>
                  <span className="flex items-center gap-3 text-xs">
                    {r.overdue_tasks > 0 && <span className="text-rose-400">{r.overdue_tasks} overdue</span>}
                    {r.retainer_hours != null && (r.month_hours ?? 0) > r.retainer_hours && (
                      <span className="text-amber-400">{r.month_hours}/{r.retainer_hours}h</span>
                    )}
                  </span>
                </button>
              ))}
            </div>
          )}
        </Card>

        {/* Pro load */}
        <Card className="p-4">
          <h2 className="text-sm font-medium text-zinc-200 mb-3">Team load (this month)</h2>
          {overview && overview.pro_load.length === 0 ? (
            <p className="text-sm text-zinc-500">No pros assigned yet.</p>
          ) : (
            <div className="space-y-2">
              {overview?.pro_load.map((p) => (
                <div key={p.id} className="flex items-center justify-between text-xs">
                  <span className="text-zinc-300 truncate max-w-[140px]">{p.email}</span>
                  <span className="text-zinc-500">
                    {p.clients_led} led · {p.open_tasks} open · {p.hours_month ?? 0}h
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Work by category */}
      {overview && overview.work_by_category.length > 0 && (
        <Card className="p-4">
          <h2 className="text-sm font-medium text-zinc-200 mb-3">Open work by service area</h2>
          <div className="flex flex-wrap gap-2">
            {overview.work_by_category.map((c) => (
              <Badge key={c.service_category} variant="neutral">
                {serviceLabel(c.service_category)} · {c.count}
              </Badge>
            ))}
          </div>
        </Card>
      )}

      {/* Roster */}
      <Card className="p-4">
        <div className="flex items-center justify-between gap-3 mb-3">
          <h2 className="text-sm font-medium text-zinc-200">Clients</h2>
          <div className="flex items-center gap-2">
            <Input placeholder="Search…" value={search} onChange={(e) => setSearch(e.target.value)} className="w-44" />
            <Select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              placeholder="All statuses"
              options={[
                { value: 'active', label: 'Active' },
                { value: 'prospect', label: 'Prospect' },
                { value: 'paused', label: 'Paused' },
                { value: 'offboarded', label: 'Offboarded' },
              ]}
            />
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-zinc-500 border-b border-white/[0.06]">
                <th className="py-2 pr-3 font-medium">Client</th>
                <th className="py-2 px-3 font-medium">Status</th>
                <th className="py-2 px-3 font-medium">Model</th>
                <th className="py-2 px-3 font-medium">Utilization</th>
                <th className="py-2 px-3 font-medium">Tasks</th>
                <th className="py-2 px-3 font-medium">Lead</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c) => (
                <tr
                  key={c.id}
                  onClick={() => navigate(`/admin/fractional-hr/${c.id}`)}
                  className="border-b border-white/[0.04] hover:bg-zinc-800/40 cursor-pointer"
                >
                  <td className="py-2.5 pr-3">
                    <div className="text-zinc-100">{c.name}</div>
                    {c.company_name && <div className="text-[11px] text-zinc-500">↳ {c.company_name}</div>}
                  </td>
                  <td className="py-2.5 px-3">
                    <Badge variant={STATUS_VARIANT[c.status] ?? 'neutral'}>{c.status}</Badge>
                  </td>
                  <td className="py-2.5 px-3 text-zinc-400 text-xs">{BILLING_LABELS[c.billing_model]}</td>
                  <td className="py-2.5 px-3"><Util summary={c.hours_summary} /></td>
                  <td className="py-2.5 px-3 text-xs">
                    <span className="text-zinc-300">{c.open_tasks ?? 0} open</span>
                    {(c.overdue_tasks ?? 0) > 0 && <span className="text-rose-400 ml-1.5">{c.overdue_tasks} overdue</span>}
                  </td>
                  <td className="py-2.5 px-3 text-xs text-zinc-400 truncate max-w-[160px]">{c.lead_pro_email ?? '—'}</td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-zinc-500 text-sm">
                    No clients yet. Create your first fractional HR engagement.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* New client modal */}
      <Modal open={showAdd} onClose={() => setShowAdd(false)} title="New fractional HR client">
        <div className="space-y-3">
          <Input label="Client name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} autoFocus />
          <div className="grid grid-cols-2 gap-3">
            <Select
              label="Status"
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value as ClientStatus })}
              options={[
                { value: 'prospect', label: 'Prospect' },
                { value: 'active', label: 'Active' },
                { value: 'paused', label: 'Paused' },
              ]}
            />
            <Select
              label="Billing model"
              value={form.billing_model}
              onChange={(e) => setForm({ ...form, billing_model: e.target.value as BillingModel })}
              options={BILLING_OPTS}
            />
          </div>
          {showRetainer && (
            <div className="grid grid-cols-2 gap-3">
              <Input
                label={form.billing_model === 'hours_block' ? 'Block hours' : 'Retainer hours'}
                type="number"
                value={form.retainer_hours}
                onChange={(e) => setForm({ ...form, retainer_hours: e.target.value })}
              />
              {form.billing_model === 'monthly_retainer' && (
                <Select
                  label="Period"
                  value={form.retainer_period}
                  onChange={(e) => setForm({ ...form, retainer_period: e.target.value })}
                  options={[
                    { value: 'weekly', label: 'Weekly' },
                    { value: 'monthly', label: 'Monthly' },
                    { value: 'quarterly', label: 'Quarterly' },
                  ]}
                />
              )}
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            {showRate && (
              <Input
                label="Rate ($/hr)"
                type="number"
                value={form.billing_rate}
                onChange={(e) => setForm({ ...form, billing_rate: e.target.value })}
              />
            )}
            {form.billing_model === 'project_fixed' && (
              <Input
                label="Project fee ($)"
                type="number"
                value={form.project_fee}
                onChange={(e) => setForm({ ...form, project_fee: e.target.value })}
              />
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Input label="Industry" value={form.industry} onChange={(e) => setForm({ ...form, industry: e.target.value })} />
            <Input label="Headcount" type="number" value={form.headcount} onChange={(e) => setForm({ ...form, headcount: e.target.value })} />
          </div>
          <Input label="Contact email" value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} />
          <Select label="Lead pro" value={form.lead_pro_id} onChange={(e) => setForm({ ...form, lead_pro_id: e.target.value })} options={proOpts} />
          {addError && <p className="text-sm text-rose-400">{addError}</p>}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setShowAdd(false)}>Cancel</Button>
            <Button onClick={submitAdd} disabled={saving}>
              {saving ? <Loader2 size={16} className="animate-spin" /> : 'Create'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
