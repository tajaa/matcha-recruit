import { useState, useEffect } from 'react'
import { Loader2 } from 'lucide-react'
import { Card } from '../../../components/ui'
import type { LossRatioData, LossRatioRow, LossPremiumBody } from '../../../types/lossDevelopment'
import { fmtMoney } from '../../../types/limitAdequacy'

// Loss Ratio = projected ultimate ÷ paid premium, per (line, policy year), with a
// per-year account rollup. Layout-neutral (a Card) so it serves as a tab here and
// a section in the off-platform client page. Reused via fetch/save props.
export function LossRatioTab({ subjectId, fetchData, savePremium }: {
  subjectId: string
  fetchData: () => Promise<LossRatioData>
  savePremium: (b: LossPremiumBody) => Promise<LossRatioData>
}) {
  const [data, setData] = useState<LossRatioData | null>(null)
  const [loading, setLoading] = useState(true)
  const [edits, setEdits] = useState<Record<string, string>>({})
  const [savingKey, setSavingKey] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    fetchData().then(setData).catch(() => setData(null)).finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subjectId])

  async function save(line: string, period: string) {
    const key = `${line}:${period}`
    if (!(key in edits)) return
    const raw = edits[key].trim()
    const parsed = raw === '' ? null : Number(raw.replace(/[,$\s]/g, ''))
    if (parsed != null && (isNaN(parsed) || parsed < 0)) return
    setSavingKey(key)
    try {
      const d = await savePremium({ line, policy_period_label: period, paid_premium: parsed })
      setData(d)
      setEdits((e) => { const n = { ...e }; delete n[key]; return n })
    } catch { /* keep the edit so the broker can retry */ }
    finally { setSavingKey(null) }
  }

  if (loading) return <Loader2 className="h-5 w-5 text-zinc-500 animate-spin" />
  if (!data || !data.has_data) {
    return (
      <Card className="p-5">
        <p className="text-sm text-zinc-500">
          No loss runs on file yet. Add carrier loss runs in the <span className="text-zinc-300">Loss Triangle</span> tab,
          then enter the premium paid here to compute loss ratios.
        </p>
      </Card>
    )
  }

  const target = data.target
  const byLine: Record<string, { label: string; rows: LossRatioRow[] }> = {}
  for (const r of data.rows) (byLine[r.line] ??= { label: r.label, rows: [] }).rows.push(r)

  return (
    <Card className="p-5 space-y-5">
      <div>
        <h3 className="text-sm font-medium text-zinc-200">Loss Ratio</h3>
        <p className="text-[11px] text-zinc-500 max-w-xl">
          Projected ultimate ÷ premium paid to the carrier, per policy year. Enter the paid premium per line/year —
          underwriters target <span className="text-emerald-400">&lt; {target}%</span> for profitability.
        </p>
      </div>

      {Object.entries(byLine).map(([line, grp]) => (
        <div key={line} className="space-y-1.5">
          <h4 className="text-xs font-semibold text-zinc-300 uppercase tracking-wide">{grp.label}</h4>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[10px] text-zinc-600 uppercase border-b border-zinc-800">
                <th className="text-left font-medium py-1 pr-2">Policy yr</th>
                <th className="text-right font-medium px-2">Proj. ultimate</th>
                <th className="text-right font-medium px-2">Premium paid</th>
                <th className="text-right font-medium px-2">Loss ratio</th>
              </tr>
            </thead>
            <tbody>
              {grp.rows.map((r) => {
                const key = `${r.line}:${r.period_label}`
                return (
                  <tr key={key} className="border-b border-zinc-800/30">
                    <td className="py-1 pr-2 text-zinc-200">{r.period_label}</td>
                    <td className="px-2 text-right font-mono text-zinc-300">{fmtMoney(r.projected_ultimate)}</td>
                    <td className="px-2 text-right">
                      <div className="inline-flex items-center justify-end gap-1.5">
                        {savingKey === key && <Loader2 className="h-3 w-3 animate-spin text-zinc-500" />}
                        <span className="text-zinc-600">$</span>
                        <input inputMode="decimal"
                          value={edits[key] ?? (r.paid_premium != null ? String(r.paid_premium) : '')}
                          onChange={(e) => setEdits((s) => ({ ...s, [key]: e.target.value }))}
                          onBlur={() => { void save(r.line, r.period_label) }}
                          onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur() }}
                          placeholder="—"
                          className="w-24 bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-right font-mono text-xs text-zinc-100 focus:outline-none focus:border-zinc-500" />
                      </div>
                    </td>
                    <td className="px-2 text-right"><LossRatioChip ratio={r.loss_ratio} status={r.status} target={target} /></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ))}

      {data.years.length > 0 && (
        <div className="pt-3 border-t border-zinc-800/50 space-y-1.5">
          <h4 className="text-xs font-semibold text-zinc-300 uppercase tracking-wide">Account rollup (all lines)</h4>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[10px] text-zinc-600 uppercase border-b border-zinc-800">
                <th className="text-left font-medium py-1 pr-2">Policy yr</th>
                <th className="text-right font-medium px-2">Total ultimate</th>
                <th className="text-right font-medium px-2">Total premium</th>
                <th className="text-right font-medium px-2">Loss ratio</th>
              </tr>
            </thead>
            <tbody>
              {data.years.map((y) => (
                <tr key={y.period_label} className="border-b border-zinc-800/30">
                  <td className="py-1 pr-2 text-zinc-200">{y.period_label}</td>
                  <td className="px-2 text-right font-mono text-zinc-300">{fmtMoney(y.total_ultimate)}</td>
                  <td className="px-2 text-right font-mono text-zinc-300">{y.total_premium != null ? fmtMoney(y.total_premium) : '—'}</td>
                  <td className="px-2 text-right"><LossRatioChip ratio={y.loss_ratio} status={y.status} target={target} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

function LossRatioChip({ ratio, status, target }: { ratio: number | null; status: string; target: number }) {
  if (ratio == null) return <span className="text-[11px] text-zinc-600">— need premium</span>
  const tone = status === 'adverse'
    ? 'bg-red-500/15 text-red-300 border-red-500/30'
    : 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
  return (
    <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 font-mono text-xs ${tone}`} title={`Underwriters target < ${target}%`}>
      {ratio}% {status === 'adverse' ? '✗' : '✓'}
    </span>
  )
}
