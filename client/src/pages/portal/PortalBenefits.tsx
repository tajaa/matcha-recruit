import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Check, HeartPulse, Loader2 } from 'lucide-react'
import { Badge, Button, Card, Modal, Select, Textarea, Toggle, useToast } from '../../components/ui'
import { portalBenefitsApi } from '../../api/portal/portalBenefits'
import type { MyBenefits, MyPlan } from '../../api/portal/portalBenefits'
import type { Dependent, DependentRelationship, LifeEvent, LifeEventType } from '../../api/benefits/benefits'

const LIFE_EVENT_OPTIONS: { value: LifeEventType; label: string }[] = [
  { value: 'marriage', label: 'Marriage' },
  { value: 'divorce', label: 'Divorce' },
  { value: 'birth_adoption', label: 'Birth / adoption' },
  { value: 'death_of_dependent', label: 'Death of dependent' },
  { value: 'loss_of_coverage', label: 'Loss of other coverage' },
  { value: 'gain_of_coverage', label: 'Gain of other coverage' },
  { value: 'dependent_status_change', label: 'Dependent status change' },
  { value: 'relocation', label: 'Relocation' },
  { value: 'other', label: 'Other' },
]

const RELATIONSHIP_OPTIONS: { value: DependentRelationship; label: string }[] = [
  { value: 'spouse', label: 'Spouse' },
  { value: 'child', label: 'Child' },
  { value: 'domestic_partner', label: 'Domestic partner' },
  { value: 'other', label: 'Other' },
]

type PlanSelection = { tierId: string; waived: boolean; dependents: Dependent[] }

