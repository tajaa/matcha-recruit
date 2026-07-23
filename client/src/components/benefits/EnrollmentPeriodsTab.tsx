import { useEffect, useState } from 'react'
import { Plus, Loader2, PlayCircle, StopCircle } from 'lucide-react'
import { Badge, Button, DataTable, Input, Modal, useToast } from '../../components/ui'
import type { Column } from '../../components/ui'
import { benefitsApi } from '../../api/benefits/benefits'
import type { OePeriod } from '../../api/benefits/benefits'

const STATUS_VARIANT = { draft: 'neutral', open: 'success', closed: 'neutral' } as const

export function EnrollmentPeriodsTab({ onSelect }: { onSelect: (period: OePeriod) => void }) {
  const { toast } = useToast()
  const [periods, setPeriods] = useState<OePeriod[]>([])
  const [loading, setLoading] = useState(true)
  const [showNew, setShowNew] = useState(false)
  const [form, setForm] = useState({ name: '', starts_on: '', ends_on: '', plan_year_start: '' })
  const [saving, setSaving] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const res = await benefitsApi.listPeriods()
      setPeriods(res.periods)
    } catch {
      toast('Failed to load enrollment periods', 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function create() {
    setSaving(true)
    try {
      await benefitsApi.createPeriod({
        name: form.name, starts_on: form.starts_on, ends_on: form.ends_on,
        plan_year_start: form.plan_year_start || null,
      })
      setShowNew(false)
      setForm({ name: '', starts_on: '', ends_on: '', plan_year_start: '' })
      await load()
      toast('Enrollment period created', 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to create period', 'error')
    } finally {
      setSaving(false)
    }
  }

  async function open(period: OePeriod) {
    try {
      await benefitsApi.openPeriod(period.id)
      await load()
      toast('Period opened', 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to open period', 'error')
    }
  }

  async function close(period: OePeriod) {
    try {
      await benefitsApi.closePeriod(period.id)
      await load()
      toast('Period closed', 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to close period', 'error')
    }
  }

  const columns: Column<OePeriod>[] = [
    { key: 'name', header: 'Period', render: (p) => <button className="font-medium text-zinc-100 hover:underline" onClick={() => onSelect(p)}>{p.name}</button> },
    { key: 'window', header: 'Window', render: (p) => `${p.starts_on} → ${p.ends_on}` },
    { key: 'plan_year', header: 'Plan year start', render: (p) => p.plan_year_start ?? '—' },
    { key: 'status', header: 'Status', render: (p) => <Badge variant={STATUS_VARIANT[p.status]}>{p.status}</Badge> },
    {
      key: 'actions', header: '', align: 'right', render: (p) => (
        <div className="flex justify-end gap-2">
          {p.status === 'draft' && (
            <Button size="sm" variant="ghost" onClick={() => open(p)}><PlayCircle className="w-3.5 h-3.5" /><span className="ml-1">Open</span></Button>
          )}
          {p.status === 'open' && (
            <Button size="sm" variant="ghost" onClick={() => close(p)}><StopCircle className="w-3.5 h-3.5" /><span className="ml-1">Close</span></Button>
          )}
        </div>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setShowNew(true)}><Plus className="w-4 h-4" /><span className="ml-2">New period</span></Button>
      </div>
      <DataTable columns={columns} rows={periods} rowKey={(p) => p.id} loading={loading} emptyText="No enrollment periods yet." />

      <Modal open={showNew} onClose={() => setShowNew(false)} title="New enrollment period">
        <div className="space-y-3">
          <Input label="Name" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
          <div className="grid grid-cols-2 gap-3">
            <Input label="Starts on" type="date" value={form.starts_on} onChange={(e) => setForm((f) => ({ ...f, starts_on: e.target.value }))} />
            <Input label="Ends on" type="date" value={form.ends_on} onChange={(e) => setForm((f) => ({ ...f, ends_on: e.target.value }))} />
          </div>
          <Input label="Plan year start (optional)" type="date" value={form.plan_year_start} onChange={(e) => setForm((f) => ({ ...f, plan_year_start: e.target.value }))} />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowNew(false)}>Cancel</Button>
            <Button onClick={create} disabled={saving || !form.name || !form.starts_on || !form.ends_on}>
              {saving && <Loader2 className="w-4 h-4 animate-spin" />} Create
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
