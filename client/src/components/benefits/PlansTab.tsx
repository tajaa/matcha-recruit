import { useEffect, useState } from 'react'
import { Plus, Loader2, Archive, Trash2, Pencil } from 'lucide-react'
import { Badge, Button, Card, DataTable, Input, Modal, Select, Toggle, useToast } from '../../components/ui'
import type { Column } from '../../components/ui'
import { benefitsApi } from '../../api/benefits/benefits'
import type { CostPeriod, CoverageTier, Plan, PlanCreateInput, PlanType, TierInput } from '../../api/benefits/benefits'

const PLAN_TYPE_OPTIONS = [
  { value: 'medical', label: 'Medical' },
  { value: 'dental', label: 'Dental' },
  { value: 'vision', label: 'Vision' },
  { value: 'life', label: 'Life' },
  { value: 'disability', label: 'Disability' },
  { value: 'other', label: 'Other' },
]

const COVERAGE_TIERS: { value: CoverageTier; label: string }[] = [
  { value: 'employee_only', label: 'Employee only' },
  { value: 'employee_spouse', label: 'Employee + spouse' },
  { value: 'employee_children', label: 'Employee + children' },
  { value: 'family', label: 'Family' },
]

const COST_PERIOD_OPTIONS = [
  { value: 'monthly', label: 'Monthly' },
  { value: 'per_pay_period', label: 'Per pay period' },
]

function emptyTiers(): TierInput[] {
  return COVERAGE_TIERS.map((t) => ({
    coverage_tier: t.value, employee_cost: 0, employer_cost: 0, cost_period: 'monthly' as CostPeriod,
  }))
}

