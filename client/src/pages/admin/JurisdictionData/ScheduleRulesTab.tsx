import { useEffect, useState, useCallback } from 'react'
import { api } from '../../../api/client'
import { Button, Badge } from '../../../components/ui'

type StateRow = {
  state: string
  run_status: string | null
  requirement_count: number | null
  extracted_count: number | null
  completed_at: string | null
  pending: number
  approved: number
  rejected: number
  stale: number
}

type Overview = { states: StateRow[]; code_curated_states: string[] }

type Rule = {
  id: string
  rule_key: string
  rule_value: number | null
  no_rule: boolean
  citation: string
  ai_confidence: number | null
  ai_rationale: string | null
  review_status: 'pending' | 'approved' | 'rejected'
  block_grade: boolean
  proposed: Record<string, unknown> | null
  stale_since: string | null
}

export default function ScheduleRulesTab() {
  const [overview, setOverview] = useState<Overview | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [rules, setRules] = useState<Rule[]>([])
  const [busy, setBusy] = useState(false)
  const [checked, setChecked] = useState<Set<string>>(new Set())

  const loadOverview = useCallback(async () => {
    setOverview(await api.get<Overview>('/admin/schedule-rules/overview'))
  }, [])

  useEffect(() => { loadOverview() }, [loadOverview])

  async function openState(state: string) {
    setSelected(state)
    const res = await api.get<{ state: string; rules: Rule[] }>(`/admin/schedule-rules/${state}`)
    setRules(res.rules)
    setChecked(new Set())
  }

  async function extract(states?: string[]) {
    setBusy(true)
    try {
      await api.post('/admin/schedule-rules/extract', { states })
    } finally {
      setBusy(false)
    }
  }

  async function approve(id: string) {
    await api.post(`/admin/schedule-rules/${id}/approve`, {})
    if (selected) await openState(selected)
    await loadOverview()
  }

  async function reject(id: string) {
    await api.post(`/admin/schedule-rules/${id}/reject`, {})
    if (selected) await openState(selected)
    await loadOverview()
  }

  async function acceptProposed(id: string) {
    await api.post(`/admin/schedule-rules/${id}/accept-proposed`, {})
    if (selected) await openState(selected)
    await loadOverview()
  }

  async function bulkApprove() {
    if (checked.size === 0) return
    await api.post('/admin/schedule-rules/bulk-approve', Array.from(checked))
    if (selected) await openState(selected)
    await loadOverview()
    setChecked(new Set())
  }

  async function toggleBlockGrade(id: string, next: boolean) {
    if (next && !confirm(
      'Block-grade makes this a non-overridable hard stop on the schedule write path — ' +
      'no force-through option. Only do this if you have personally verified the citation. Continue?'
    )) return
    await api.post(`/admin/schedule-rules/${id}/block-grade`, { block_grade: next })
    if (selected) await openState(selected)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-zinc-500 max-w-2xl">
          Extracts scheduling thresholds (meal breaks, overtime, minor-hour caps, rest gaps) from
          the already-codified jurisdiction catalog. Nothing here reaches the schedule-compliance
          gate until a row is approved below.
        </p>
        <Button variant="secondary" size="sm" disabled={busy} onClick={() => extract()}>
          {busy ? 'Queuing…' : 'Extract all states'}
        </Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
        {overview?.states.map((s) => (
          <button
            key={s.state}
            onClick={() => openState(s.state)}
            className={`text-left border rounded-lg p-2.5 ${selected === s.state ? 'border-zinc-400' : 'border-zinc-800'}`}
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-zinc-200">{s.state}</span>
              {s.run_status && <Badge variant={s.run_status === 'failed' ? 'danger' : 'neutral'}>{s.run_status}</Badge>}
            </div>
            <div className="text-[11px] text-zinc-500 mt-1">
              {s.approved} approved · {s.pending} pending
              {s.stale > 0 && <span className="text-amber-400"> · {s.stale} stale</span>}
            </div>
          </button>
        ))}
      </div>

      {selected && (
        <div className="border border-zinc-800 rounded-lg p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-zinc-200">{selected} rules</h3>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={() => extract([selected])}>Re-extract</Button>
              <Button variant="secondary" size="sm" disabled={checked.size === 0} onClick={bulkApprove}>
                Bulk approve ({checked.size})
              </Button>
            </div>
          </div>

          {rules.length === 0 ? (
            <p className="text-sm text-zinc-500">No rules extracted for this state yet.</p>
          ) : (
            <div className="space-y-1">
              {rules.map((r) => (
                <div key={r.id} className="flex items-start gap-2 text-sm py-2 border-b border-zinc-900 last:border-0">
                  <input
                    type="checkbox"
                    className="mt-1"
                    disabled={r.review_status === 'approved'}
                    checked={checked.has(r.id)}
                    onChange={(e) => {
                      const next = new Set(checked)
                      e.target.checked ? next.add(r.id) : next.delete(r.id)
                      setChecked(next)
                    }}
                  />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-zinc-300">{r.rule_key}</span>
                      <span className="text-zinc-100">
                        {r.no_rule ? 'no limit under law' : r.rule_value}
                      </span>
                      <Badge variant={r.review_status === 'approved' ? 'success' : r.review_status === 'rejected' ? 'danger' : 'neutral'}>
                        {r.review_status}
                      </Badge>
                      {r.stale_since && <Badge variant="warning">stale</Badge>}
                      {r.block_grade && <Badge variant="danger">block-grade</Badge>}
                    </div>
                    <p className="text-xs text-zinc-500 mt-0.5">{r.citation}</p>
                    {r.ai_rationale && <p className="text-xs text-zinc-600 mt-0.5">{r.ai_rationale}</p>}
                    {r.proposed && (
                      <p className="text-xs text-amber-400 mt-1">
                        Re-run proposes a different value — review before accepting.
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    {r.proposed && (
                      <Button variant="ghost" size="sm" onClick={() => acceptProposed(r.id)}>Accept new</Button>
                    )}
                    {r.review_status !== 'approved' && (
                      <Button variant="secondary" size="sm" onClick={() => approve(r.id)}>Approve</Button>
                    )}
                    {r.review_status !== 'rejected' && (
                      <Button variant="ghost" size="sm" onClick={() => reject(r.id)}>Reject</Button>
                    )}
                    {r.review_status === 'approved' && r.rule_key.startsWith('minor_') && (
                      <Button variant="ghost" size="sm" onClick={() => toggleBlockGrade(r.id, !r.block_grade)}>
                        {r.block_grade ? 'Un-block-grade' : 'Block-grade'}
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
