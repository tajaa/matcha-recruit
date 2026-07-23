import { useEffect, useState } from 'react'
import { Check, Loader2, X } from 'lucide-react'
import { Badge, Button, Card, DataTable, Modal, Select, Textarea, useToast } from '../../components/ui'
import type { Column } from '../../components/ui'
import { benefitsApi } from '../../api/benefits/benefits'
import type { Election, OePeriod } from '../../api/benefits/benefits'

const STATUS_VARIANT = { draft: 'neutral', submitted: 'warning', approved: 'success', rejected: 'danger' } as const

export function ElectionsReviewTab({ periods }: { periods: OePeriod[] }) {
  const { toast } = useToast()
  const [periodId, setPeriodId] = useState<string>('')
  const [elections, setElections] = useState<Election[]>([])
  const [statusCounts, setStatusCounts] = useState<Record<string, number>>({})
  const [notSubmitted, setNotSubmitted] = useState<{ employee_id: string; employee_name: string }[]>([])
  const [loading, setLoading] = useState(false)
  const [decision, setDecision] = useState<{ election: Election; action: 'approve' | 'reject' } | null>(null)
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!periodId && periods.length) setPeriodId(periods[0].id)
  }, [periods, periodId])

  async function load(id: string) {
    if (!id) return
    setLoading(true)
    try {
      const res = await benefitsApi.reviewPeriodElections(id)
      setElections(res.elections)
      setStatusCounts(res.status_counts)
      setNotSubmitted(res.not_submitted)
    } catch {
      toast('Failed to load elections', 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(periodId) }, [periodId]) // eslint-disable-line react-hooks/exhaustive-deps

  async function decide() {
    if (!decision) return
    setSaving(true)
    try {
      if (decision.action === 'approve') await benefitsApi.approveElection(decision.election.id, note)
      else await benefitsApi.rejectElection(decision.election.id, note)
      setDecision(null)
      setNote('')
      await load(periodId)
      toast(`Election ${decision.action}d`, 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to record decision', 'error')
    } finally {
      setSaving(false)
    }
  }

  const columns: Column<Election>[] = [
    { key: 'employee', header: 'Employee', render: (e) => e.employee_name ?? e.employee_id },
    { key: 'plan_type', header: 'Type', render: (e) => <Badge>{e.plan_type}</Badge> },
    { key: 'plan', header: 'Election', render: (e) => e.waived ? 'Waived' : `${e.plan_name ?? ''} — ${e.coverage_tier ?? ''}` },
    { key: 'status', header: 'Status', render: (e) => <Badge variant={STATUS_VARIANT[e.status]}>{e.status}</Badge> },
    {
      key: 'actions', header: '', align: 'right', render: (e) => e.status === 'submitted' ? (
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="ghost" onClick={() => setDecision({ election: e, action: 'approve' })}><Check className="w-3.5 h-3.5" /></Button>
          <Button size="sm" variant="ghost" onClick={() => setDecision({ election: e, action: 'reject' })}><X className="w-3.5 h-3.5" /></Button>
        </div>
      ) : null,
    },
  ]

  return (
    <div className="space-y-4">
      <div className="max-w-xs">
        <Select label="Enrollment period" value={periodId}
          options={periods.map((p) => ({ value: p.id, label: `${p.name} (${p.status})` }))}
          onChange={(e) => setPeriodId(e.target.value)} />
      </div>

      {Object.keys(statusCounts).length > 0 && (
        <div className="flex gap-3 flex-wrap">
          {Object.entries(statusCounts).map(([status, n]) => (
            <Card key={status} className="px-4 py-2">
              <div className="text-xs text-zinc-500 uppercase">{status}</div>
              <div className="text-lg font-semibold text-zinc-100">{n}</div>
            </Card>
          ))}
        </div>
      )}

      <DataTable columns={columns} rows={elections} rowKey={(e) => e.id} loading={loading} emptyText="No elections for this period yet." />

      {notSubmitted.length > 0 && (
        <Card className="p-4">
          <div className="text-sm font-medium text-zinc-300 mb-2">Not yet submitted ({notSubmitted.length})</div>
          <div className="text-sm text-zinc-500 space-y-1">
            {notSubmitted.map((e) => <div key={e.employee_id}>{e.employee_name}</div>)}
          </div>
        </Card>
      )}

      <Modal open={!!decision} onClose={() => setDecision(null)} title={decision?.action === 'approve' ? 'Approve election' : 'Reject election'}>
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
