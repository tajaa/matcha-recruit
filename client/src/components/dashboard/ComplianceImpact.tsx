import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Badge, Button, Modal } from '../ui'
import { Shield, MapPin, Users, ExternalLink } from 'lucide-react'
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
  const navigate = useNavigate()
  const [horizon, setHorizon] = useState(90)
  const [data, setData] = useState<ComplianceDashboard | null>(null)
  const [loading, setLoading] = useState(true)

  // Action modal state
  const [selected, setSelected] = useState<ComplianceDashboardItem | null>(null)
  const [users, setUsers] = useState<AssignableUser[]>([])
  const [assignee, setAssignee] = useState('')
  const [turnaround, setTurnaround] = useState('')
  const [saving, setSaving] = useState(false)
  const [modalError, setModalError] = useState('')

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
    setModalError('')
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
      setModalError('Failed to save changes. Please try again.')
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
  const hasNoChanges = selected ? (assignee === (selected.action_owner_id || '') && turnaround === '') : true

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
                      className="w-full rounded-lg px-3 py-2.5 text-left hover:bg-zinc-800/60 transition-colors"
                    >
                      {/* Row 1: severity dot + title + days */}
                      <div className="flex items-center gap-3">
                        <span className={`h-2 w-2 rounded-full shrink-0 ${SEV_DOT[item.severity] || SEV_DOT.info}`} />
                        <p className="text-sm text-zinc-200 truncate flex-1">{item.title}</p>
                        {item.days_until != null && (
                          <span className={`text-xs font-mono shrink-0 ${
                            item.days_until < 0 ? 'text-red-400' : item.days_until <= 30 ? 'text-amber-400' : 'text-zinc-500'
                          }`}>
                            {item.days_until < 0 ? `${Math.abs(item.days_until)}d ago` : `${item.days_until}d`}
                          </span>
                        )}
                      </div>
                      {/* Row 2: badges */}
                      <div className="flex items-center gap-2 mt-1 ml-5">
                        <span className="inline-flex items-center gap-1 text-[10px] text-zinc-400">
                          <MapPin className="h-3 w-3" />{item.location_name}
                        </span>
                        {item.category && <Badge variant="neutral">{item.category}</Badge>}
                        <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium capitalize ${
                          item.severity === 'critical' ? 'bg-red-900/40 text-red-400 border-red-800/40' :
                          item.severity === 'warning' ? 'bg-amber-900/40 text-amber-400 border-amber-800/40' :
                          'bg-zinc-800 text-zinc-500 border-zinc-700'
                        }`}>
                          {item.severity}
                        </span>
                        <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium ${sla.cls}`}>
                          {sla.label}
                        </span>
                      </div>
                      {/* Row 3: next action */}
                      {item.next_action && (
                        <p className="text-[11px] text-zinc-400 mt-1 ml-5 truncate">
                          Next: {item.next_action}
                        </p>
                      )}
                      {/* Row 4: owner + due date */}
                      {(item.action_owner_name || item.action_due_date) && (
                        <p className="text-[10px] text-zinc-500 mt-0.5 ml-5">
                          {item.action_owner_name && <>Owner: {item.action_owner_name}</>}
                          {item.action_owner_name && item.action_due_date && ' · '}
                          {item.action_due_date && <>Due: {item.action_due_date}</>}
                        </p>
                      )}
                      {/* Row 5: financial exposure */}
                      {item.estimated_financial_impact && (
                        <p className="text-[10px] text-amber-500 mt-0.5 ml-5">
                          Exposure: {item.estimated_financial_impact}
                        </p>
                      )}
                      {/* Row 6: affected employees */}
                      {item.affected_employee_count > 0 && (
                        <p className="text-[10px] text-zinc-500 mt-0.5 ml-5 inline-flex items-center gap-1">
                          <Users className="h-3 w-3" />
                          {item.affected_employee_count} employees
                          {item.affected_employee_sample?.length > 0 && (
                            <span className="text-zinc-600">
                              — {item.affected_employee_sample.slice(0, 2).join(', ')}
                              {item.affected_employee_count > 2 && ' ~est'}
                            </span>
                          )}
                        </p>
                      )}
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
            {/* Meta badges */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1 text-[11px] text-zinc-400">
                <MapPin className="h-3 w-3" />{selected.location_name}
              </span>
              {selected.category && <Badge variant="neutral">{selected.category}</Badge>}
              <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium capitalize ${
                selected.severity === 'critical' ? 'bg-red-900/40 text-red-400 border-red-800/40' :
                selected.severity === 'warning' ? 'bg-amber-900/40 text-amber-400 border-amber-800/40' :
                'bg-zinc-800 text-zinc-500 border-zinc-700'
              }`}>
                {selected.severity}
              </span>
              {selected.effective_date && (
                <span className="text-[11px] text-zinc-500">
                  Effective: {selected.effective_date}
                  {selected.days_until != null && ` (${selected.days_until < 0 ? `${Math.abs(selected.days_until)}d ago` : `in ${selected.days_until}d`})`}
                </span>
              )}
            </div>

            {selected.description && (
              <div className="rounded-lg bg-zinc-800/50 border border-zinc-700/50 p-3">
                <p className="text-sm text-zinc-400">{selected.description}</p>
              </div>
            )}

            {selected.next_action && (
              <div>
                <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-1">Recommended Action</p>
                <p className="text-sm text-zinc-300">{selected.next_action}</p>
              </div>
            )}

            {selected.recommended_playbook && (
              <div>
                <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-1">Playbook</p>
                <p className="text-sm text-zinc-300 whitespace-pre-line">{selected.recommended_playbook}</p>
              </div>
            )}

            {selected.affected_employee_count > 0 && (
              <div>
                <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-1">Affected Employees</p>
                <p className="text-sm text-zinc-300 inline-flex items-center gap-1.5">
                  <Users className="h-3.5 w-3.5 text-zinc-400" />
                  {selected.affected_employee_count} employees
                  {selected.affected_employee_sample?.length > 0 && (
                    <span className="text-zinc-500">
                      — {selected.affected_employee_sample.slice(0, 3).join(', ')}
                      {selected.affected_employee_count > 3 && ' ~est'}
                    </span>
                  )}
                </p>
              </div>
            )}

            {selected.estimated_financial_impact && (
              <div className="rounded-lg bg-amber-900/20 border border-amber-800/30 p-3">
                <p className="text-[11px] text-amber-400 uppercase tracking-wide mb-0.5">Financial Exposure</p>
                <p className="text-sm font-medium text-amber-300">{selected.estimated_financial_impact}</p>
              </div>
            )}

            {selected.source_url && (
              <a
                href={selected.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 transition-colors"
              >
                <ExternalLink className="h-3 w-3" />
                View Source
              </a>
            )}

            <div className="border-t border-zinc-800" />

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
              {turnaround && (
                <p className="text-[11px] text-zinc-500 mt-1.5">
                  Due date will be set to {new Date(turnaround + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })} · reminder email sent when due approaches
                </p>
              )}
            </div>

            {/* Error */}
            {modalError && (
              <p className="text-xs text-red-400">{modalError}</p>
            )}

            {/* Buttons */}
            <div className="flex items-center gap-2 pt-2">
              <Button onClick={handleSave} disabled={saving || hasNoChanges}>
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

            {/* Full View link */}
            <div className="border-t border-zinc-800 pt-3">
              <button
                type="button"
                onClick={() => {
                  setSelected(null)
                  navigate(`/app/compliance?location_id=${selected.location_id}&legislation_id=${selected.legislation_id}`)
                }}
                className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
              >
                Full View &rarr;
              </button>
            </div>
          </div>
        )}
      </Modal>
    </>
  )
}
