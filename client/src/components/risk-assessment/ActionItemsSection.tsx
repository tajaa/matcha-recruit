import { useEffect, useState, useCallback } from 'react'
import { api } from '../../api/client'
import { Plus, Check, X, ChevronDown, ChevronRight, User, Calendar, Clock } from 'lucide-react'
import { formatCurrency, capitalize } from '../../types/risk-assessment'
import type { ActionItem, AssignableUser, RiskAssessment, EmployeeViolation, OpenCase } from '../../types/risk-assessment'

function formatStatus(status: string): string {
  return status.replace(/_/g, ' ')
}

type Props = {
  qs: string
  assessment?: RiskAssessment
}

export function ActionItemsSection({ qs, assessment }: Props) {
  const [items, setItems] = useState<ActionItem[]>([])
  const [closedItems, setClosedItems] = useState<ActionItem[]>([])
  const [users, setUsers] = useState<AssignableUser[]>([])
  const [showHistory, setShowHistory] = useState(false)
  const [adding, setAdding] = useState<string | null>(null)

  // Extract violations and cases from assessment raw_data
  const violations: EmployeeViolation[] = (() => {
    const raw = assessment?.dimensions?.compliance?.raw_data?.employee_violations
    if (!Array.isArray(raw)) return []
    return raw.filter(
      (v): v is EmployeeViolation =>
        v && typeof v === 'object' && typeof v.employee_name === 'string' && typeof v.pay_rate === 'number',
    )
  })()

  const cases: OpenCase[] = (() => {
    const raw = assessment?.dimensions?.er_cases?.raw_data?.open_cases
    if (!Array.isArray(raw)) return []
    return raw.filter(
      (c): c is OpenCase => c && typeof c === 'object' && typeof c.title === 'string' && typeof c.status === 'string',
    )
  })()

  const fetchItems = useCallback(async () => {
    try {
      const sep = qs ? '&' : '?'
      const [open, all] = await Promise.all([
        api.get<ActionItem[]>(`/risk-assessment/action-items${qs}${sep}status=open`),
        api.get<ActionItem[]>(`/risk-assessment/action-items${qs}${sep}status=all`),
      ])
      setItems(open)
      setClosedItems(all.filter(i => i.status !== 'open'))
    } catch { /* silently fail */ }
  }, [qs])

  const fetchUsers = useCallback(async () => {
    try {
      setUsers(await api.get<AssignableUser[]>(`/risk-assessment/assignable-users${qs}`))
    } catch { /* silently fail */ }
  }, [qs])

  useEffect(() => { fetchItems(); fetchUsers() }, [fetchItems, fetchUsers])

  const trackedRefs = new Set(items.map(i => i.source_ref).filter(Boolean))
  const closedRefs = new Set(closedItems.map(i => i.source_ref).filter(Boolean))

  const suggestedViolations = violations.filter(v => !trackedRefs.has(v.employee_name) && !closedRefs.has(v.employee_name))
  const suggestedCases = cases.filter(c => !trackedRefs.has(c.case_id) && !closedRefs.has(c.case_id))

  const addItem = async (title: string, description: string, sourceType: 'wage_violation' | 'er_case', sourceRef: string) => {
    const key = `${sourceType}:${sourceRef}`
    setAdding(key)
    try {
      await api.post<ActionItem>('/risk-assessment/action-items', { title, description, source_type: sourceType, source_ref: sourceRef })
      await fetchItems()
    } catch { /* silently fail */ }
    setAdding(null)
  }

  const updateItem = async (id: string, update: { assigned_to?: string | null; due_date?: string | null; status?: 'open' | 'completed' }) => {
    try {
      await api.put<ActionItem>(`/risk-assessment/action-items/${id}`, update)
      await fetchItems()
    } catch { /* silently fail */ }
  }

  const hasSuggestions = suggestedViolations.length > 0 || suggestedCases.length > 0
  const hasItems = items.length > 0
  const hasHistory = closedItems.length > 0

  if (!hasSuggestions && !hasItems && !hasHistory) return null

  return (
    <div>
      <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-4">Action Items</div>
      <div className="space-y-4">

        {/* Suggested (auto-detected) items */}
        {hasSuggestions && (
          <div className="bg-zinc-900 border border-white/10 rounded-2xl divide-y divide-white/10 overflow-hidden">
            {suggestedViolations.length > 0 && (
              <div className="p-5">
                <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mb-3">Suggested — Wage Compliance</div>
                <div className="flex flex-col gap-2">
                  {suggestedViolations.map((v, i) => {
                    const isLarge = v.shortfall >= 10000
                    const location = v.location_city && v.location_state ? `${v.location_city}, ${v.location_state}` : v.location_state || 'Unknown'
                    const rateLabel = v.pay_classification === 'exempt' ? 'salary' : 'hourly rate'
                    const addKey = `wage_violation:${v.employee_name}`
                    return (
                      <div key={i} className="flex items-center gap-3 text-[11px]">
                        <button
                          onClick={() => addItem(
                            `${v.employee_name} below minimum wage`,
                            `${v.employee_name}'s ${rateLabel} is ${formatCurrency(v.pay_rate)} but the minimum for ${location} is ${formatCurrency(v.threshold)} (gap: ${formatCurrency(v.shortfall)})`,
                            'wage_violation',
                            v.employee_name,
                          )}
                          disabled={adding === addKey}
                          className="shrink-0 w-5 h-5 flex items-center justify-center rounded bg-white/5 hover:bg-emerald-500/20 text-zinc-600 hover:text-emerald-400 transition-colors disabled:opacity-40"
                          title="Track this item"
                        >
                          <Plus size={12} />
                        </button>
                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${isLarge ? 'bg-red-500' : 'bg-amber-500'}`} />
                        <span className="text-zinc-400">
                          <span className="text-zinc-200">{v.employee_name}</span>
                          {`'s ${rateLabel} is `}
                          <span className="font-mono text-red-400">{formatCurrency(v.pay_rate)}</span>
                          {' — min '}
                          <span className="font-mono text-zinc-300">{formatCurrency(v.threshold)}</span>
                          <span className="text-zinc-600">{` (gap: ${formatCurrency(v.shortfall)})`}</span>
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
            {suggestedCases.length > 0 && (
              <div className="p-5">
                <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mb-3">Suggested — Open ER Cases</div>
                <div className="flex flex-col gap-2">
                  {suggestedCases.map((c) => {
                    const isPending = c.status === 'pending_determination'
                    const addKey = `er_case:${c.case_id}`
                    return (
                      <div key={c.case_id} className="flex items-center gap-3 text-[11px]">
                        <button
                          onClick={() => addItem(
                            `ER case: ${c.title}`,
                            `Case '${c.title}' is ${formatStatus(c.status)}${c.category ? ` · ${formatStatus(c.category)}` : ''}`,
                            'er_case',
                            c.case_id,
                          )}
                          disabled={adding === addKey}
                          className="shrink-0 w-5 h-5 flex items-center justify-center rounded bg-white/5 hover:bg-emerald-500/20 text-zinc-600 hover:text-emerald-400 transition-colors disabled:opacity-40"
                          title="Track this item"
                        >
                          <Plus size={12} />
                        </button>
                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${isPending ? 'bg-red-500' : 'bg-amber-500'}`} />
                        <span className="text-zinc-400">
                          <span className="text-zinc-200">'{c.title}'</span>
                          {` is ${formatStatus(c.status)}`}
                          {c.category && <span className="text-zinc-600">{` · ${formatStatus(c.category)}`}</span>}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tracked (persisted) items */}
        {hasItems && (
          <div>
            <div className="text-[9px] text-zinc-400 uppercase tracking-widest font-bold mb-3">Tracked ({items.length})</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {items.map((item) => {
                const isOverdue = item.due_date && new Date(item.due_date) < new Date(new Date().toDateString())
                return (
                  <div key={item.id} className="bg-zinc-900 border border-white/10 rounded-2xl overflow-hidden group">
                    <div className={`h-0.5 ${item.source_type === 'wage_violation' ? 'bg-red-500' : 'bg-amber-500'}`} />
                    <div className="p-5 flex flex-col gap-4">
                      <div>
                        <div className="flex items-start justify-between gap-3">
                          <div className="text-[12px] text-zinc-200 font-medium leading-snug">{item.title}</div>
                          <span className={`shrink-0 text-[8px] uppercase tracking-widest font-bold px-1.5 py-0.5 rounded ${
                            item.source_type === 'wage_violation'
                              ? 'bg-red-500/10 text-red-400 border border-red-500/20'
                              : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                          }`}>
                            {item.source_type === 'wage_violation' ? 'Wage' : 'ER'}
                          </span>
                        </div>
                        {item.description && (
                          <div className="text-[10px] text-zinc-500 mt-1.5 leading-relaxed">{item.description}</div>
                        )}
                      </div>

                      {/* Controls row */}
                      <div className="flex items-center gap-2">
                        <div className="relative flex-1 min-w-0">
                          <User size={10} className="absolute left-2 top-1/2 -translate-y-1/2 text-zinc-600 pointer-events-none" />
                          <select
                            value={item.assigned_to ?? ''}
                            onChange={(e) => updateItem(item.id, { assigned_to: e.target.value || null })}
                            className="w-full bg-zinc-800/80 border border-white/5 rounded-lg pl-6 pr-2 py-1.5 text-[10px] text-zinc-300 outline-none hover:border-white/10 transition-colors appearance-none cursor-pointer truncate"
                          >
                            <option value="">Unassigned</option>
                            {users.map(u => (
                              <option key={u.id} value={u.id}>{u.name}</option>
                            ))}
                          </select>
                        </div>
                        <div className="relative shrink-0">
                          <Calendar size={10} className="absolute left-2 top-1/2 -translate-y-1/2 text-zinc-600 pointer-events-none" />
                          <input
                            type="date"
                            value={item.due_date ?? ''}
                            onChange={(e) => updateItem(item.id, { due_date: e.target.value || null })}
                            className={`bg-zinc-800/80 border rounded-lg pl-6 pr-2 py-1.5 text-[10px] outline-none hover:border-white/10 transition-colors w-[120px] cursor-pointer ${
                              isOverdue
                                ? 'border-red-500/30 text-red-400'
                                : 'border-white/5 text-zinc-300'
                            }`}
                          />
                        </div>
                      </div>

                      {isOverdue && (
                        <div className="flex items-center gap-1.5 text-[9px] text-red-400 font-mono">
                          <Clock size={10} />
                          Overdue
                        </div>
                      )}

                      <div className="flex items-center gap-2 pt-2 border-t border-white/5">
                        <button
                          onClick={() => updateItem(item.id, { status: 'completed' })}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px] font-bold uppercase tracking-widest hover:bg-emerald-500/20 transition-colors"
                        >
                          <Check size={11} />
                          Resolve
                        </button>
                        {item.assigned_to_name && (
                          <span className="ml-auto text-[9px] text-zinc-600 font-mono truncate">
                            {item.assigned_to_name}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* History (completed & dismissed) */}
        {hasHistory && (
          <div>
            <button
              onClick={() => setShowHistory(!showHistory)}
              className="flex items-center gap-1.5 text-[10px] text-zinc-400 uppercase tracking-widest font-bold hover:text-zinc-300 transition-colors mb-3"
            >
              {showHistory ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              History ({closedItems.length})
            </button>
            {showHistory && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {closedItems.map((item) => (
                  <div key={item.id} className="bg-zinc-900/60 border border-white/5 rounded-2xl overflow-hidden opacity-50 hover:opacity-75 transition-opacity">
                    <div className={`h-0.5 ${item.status === 'completed' ? 'bg-emerald-500/40' : 'bg-zinc-600/40'}`} />
                    <div className="p-4 flex items-start gap-3">
                      <span className={`mt-0.5 shrink-0 w-4 h-4 rounded-full flex items-center justify-center ${
                        item.status === 'completed'
                          ? 'bg-emerald-500/20 text-emerald-500'
                          : 'bg-zinc-700/50 text-zinc-500'
                      }`}>
                        {item.status === 'completed' ? <Check size={10} /> : <X size={10} />}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="text-[11px] text-zinc-400 line-through">{item.title}</div>
                        <div className="flex items-center gap-2 mt-1 text-[9px] text-zinc-600 font-mono">
                          <span className="uppercase tracking-widest font-bold">{capitalize(item.status)}</span>
                          {item.assigned_to_name && <span>· {item.assigned_to_name}</span>}
                          {item.closed_at && <span>· {new Date(item.closed_at).toLocaleDateString()}</span>}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
