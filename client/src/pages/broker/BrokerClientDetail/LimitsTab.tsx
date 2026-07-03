import { useState, useEffect } from 'react'
import { FileDown, Loader2 } from 'lucide-react'
import { Card } from '../../../components/ui'
import { fetchClientLimitAdequacy, downloadClientLimits } from '../../../api/broker'
import type { LimitReview } from '../../../types/limitAdequacy'
import { LIMIT_STATUS_LABEL, fmtMoney } from '../../../types/limitAdequacy'

export function LimitsTab({ companyId }: { companyId: string }) {
  const [review, setReview] = useState<LimitReview | null>(null)
  const [loading, setLoading] = useState(true)
  const [dl, setDl] = useState(false)

  useEffect(() => {
    fetchClientLimitAdequacy(companyId).then(setReview).catch(() => setReview(null)).finally(() => setLoading(false))
  }, [companyId])

  const tone = (s: string) =>
    s === 'ok' ? 'text-emerald-400' : s === 'directional_low' ? 'text-amber-400'
      : s === 'not_carried' ? 'text-zinc-500' : 'text-red-400'

  if (loading) return <Loader2 className="h-5 w-5 text-zinc-500 animate-spin" />
  if (!review) return <Card className="p-5"><p className="text-sm text-zinc-500">No limit-adequacy data.</p></Card>

  const s = review.summary
  const rows = review.lines.filter((l) => l.carried || l.contract_required || l.status === 'directional_low')
  return (
    <Card className="p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium text-zinc-200">Limit Adequacy &amp; Contract Review</h3>
          <p className="text-[11px] text-zinc-500">{s.contract_shortfalls} contract shortfall(s) · {s.baseline_lows} below baseline · {s.contracts} contract(s).</p>
        </div>
        <button
          onClick={async () => { setDl(true); try { await downloadClientLimits(companyId) } finally { setDl(false) } }}
          disabled={dl}
          className="inline-flex items-center gap-1.5 text-xs text-zinc-900 bg-zinc-100 hover:bg-white rounded-lg px-3 py-1.5 font-medium disabled:opacity-50 shrink-0"
        >
          {dl ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileDown className="h-3.5 w-3.5" />} Limits packet
        </button>
      </div>
      {rows.length === 0 ? (
        <p className="text-sm text-zinc-600">No coverage lines or contracts on file for this client.</p>
      ) : (
        <div className="space-y-1">
          {rows.map((l) => {
            const carried = l.carried ? fmtMoney(l.carried.per_occurrence) + (l.carried.aggregate ? ` / ${fmtMoney(l.carried.aggregate)}` : '') : '—'
            const req = l.contract_required ? fmtMoney(l.contract_required.per_occurrence) + (l.contract_required.aggregate ? ` / ${fmtMoney(l.contract_required.aggregate)}` : '') : '—'
            return (
              <div key={l.key} className="flex items-center gap-3 py-1.5 border-b border-zinc-800/30 last:border-0">
                <span className={`text-[10px] font-semibold uppercase w-20 shrink-0 ${tone(l.status)}`}>{LIMIT_STATUS_LABEL[l.status]}</span>
                <span className="text-sm text-zinc-200 flex-1">{l.label}</span>
                <span className="text-[11px] text-zinc-400 font-mono">carry {carried}</span>
                <span className="text-[11px] text-zinc-500 font-mono w-28 text-right">req {req}</span>
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}
