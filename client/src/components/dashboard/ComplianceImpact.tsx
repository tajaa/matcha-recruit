import { useEffect, useState, useCallback } from 'react'
import { Card, Badge, Button, Modal } from '../ui'
import { Shield } from 'lucide-react'
import { fetchComplianceDashboard, fetchAssignableUsers, updateAlertActionPlan, assignLegislation } from '../../api/compliance'
import type { ComplianceDashboard, ComplianceDashboardItem } from '../../types/dashboard'
import type { AssignableUser } from '../../types/compliance'

const SEV_DOT: Record<string, string> = {
  critical: 'bg-red-500',
  warning: 'bg-amber-500',
  info: 'bg-zinc-500',
}

const SLA_PILL: Record<string, { label: string; cls: string }> = {
  overdue: { label: 'Overdue', cls: 'bg-red-900/50 text-red-400 border-red-800' },
  due_soon: { label: 'Due Soon', cls: 'bg-amber-900/50 text-amber-400 border-amber-800' },
  on_track: { label: 'On Track', cls: 'bg-emerald-900/50 text-emerald-400 border-emerald-800' },
  unassigned: { label: 'Unassigned', cls: 'bg-zinc-800 text-zinc-400 border-zinc-700' },
  completed: { label: 'Completed', cls: 'bg-zinc-800 text-zinc-500 border-zinc-700' },
}

const TURNAROUND_OPTIONS = [
  { label: '1d', days: 1 },
  { label: '2d', days: 2 },
  { label: '3d', days: 3 },
  { label: '5d', days: 5 },
  { label: '1w', days: 7 },
  { label: '2w', days: 14 },
]

function addDays(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return d.toISOString().split('T')[0]
}