export default function PortalBenefits() {
  const { toast } = useToast()
  const [data, setData] = useState<MyBenefits | null>(null)
  const [loading, setLoading] = useState(true)
  const [selections, setSelections] = useState<Record<string, PlanSelection>>({})
  const [saving, setSaving] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [confirmSubmit, setConfirmSubmit] = useState(false)
  const [lifeEvents, setLifeEvents] = useState<LifeEvent[]>([])
  const [showLifeEventForm, setShowLifeEventForm] = useState(false)
  const [leForm, setLeForm] = useState({ event_type: 'marriage' as LifeEventType, event_date: '', description: '' })

  const load = useCallback(async () => {
    const [benefits, events] = await Promise.all([
      portalBenefitsApi.getMyBenefits(),
      portalBenefitsApi.listLifeEvents(),
    ])
    setData(benefits)
    setLifeEvents(events.life_events)
    const next: Record<string, PlanSelection> = {}
    for (const el of benefits.my_elections) {
      next[el.plan_type] = { tierId: el.tier_id ?? '', waived: el.waived, dependents: el.dependents }
    }
    setSelections(next)
  }, [])

  useEffect(() => {
    load().catch(() => toast('Failed to load your benefits', 'error')).finally(() => setLoading(false))
  }, [load, toast])

  async function saveElection(plan: MyPlan) {
    const sel = selections[plan.plan_type]
    if (!sel) return
    setSaving(plan.plan_type)
    try {
      await portalBenefitsApi.upsertElection({
        plan_type: plan.plan_type,
        plan_id: sel.waived ? null : plan.id,
        tier_id: sel.waived ? null : sel.tierId,
        waived: sel.waived,
        dependents: sel.waived ? [] : sel.dependents,
      })
      await load()
      toast('Saved', 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to save election', 'error')
    } finally {
      setSaving(null)
    }
  }

  async function submitAll() {
    setSubmitting(true)
    try {
      await portalBenefitsApi.submitElections()
      setConfirmSubmit(false)
      await load()
      toast('Elections submitted', 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to submit elections', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  async function reportLifeEvent() {
    try {
      await portalBenefitsApi.reportLifeEvent({
        event_type: leForm.event_type, event_date: leForm.event_date, description: leForm.description || null,
      })
      setShowLifeEventForm(false)
      setLeForm({ event_type: 'marriage', event_date: '', description: '' })
      await load()
      toast('Life event reported — awaiting review', 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to report life event', 'error')
    }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>

  const draftCount = data?.my_elections.filter((e) => e.status === 'draft').length ?? 0

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-zinc-100">
          <HeartPulse className="w-5 h-5" /> My Benefits
        </h1>
      </div>

      {!data?.window && (
        <Card className="p-4 flex items-start gap-3 border-amber-900/50">
          <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
          <div className="text-sm text-zinc-300">No active enrollment window right now. Check back during open enrollment, or report a qualifying life event below.</div>
        </Card>
      )}

      {data?.window && (
        <Card className="p-4 flex items-center justify-between">
          <div className="text-sm text-zinc-300">
            Enrollment window open{data.window.ends_on ? ` — closes ${data.window.ends_on}` : ''}.
          </div>
          <Button onClick={() => setConfirmSubmit(true)} disabled={draftCount === 0}>
            Submit elections{draftCount ? ` (${draftCount})` : ''}
          </Button>
        </Card>
      )}

      {data?.window && data.plans.map((plan) => {
        const sel = selections[plan.plan_type] ?? { tierId: '', waived: false, dependents: [] }
        const myElection = data.my_elections.find((e) => e.plan_type === plan.plan_type)
        const locked = myElection?.status === 'submitted' || myElection?.status === 'approved'
        return (
          <Card key={plan.id} className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium text-zinc-100">{plan.name}</div>
                <div className="text-xs text-zinc-500">{plan.carrier_name}</div>
              </div>
              {myElection && <Badge variant={locked ? 'success' : 'neutral'}>{myElection.status}</Badge>}
            </div>

            {plan.waivable && (
              <div className="flex items-center gap-2">
                <Toggle checked={sel.waived} disabled={locked}
                  onChange={(v) => setSelections((s) => ({ ...s, [plan.plan_type]: { ...sel, waived: v } }))} />
                <span className="text-sm text-zinc-300">Waive this coverage</span>
              </div>
            )}

            {!sel.waived && (
              <Select
                label="Coverage tier" disabled={locked}
                value={sel.tierId}
                options={plan.tiers.map((t) => ({
                  value: t.id,
                  label: `${t.coverage_tier.replace(/_/g, ' ')} — $${t.employee_cost}/${t.cost_period === 'monthly' ? 'mo' : 'pay period'}`,
                }))}
                onChange={(e) => setSelections((s) => ({ ...s, [plan.plan_type]: { ...sel, tierId: e.target.value } }))}
              />
            )}

            {!sel.waived && sel.tierId && (
              <DependentsEditor
                dependents={sel.dependents}
                disabled={locked}
                onChange={(dependents) => setSelections((s) => ({ ...s, [plan.plan_type]: { ...sel, dependents } }))}
              />
            )}

            {!locked && (
              <div className="flex justify-end">
                <Button size="sm" onClick={() => saveElection(plan)} disabled={saving === plan.plan_type || (!sel.waived && !sel.tierId)}>
                  {saving === plan.plan_type && <Loader2 className="w-3.5 h-3.5 animate-spin" />} Save
                </Button>
              </div>
            )}
          </Card>
        )
      })}

      {data && data.current_coverage.length > 0 && (
        <Card className="p-4">
          <div className="text-sm font-medium text-zinc-300 mb-2">Current approved coverage</div>
          <div className="space-y-1 text-sm text-zinc-400">
            {data.current_coverage.map((c) => (
              <div key={c.id}>{c.plan_type}: {c.waived ? 'Waived' : `${c.plan_name ?? ''} (${c.coverage_tier ?? ''})`}</div>
            ))}
          </div>
        </Card>
      )}

      <Card className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="text-sm font-medium text-zinc-300">Life events</div>
          <Button size="sm" variant="ghost" onClick={() => setShowLifeEventForm(true)}>Report a life event</Button>
        </div>
        <div className="space-y-1 text-sm text-zinc-400">
          {lifeEvents.length === 0 && <div>No life events reported.</div>}
          {lifeEvents.map((e) => (
            <div key={e.id} className="flex items-center justify-between">
              <span>{e.event_type.replace(/_/g, ' ')} — {e.event_date}</span>
              <Badge variant={e.status === 'approved' ? 'success' : e.status === 'denied' ? 'danger' : 'neutral'}>{e.status}</Badge>
            </div>
          ))}
        </div>
      </Card>

      <Modal open={confirmSubmit} onClose={() => setConfirmSubmit(false)} title="Submit elections?">
        <div className="space-y-3">
          <p className="text-sm text-zinc-400">This submits all your draft elections for review. You won't be able to edit them until a decision is made.</p>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setConfirmSubmit(false)}>Cancel</Button>
            <Button onClick={submitAll} disabled={submitting}>
              {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />} Submit
            </Button>
          </div>
        </div>
      </Modal>

      <Modal open={showLifeEventForm} onClose={() => setShowLifeEventForm(false)} title="Report a life event">
        <div className="space-y-3">
          <Select label="Event type" value={leForm.event_type} options={LIFE_EVENT_OPTIONS}
            onChange={(e) => setLeForm((f) => ({ ...f, event_type: e.target.value as LifeEventType }))} />
          <label className="block">
            <span className="block text-sm font-medium text-zinc-300 mb-1.5">Event date</span>
            <input type="date" className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3.5 py-2.5 text-sm text-zinc-100"
              value={leForm.event_date} onChange={(e) => setLeForm((f) => ({ ...f, event_date: e.target.value }))} />
          </label>
          <Textarea label="Description (optional)" value={leForm.description} onChange={(e) => setLeForm((f) => ({ ...f, description: e.target.value }))} />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowLifeEventForm(false)}>Cancel</Button>
            <Button onClick={reportLifeEvent} disabled={!leForm.event_date}>Report</Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}

function DependentsEditor({ dependents, disabled, onChange }: {
  dependents: Dependent[]; disabled: boolean; onChange: (d: Dependent[]) => void
}) {
  function update(i: number, patch: Partial<Dependent>) {
    const next = [...dependents]
    next[i] = { ...next[i], ...patch }
    onChange(next)
  }
  function add() {
    onChange([...dependents, { name: '', relationship: 'spouse' as DependentRelationship, dob: '' }])
  }
  function remove(i: number) {
    onChange(dependents.filter((_, idx) => idx !== i))
  }
  return (
    <div className="space-y-2">
      <div className="text-xs text-zinc-500">Dependents</div>
      {dependents.map((d, i) => (
        <div key={i} className="grid grid-cols-3 gap-2 items-end">
          <label className="block">
            <span className="block text-xs text-zinc-400 mb-1">Name</span>
            <input disabled={disabled} className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100"
              value={d.name} onChange={(e) => update(i, { name: e.target.value })} />
          </label>
          <Select label="Relationship" disabled={disabled} value={d.relationship} options={RELATIONSHIP_OPTIONS}
            onChange={(e) => update(i, { relationship: e.target.value as DependentRelationship })} />
          <div className="flex items-end gap-2">
            <label className="flex-1">
              <span className="block text-xs text-zinc-400 mb-1">DOB</span>
              <input type="date" disabled={disabled} className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100"
                value={d.dob ?? ''} onChange={(e) => update(i, { dob: e.target.value })} />
            </label>
            {!disabled && <Button size="sm" variant="ghost" onClick={() => remove(i)}>Remove</Button>}
          </div>
        </div>
      ))}
      {!disabled && <Button size="sm" variant="ghost" onClick={add}>+ Add dependent</Button>}
    </div>
  )
}