export function PlansTab() {
  const { toast } = useToast()
  const [plans, setPlans] = useState<Plan[]>([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState<Plan | null>(null)
  const [showEditor, setShowEditor] = useState(false)
  const [form, setForm] = useState<PlanCreateInput>({ plan_type: 'medical', name: '', carrier_name: '', description: '', waivable: true, tiers: emptyTiers() })
  const [saving, setSaving] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const res = await benefitsApi.listPlans()
      setPlans(res.plans)
    } catch {
      toast('Failed to load plans', 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  function openNew() {
    setEditing(null)
    setForm({ plan_type: 'medical', name: '', carrier_name: '', description: '', waivable: true, tiers: emptyTiers() })
    setShowEditor(true)
  }

  function openEdit(plan: Plan) {
    setEditing(plan)
    const byTier = new Map(plan.tiers.map((t) => [t.coverage_tier, t]))
    setForm({
      plan_type: plan.plan_type,
      name: plan.name,
      carrier_name: plan.carrier_name ?? '',
      description: plan.description ?? '',
      waivable: plan.waivable,
      tiers: COVERAGE_TIERS.map((t) => {
        const existing = byTier.get(t.value)
        return {
          coverage_tier: t.value,
          employee_cost: existing?.employee_cost ?? 0,
          employer_cost: existing?.employer_cost ?? 0,
          cost_period: existing?.cost_period ?? 'monthly',
        }
      }),
    })
    setShowEditor(true)
  }

  async function save() {
    setSaving(true)
    try {
      if (editing) {
        await benefitsApi.updatePlan(editing.id, {
          name: form.name, carrier_name: form.carrier_name, description: form.description, waivable: form.waivable,
        })
        await benefitsApi.replaceTiers(editing.id, form.tiers)
      } else {
        await benefitsApi.createPlan(form)
      }
      setShowEditor(false)
      await load()
      toast(editing ? 'Plan updated' : 'Plan created', 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to save plan', 'error')
    } finally {
      setSaving(false)
    }
  }

  async function archive(plan: Plan) {
    try {
      const res = await benefitsApi.deletePlan(plan.id)
      await load()
      toast(res.result === 'archived' ? 'Plan archived (has elections)' : 'Plan deleted', 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to remove plan', 'error')
    }
  }

  const columns: Column<Plan>[] = [
    { key: 'name', header: 'Plan', render: (p) => <span className="font-medium text-zinc-100">{p.name}</span> },
    { key: 'type', header: 'Type', render: (p) => <Badge>{p.plan_type}</Badge> },
    { key: 'carrier', header: 'Carrier', render: (p) => p.carrier_name ?? '—' },
    { key: 'tiers', header: 'Tiers', render: (p) => `${p.tiers.length}` },
    { key: 'status', header: 'Status', render: (p) => <Badge variant={p.status === 'active' ? 'success' : p.status === 'archived' ? 'neutral' : 'warning'}>{p.status}</Badge> },
    {
      key: 'actions', header: '', align: 'right', render: (p) => (
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="ghost" onClick={() => openEdit(p)}><Pencil className="w-3.5 h-3.5" /></Button>
          <Button size="sm" variant="ghost" onClick={() => archive(p)}>
            {p.status === 'archived' ? <Trash2 className="w-3.5 h-3.5" /> : <Archive className="w-3.5 h-3.5" />}
          </Button>
        </div>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={openNew}><Plus className="w-4 h-4" /><span className="ml-2">New plan</span></Button>
      </div>
      <DataTable columns={columns} rows={plans} rowKey={(p) => p.id} loading={loading} emptyText="No benefit plans yet." />

      <Modal open={showEditor} onClose={() => setShowEditor(false)} title={editing ? 'Edit plan' : 'New plan'} width="lg">
        <div className="space-y-4">
          <div className="grid sm:grid-cols-2 gap-3">
            <Select label="Plan type" options={PLAN_TYPE_OPTIONS} value={form.plan_type} disabled={!!editing}
              onChange={(e) => setForm((f) => ({ ...f, plan_type: e.target.value as PlanType }))} />
            <Input label="Name" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
            <Input label="Carrier" value={form.carrier_name ?? ''} onChange={(e) => setForm((f) => ({ ...f, carrier_name: e.target.value }))} />
            <div className="flex items-center gap-2 pt-6">
              <Toggle checked={form.waivable ?? true} onChange={(v) => setForm((f) => ({ ...f, waivable: v }))} />
              <span className="text-sm text-zinc-300">Waivable</span>
            </div>
          </div>
          <Input label="Description" value={form.description ?? ''} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} />

          <div>
            <div className="text-sm font-medium text-zinc-300 mb-2">Coverage tiers</div>
            <div className="space-y-2">
              {form.tiers.map((tier, i) => (
                <Card key={tier.coverage_tier} className="p-3 grid grid-cols-4 gap-2 items-end">
                  <div className="text-sm text-zinc-300">{COVERAGE_TIERS.find((t) => t.value === tier.coverage_tier)?.label}</div>
                  <Input label="Employee cost" type="number" value={tier.employee_cost}
                    onChange={(e) => setForm((f) => {
                      const tiers = [...f.tiers]; tiers[i] = { ...tiers[i], employee_cost: Number(e.target.value) }; return { ...f, tiers }
                    })} />
                  <Input label="Employer cost" type="number" value={tier.employer_cost}
                    onChange={(e) => setForm((f) => {
                      const tiers = [...f.tiers]; tiers[i] = { ...tiers[i], employer_cost: Number(e.target.value) }; return { ...f, tiers }
                    })} />
                  <Select label="Period" options={COST_PERIOD_OPTIONS} value={tier.cost_period}
                    onChange={(e) => setForm((f) => {
                      const tiers = [...f.tiers]; tiers[i] = { ...tiers[i], cost_period: e.target.value as CostPeriod }; return { ...f, tiers }
                    })} />
                </Card>
              ))}
            </div>
          </div>

          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowEditor(false)}>Cancel</Button>
            <Button onClick={save} disabled={saving || !form.name}>
              {saving && <Loader2 className="w-4 h-4 animate-spin" />} Save
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
