import { useEffect, useState } from 'react'
import { Check, Loader2, X } from 'lucide-react'
import { Badge, Button, DataTable, Modal, Textarea, useToast } from '../../components/ui'
import type { Column } from '../../components/ui'
import { benefitsApi } from '../../api/benefits/benefits'
import type { LifeEvent } from '../../api/benefits/benefits'

export function LifeEventsTab() {
  const { toast } = useToast()
  const [events, setEvents] = useState<LifeEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [decision, setDecision] = useState<{ event: LifeEvent; action: 'approve' | 'deny' } | null>(null)
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const res = await benefitsApi.listLifeEvents('pending')
      setEvents(res.life_events)
    } catch {
      toast('Failed to load life events', 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function decide() {
    if (!decision) return
    setSaving(true)
    try {
      if (decision.action === 'approve') await benefitsApi.approveLifeEvent(decision.event.id, note)
      else await benefitsApi.denyLifeEvent(decision.event.id, note)
      setDecision(null)
      setNote('')
      await load()
      toast(`Life event ${decision.action === 'approve' ? 'approved' : 'denied'}`, 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to record decision', 'error')
    } finally {
      setSaving(false)
    }
  }

  const columns: Column<LifeEvent>[] = [
    { key: 'employee', header: 'Employee', render: (e) => e.employee_name ?? e.employee_id },
    { key: 'type', header: 'Event', render: (e) => <Badge>{e.event_type.replace(/_/g, ' ')}</Badge> },
    { key: 'date', header: 'Event date', render: (e) => e.event_date },
    { key: 'description', header: 'Description', render: (e) => e.description ?? '—' },
    {
      key: 'actions', header: '', align: 'right', render: (e) => (
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="ghost" onClick={() => setDecision({ event: e, action: 'approve' })}><Check className="w-3.5 h-3.5" /></Button>
          <Button size="sm" variant="ghost" onClick={() => setDecision({ event: e, action: 'deny' })}><X className="w-3.5 h-3.5" /></Button>
        </div>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <DataTable columns={columns} rows={events} rowKey={(e) => e.id} loading={loading} emptyText="No pending life events." />

      <Modal open={!!decision} onClose={() => setDecision(null)} title={decision?.action === 'approve' ? 'Approve life event' : 'Deny life event'}>
        <div className="space-y-3">
          <Textarea label="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setDecision(null)}>Cancel</Button>
            <Button onClick={decide} disabled={saving}>
              {saving && <Loader2 className="w-4 h-4 animate-spin" />} Confirm
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