export function ComplianceImpact() {
  const [horizon, setHorizon] = useState(90)
  const [data, setData] = useState<ComplianceDashboard | null>(null)
  const [loading, setLoading] = useState(true)

  // Action modal state
  const [selected, setSelected] = useState<ComplianceDashboardItem | null>(null)
  const [users, setUsers] = useState<AssignableUser[]>([])
  const [assignee, setAssignee] = useState('')
  const [turnaround, setTurnaround] = useState('')
  const [saving, setSaving] = useState(false)

  const load = useCallback((h: number) => {
    setLoading(true)
    fetchComplianceDashboard(h)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load(horizon) }, [horizon, load])

  const openModal = (item: ComplianceDashboardItem) => {
    setSelected(item)
    setAssignee(item.action_owner_id || '')
    setTurnaround('')
    if (users.length === 0) {
      fetchAssignableUsers().then(setUsers).catch(() => {})
    }
  }

  const handleSave = async () => {
    if (!selected) return
    setSaving(true)
    try {
      const dueDate = turnaround || undefined
      if (selected.alert_id) {
        await updateAlertActionPlan(selected.alert_id, {
          action_owner_id: assignee || undefined,
          action_due_date: dueDate,
        })
      }
      if (assignee && selected.legislation_id) {
        await assignLegislation(selected.legislation_id, {
          location_id: selected.location_id,
          action_owner_id: assignee,
          action_due_date: dueDate,
        })
      }
      setSelected(null)
      load(horizon)
    } catch {
      // silently fail — user sees no change
    } finally {
      setSaving(false)
    }
  }

  const handleMarkActioned = async () => {
    if (!selected?.alert_id) return
    setSaving(true)
    try {
      await updateAlertActionPlan(selected.alert_id, { mark_actioned: true })
      setSelected(null)
      load(horizon)
    } catch {
      // silently fail
    } finally {
      setSaving(false)
    }
  }

  const kpis = data?.kpis
  const comingUp = data?.coming_up ?? []

  return (
    <>
      <Card className="p-5">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-emerald-400" />
            <h3 className="text-sm font-medium text-zinc-200">Compliance Impact</h3>
          </div>
          <div className="flex gap-1">
            {[30, 60, 90].map((d) => (
              <Button
                key={d}
                size="sm"
                variant={horizon === d ? 'secondary' : 'ghost'}
                onClick={() => setHorizon(d)}
              >
                {d}d
              </Button>
            ))}
          </div>
        </div>

        {/* KPI row */}
        {loading ? (
          <p className="text-xs text-zinc-500 animate-pulse">Loading...</p>
        ) : kpis ? (
          <>
            <div className="grid grid-cols-7 gap-2 mb-5">
              {([
                ['Locations', kpis.total_locations],
                ['Unread', kpis.unread_alerts],
                ['Critical', kpis.critical_alerts],
                ['At Risk', kpis.employees_at_risk],
                ['Overdue', kpis.overdue_actions],
                ['Assigned', kpis.assigned_actions],
                ['Unassigned', kpis.unassigned_actions],
              ] as const).map(([label, val]) => (
                <div key={label} className="text-center">
                  <p className="text-lg font-semibold text-zinc-100">{val}</p>
                  <p className="text-[10px] text-zinc-500 uppercase tracking-wide">{label}</p>
                </div>
              ))}
            </div>

            {/* Coming up list */}
            {comingUp.length > 0 && (
              <div className="space-y-2">
                {comingUp.map((item) => {
                  const sla = SLA_PILL[item.sla_state] || SLA_PILL.unassigned
                  return (
                    <button
                      key={item.legislation_id}
                      type="button"
                      onClick={() => openModal(item)}
                      className="flex items-center gap-3 w-full rounded-lg px-3 py-2.5 text-left hover:bg-zinc-800/60 transition-colors"
                    >
                      <span className={`h-2 w-2 rounded-full shrink-0 ${SEV_DOT[item.severity] || SEV_DOT.info}`} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-zinc-200 truncate">{item.title}</p>
                        <div className="flex items-center gap-2 mt-0.5">
                          <Badge variant="neutral">{item.location_name}</Badge>
                          {item.category && <Badge variant="neutral">{item.category}</Badge>}
                          <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium ${sla.cls}`}>
                            {sla.label}
                          </span>
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        {item.days_until != null && (
                          <p className={`text-xs font-mono ${
                            item.days_until < 0 ? 'text-red-400' : item.days_until <= 30 ? 'text-amber-400' : 'text-zinc-500'
                          }`}>
                            {item.days_until < 0 ? `${Math.abs(item.days_until)}d ago` : `${item.days_until}d`}
                          </p>
                        )}
                        {item.action_owner_name && (
                          <p className="text-[10px] text-zinc-600 truncate max-w-[100px]">{item.action_owner_name}</p>
                        )}
                        {item.estimated_financial_impact && (
                          <p className="text-[10px] text-amber-500">{item.estimated_financial_impact}</p>
                        )}
                        {item.affected_employee_count > 0 && (
                          <p className="text-[10px] text-zinc-600">{item.affected_employee_count} employees</p>
                        )}
                      </div>
                    </button>
                  )
                })}
              </div>
            )}

            {comingUp.length === 0 && (
              <p className="text-xs text-zinc-600">No upcoming compliance changes in the next {horizon} days.</p>
            )}
          </>
        ) : (
          <p className="text-xs text-zinc-500">Failed to load compliance data.</p>
        )}
      </Card>

      {/* Action Modal */}
      <Modal
        open={!!selected}
        onClose={() => setSelected(null)}
        title={selected?.title || 'Action Plan'}
        width="md"
      >
        {selected && (
          <div className="space-y-4">
            {selected.description && (
              <p className="text-sm text-zinc-400">{selected.description}</p>
            )}
            {selected.next_action && (
              <div>
                <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-1">Recommended Action</p>
                <p className="text-sm text-zinc-300">{selected.next_action}</p>
              </div>
            )}

            {/* Assign To */}
            <div>
              <label className="text-[11px] text-zinc-500 uppercase tracking-wide block mb-1">
                Assign To
              </label>
              <select
                value={assignee}
                onChange={(e) => setAssignee(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200"
              >
                <option value="">Unassigned</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>{u.name} ({u.email})</option>
                ))}
              </select>
            </div>

            {/* Turnaround time */}
            <div>
              <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-2">Turnaround Time</p>
              <div className="flex gap-2">
                {TURNAROUND_OPTIONS.map((opt) => {
                  const iso = addDays(opt.days)
                  return (
                    <Button
                      key={opt.label}
                      size="sm"
                      variant={turnaround === iso ? 'secondary' : 'ghost'}
                      onClick={() => setTurnaround(iso)}
                    >
                      {opt.label}
                    </Button>
                  )
                })}
              </div>
            </div>

            {/* Buttons */}
            <div className="flex items-center gap-2 pt-2">
              <Button onClick={handleSave} disabled={saving}>
                {saving ? 'Saving...' : 'Save'}
              </Button>
              <Button variant="ghost" onClick={() => setSelected(null)}>
                Cancel
              </Button>
              {selected.alert_id && selected.action_status !== 'actioned' && (
                <Button variant="secondary" onClick={handleMarkActioned} disabled={saving} className="ml-auto">
                  Mark Actioned
                </Button>
              )}
            </div>
          </div>
        )}
      </Modal>
    </>
  )
}
